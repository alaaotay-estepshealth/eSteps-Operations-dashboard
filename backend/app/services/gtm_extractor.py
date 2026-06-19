"""Orchestrator that turns the GTM-2026-OS markdown corpus into a structured plan.

Pipeline per run:
  1. load_corpus()                  — pull GTM-2026-OS/* text from strategy_assets
  2. build prompt + cache marker    — concat corpus into one system block
  3. call_anthropic()               — Claude Opus 4.7 Messages API
  4. validate output (Pydantic)     — fail closed if model returns garbage
  5. write ai_requests row          — audit + cost
  6. upsert_initiatives()           — supersede prior 'suggested' per period

Authority: markdown wins. Initiatives land as status='suggested' — operators
flip individual rows to 'applied' or 'rejected' from the dashboard.
"""
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.config import settings
from app.models.ai_request import AIRequest
from app.models.gtm_initiative import GtmInitiative
from app.models.strategy_asset import StrategyAsset
from app.models.system import System
from app.models.user import User
from app.schemas.gtm_plan import GtmAiOutput
from app.services.anthropic import call_anthropic, compute_cost, AnthropicError


class GtmExtractorError(RuntimeError):
    pass


_GTM_CORPUS_PREFIX = "GTM-2026-OS/"
_TEXT_EXTENSIONS = {".md", ".txt", ".rst"}
_PERIOD_TO_DAYS = {"30d": 30, "60d": 60, "90d": 90}
_DEFAULT_SYSTEM_SLUG = "esteps-leads"


def default_system_id(db: Session) -> UUID:
    """System to anchor a cross-product GTM AIRequest row to.

    ai_requests.system_id is NOT NULL (migration 0002). GTM plans span every
    product, so they are anchored to the primary system (esteps-leads) — the
    same row 0002 backfills existing ai_requests to. Falls back to the oldest
    active system, and bootstraps an esteps-leads row if the registry is empty
    (e.g. a schema created via create_all that never ran the 0002 seed).
    """
    system = (
        db.query(System).filter(System.slug == _DEFAULT_SYSTEM_SLUG).first()
        or db.query(System)
        .filter(System.is_active.is_(True))
        .order_by(System.created_at.asc())
        .first()
    )
    if system is None:
        system = System(
            slug=_DEFAULT_SYSTEM_SLUG,
            name="eSteps Leads",
            description="Academic researcher outreach and partnership pipeline",
            webhook_secret=secrets.token_urlsafe(32),
            is_active=True,
        )
        db.add(system)
        db.commit()
        db.refresh(system)
    return system.id


def load_corpus(db: Session) -> List[Dict[str, Any]]:
    """One query, all GTM-2026-OS text. Decodes content blob to UTF-8."""
    rows = (
        db.query(StrategyAsset)
        .filter(
            StrategyAsset.is_folder.is_(False),
            StrategyAsset.relative_path.like(f"{_GTM_CORPUS_PREFIX}%"),
            StrategyAsset.content.isnot(None),
        )
        .order_by(StrategyAsset.relative_path.asc())
        .all()
    )
    out: List[Dict[str, Any]] = []
    for r in rows:
        ext = "." + (r.name.rsplit(".", 1)[-1].lower() if "." in r.name else "")
        if ext not in _TEXT_EXTENSIONS:
            continue
        try:
            text = bytes(r.content).decode("utf-8", errors="replace")
        except Exception:
            continue
        out.append({"path": r.relative_path, "name": r.name, "content": text})
    return out


def build_system_blocks(corpus: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """First block: instructions. Second block: corpus with ephemeral cache."""
    instructions = (
        "You are eSteps' GTM strategy analyst. Read the GTM Operating System "
        "files below and emit ONE JSON object that strictly conforms to this schema:\n"
        "{\n"
        '  "executive_summary": "<markdown, 200-400 words, current state + biggest risks>",\n'
        '  "kpi_targets": [\n'
        '    {"period": "30d|60d|90d", "objective": "<short label>",\n'
        '     "target": <number>, "unit": "<string>",\n'
        '     "rationale": "<cite source file + line>",\n'
        '     "assignee_label": "<Nidhal|Alaa|Growth Content Associate|...>"}\n'
        "  ],\n"
        '  "risk_flags": [{"label": "<short>", "severity": "low|medium|high", "source": "<file>"}],\n'
        '  "recommended_focus": ["<imperative>", "<imperative>", "<imperative>"],\n'
        '  "source_files": [{"name": "<file>", "path": "<full path>", "tokens": <int>}]\n'
        "}\n\n"
        "Output ONLY the JSON object — no prose, no markdown fences. The output "
        "is parsed by a Pydantic validator that fails closed on extra keys at "
        "the top level (kpi_targets entries may have extras silently dropped). "
        "Assignee labels should match how the team is referenced in the source "
        "files; the backend resolves them to user accounts."
    )
    corpus_text = "\n\n".join(
        f"=== {f['path']} ===\n{f['content']}" for f in corpus
    )
    return [
        {"type": "text", "text": instructions},
        {"type": "text", "text": corpus_text, "cache_control": {"type": "ephemeral"}},
    ]


def resolve_assignee(db: Session, label: Optional[str]) -> Optional[UUID]:
    """Case-insensitive match on username, then display_name. None on miss."""
    if not label:
        return None
    label_lower = label.strip().lower()
    if not label_lower:
        return None
    row = (
        db.query(User)
        .filter(
            or_(
                User.username.ilike(label),
                User.display_name.ilike(label),
            )
        )
        .first()
    )
    return row.id if row else None


def upsert_initiatives(
    db: Session,
    *,
    source_ai_request_id: UUID,
    kpi_targets: List[Dict[str, Any]],
) -> List[GtmInitiative]:
    """Supersede prior 'suggested' rows for this run's periods, then insert fresh.

    Only 'suggested' rows are superseded — 'applied' and 'rejected' rows are
    intentionally left untouched. The UPDATE runs before INSERT so we never
    accidentally supersede rows we just created.
    """
    periods = sorted({k.get("period") for k in kpi_targets if k.get("period")})
    if periods:
        (
            db.query(GtmInitiative)
            .filter(GtmInitiative.status == "suggested", GtmInitiative.period.in_(periods))
            .update({"status": "superseded", "updated_at": datetime.now(timezone.utc)}, synchronize_session=False)
        )

    now = datetime.now(timezone.utc)
    inserted: List[GtmInitiative] = []
    for k in kpi_targets:
        period = k.get("period")
        if period not in _PERIOD_TO_DAYS:
            continue
        due = now + timedelta(days=_PERIOD_TO_DAYS[period])
        assignee_label = k.get("assignee_label")
        row = GtmInitiative(
            period=period,
            objective_label=k.get("objective", "")[:1000],
            target_value=k.get("target"),
            target_unit=k.get("unit"),
            rationale=k.get("rationale"),
            assignee_label=assignee_label,
            assignee_user_id=resolve_assignee(db, assignee_label),
            due_at=due,
            status="suggested",
            source_ai_request_id=source_ai_request_id,
        )
        db.add(row)
        inserted.append(row)
    return inserted


def generate_gtm_plan(db: Session, ai_req: Optional[AIRequest] = None) -> AIRequest:
    """Full pipeline. Returns the AIRequest row (status='completed' or 'rejected').

    When ai_req is None, creates its own AIRequest row (standalone / test path).
    When ai_req is supplied, the router endpoint pre-created it to return an
    execution_id immediately; this function reuses and mutates that row.
    """
    corpus = load_corpus(db)
    if not corpus:
        raise GtmExtractorError(
            "Corpus empty — no GTM-2026-OS files in strategy_assets. "
            "Run POST /admin/gtm/sync."
        )

    system_blocks = build_system_blocks(corpus)
    user_message = (
        f"Today is {datetime.now(timezone.utc).date().isoformat()}. "
        "Active products: eSteps Health, Mitus, eSteps Studio. "
        "Produce the JSON object now."
    )

    if ai_req is None:
        ai_req = AIRequest(
            request_type="gtm_retrospective",
            provider="anthropic",
            model=settings.gtm_model,
            status="pending_review",
            input_preview="GTM ingest run",
            system_id=default_system_id(db),
        )
        db.add(ai_req)
        db.commit()
        db.refresh(ai_req)

    try:
        result = call_anthropic(system_blocks=system_blocks, user_message=user_message)
    except AnthropicError as e:
        ai_req.status = "rejected"
        ai_req.ai_output = {"error": str(e)}
        db.commit()
        return ai_req

    usage = result.get("usage", {})
    ai_req.tokens_used = (
        usage.get("input_tokens", 0)
        + usage.get("output_tokens", 0)
        + usage.get("cache_creation_input_tokens", 0)
        + usage.get("cache_read_input_tokens", 0)
    )
    ai_req.cost_usd = compute_cost(usage)

    try:
        parsed = json.loads(result["text"])
        validated = GtmAiOutput.model_validate(parsed)
    except (json.JSONDecodeError, ValidationError) as e:
        ai_req.status = "rejected"
        ai_req.ai_output = {
            "error": f"output_validation_failed: {str(e)[:500]}",
            "raw_preview": result["text"][:500],
        }
        db.commit()
        return ai_req

    ai_req.status = "completed"
    ai_req.ai_output = validated.model_dump(mode="json")
    db.commit()

    upsert_initiatives(
        db,
        source_ai_request_id=ai_req.id,
        kpi_targets=[k.model_dump() for k in validated.kpi_targets],
    )
    db.commit()
    db.refresh(ai_req)
    return ai_req


def gtm_today_spend_usd(db: Session) -> float:
    """Sum of cost_usd for today's gtm_retrospective rows (UTC date)."""
    from sqlalchemy import func, cast, Date

    val = (
        db.query(func.coalesce(func.sum(AIRequest.cost_usd), 0.0))
        .filter(
            AIRequest.request_type == "gtm_retrospective",
            cast(AIRequest.created_at, Date) == datetime.now(timezone.utc).date(),
        )
        .scalar()
    )
    return float(val or 0.0)
