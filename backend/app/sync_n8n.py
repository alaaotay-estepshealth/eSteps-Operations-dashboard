"""
Sync n8n executions → workflow_executions table.

Usage:
    python -m app.sync_n8n              # sync last 100 executions
    python -m app.sync_n8n --limit 500  # sync last 500

Idempotent — skips executions already in DB (ON CONFLICT execution_id).
"""
import argparse
import logging
import sys
from datetime import datetime, timezone

import httpx
from sqlalchemy import text

from app.config import settings
from app.database import SessionLocal

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

# ── n8n workflow ID → system slug mapping ────────────────────────────────────
WORKFLOW_MAP: dict[str, str] = {
    # esteps-leads (EST-1 through EST-8)
    "n8ZOWUUlpJbDlB6g": "esteps-leads",
    "Qpr7fVyFFhdi9CFy": "esteps-leads",
    "mxugXEP3EDEpY0dS": "esteps-leads",
    "JoWavDCF9sRjXagL": "esteps-leads",
    "n4jzQtRuEAEi8ggZ": "esteps-leads",
    "27NF6TG52urkcveh": "esteps-leads",
    "MDOzG7XIO6zQnnLL": "esteps-leads",
    "MTzwnOP75eG5fo0k": "esteps-leads",
    # wam-agency (WAM-1 through WAM-5)
    "i0ZgNoJyqudlEsss": "wam-agency",
    "V1ihv6CVUmuVCF7Z": "wam-agency",
    "enFBeoo2efgpPA9I": "wam-agency",
    "cyKaYQm3X2CEvzf6": "wam-agency",
    "UZDfq5AxKrJqoQwx": "wam-agency",
    # ai-chatbot (eSteps Support)
    "kOSeU48fgGRceFEn": "ai-chatbot",
    "vSldRHd3qFtlL9Cx": "ai-chatbot",
    "JeqwV8m32mZAnj51": "ai-chatbot",
    "sY0GhqxJoOeTaCTQ": "ai-chatbot",
    # solar-leads (WF-A through WF-E)
    "RkPRnKbEziwkW4gD": "solar-leads",
    "gNdsFRZLwR5ex9KF": "solar-leads",
    "LeMqX20nx2hn3Lo2": "solar-leads",
    "czkqrtMtXq6NBfDh": "solar-leads",
    "XlYnGta8YQ7nkQ2I": "solar-leads",
    # ai-influencer (Jane-1 through Jane-5)
    "fCri7YlCEymZt2Cs": "ai-influencer",
    "rGMQWyoYc3wU5563": "ai-influencer",
    "N1u3zM6YfvzTv8sZ": "ai-influencer",
    "KTtGBTZsww9gDyKM": "ai-influencer",
    "ksDUrAZ456Qbg3wU": "ai-influencer",
}

# n8n workflow ID → human-readable name
WORKFLOW_NAMES: dict[str, str] = {
    "n8ZOWUUlpJbDlB6g": "EST-1: Lead Intake & Enrichment",
    "Qpr7fVyFFhdi9CFy": "EST-2: Outreach Engine V2",
    "mxugXEP3EDEpY0dS": "EST-3: Reply Handler",
    "JoWavDCF9sRjXagL": "EST-4: RAG Ingestion",
    "n4jzQtRuEAEi8ggZ": "EST-5: Booking & CRM Sync",
    "27NF6TG52urkcveh": "EST-6: LinkedIn Actions",
    "MDOzG7XIO6zQnnLL": "EST-7: Follow-up & No-Response Logic",
    "MTzwnOP75eG5fo0k": "EST-8: Lead Scoring & Segmentation",
    "i0ZgNoJyqudlEsss": "WAM-1: Lead Import",
    "V1ihv6CVUmuVCF7Z": "WAM-2: Outreach Sequence Engine",
    "enFBeoo2efgpPA9I": "WAM-3: Reply Handler",
    "cyKaYQm3X2CEvzf6": "WAM-4: WhatsApp Reply Handler",
    "UZDfq5AxKrJqoQwx": "WAM-5: RAG Ingestion",
    "kOSeU48fgGRceFEn": "eSteps Health AI Chatbot v4.2",
    "vSldRHd3qFtlL9Cx": "Support Ticket Classifier",
    "JeqwV8m32mZAnj51": "eSteps Health AI Customer Chatbot",
    "sY0GhqxJoOeTaCTQ": "eSteps Health AI Chatbot v3",
    "RkPRnKbEziwkW4gD": "WF-A: Ingestion & Strategy Engine",
    "gNdsFRZLwR5ex9KF": "WF-B: Nurturer Sequence Dispatcher",
    "LeMqX20nx2hn3Lo2": "WF-C: AI Sales Agent",
    "czkqrtMtXq6NBfDh": "WF-D: Daily Digest & CRM Sync",
    "XlYnGta8YQ7nkQ2I": "WF-E: Error Handler",
    "fCri7YlCEymZt2Cs": "Jane-1: Brand Import",
    "rGMQWyoYc3wU5563": "Jane-2: Daily Outreach Engine",
    "N1u3zM6YfvzTv8sZ": "Jane-3: Reply Handler",
    "KTtGBTZsww9gDyKM": "Jane-4: New Brand Outreach (Manual)",
    "ksDUrAZ456Qbg3wU": "Jane-5: Call Booked Handler",
}

N8N_STATUS_MAP = {
    "success": "success",
    "error": "failed",
    "running": "running",
    "waiting": "running",
    "crashed": "failed",
    "new": "running",
}


def _parse_ts(ts_str: str | None) -> datetime | None:
    if not ts_str:
        return None
    return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))


def _fetch_executions(limit: int = 100) -> list[dict]:
    url = f"{settings.n8n_base_url}/api/v1/executions"
    headers = {"X-N8N-API-KEY": settings.n8n_api_key}
    all_execs: list[dict] = []
    cursor: str | None = None

    while len(all_execs) < limit:
        params: dict = {"limit": min(250, limit - len(all_execs))}
        if cursor:
            params["cursor"] = cursor

        resp = httpx.get(url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        batch = data.get("data", [])
        if not batch:
            break
        all_execs.extend(batch)

        cursor = data.get("nextCursor")
        if not cursor:
            break

    return all_execs[:limit]


def _load_system_ids(db) -> dict[str, str]:
    """slug → system UUID string."""
    rows = db.execute(text("SELECT id, slug FROM systems")).fetchall()
    return {r.slug: str(r.id) for r in rows}


def sync(limit: int = 100) -> dict:
    db = SessionLocal()
    try:
        system_ids = _load_system_ids(db)
        if not system_ids:
            log.error("No systems in DB. Run wire_production.sql first.")
            return {"inserted": 0, "skipped": 0, "unmapped": 0}

        execs = _fetch_executions(limit)
        log.info("Fetched %d executions from n8n", len(execs))

        inserted = 0
        skipped = 0
        unmapped = 0

        for ex in execs:
            wf_id = ex.get("workflowId", "")
            slug = WORKFLOW_MAP.get(wf_id)
            if not slug:
                unmapped += 1
                continue

            system_uuid = system_ids.get(slug)
            if not system_uuid:
                unmapped += 1
                continue

            exec_id = str(ex.get("id", ""))
            started = _parse_ts(ex.get("startedAt"))
            finished = _parse_ts(ex.get("stoppedAt"))
            status = N8N_STATUS_MAP.get(ex.get("status", ""), "failed")

            duration = None
            if started and finished:
                duration = round((finished - started).total_seconds(), 2)

            error_msg = None
            if status == "failed":
                error_msg = "Execution failed (see n8n for details)"

            try:
                result = db.execute(
                    text("""
                        INSERT INTO workflow_executions
                            (id, system_id, workflow_id, workflow_name, execution_id,
                             status, started_at, finished_at, duration_seconds,
                             error_message, created_at)
                        VALUES
                            (gen_random_uuid(), :system_id, :workflow_id, :workflow_name,
                             :execution_id, :status, :started_at, :finished_at,
                             :duration_seconds, :error_message, now())
                        ON CONFLICT (execution_id) DO NOTHING
                    """),
                    {
                        "system_id": system_uuid,
                        "workflow_id": wf_id,
                        "workflow_name": WORKFLOW_NAMES.get(wf_id, wf_id),
                        "execution_id": exec_id,
                        "status": status,
                        "started_at": started,
                        "finished_at": finished,
                        "duration_seconds": duration,
                        "error_message": error_msg,
                    },
                )
                if result.rowcount > 0:
                    inserted += 1
                else:
                    skipped += 1
            except Exception:
                skipped += 1

        db.commit()
        log.info("Done — inserted=%d  skipped=%d  unmapped=%d", inserted, skipped, unmapped)
        return {"inserted": inserted, "skipped": skipped, "unmapped": unmapped}
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sync n8n executions to ops DB")
    parser.add_argument("--limit", type=int, default=100, help="Max executions to fetch")
    args = parser.parse_args()
    result = sync(args.limit)
    print(f"\nResult: {result}")
    sys.exit(0 if result["inserted"] >= 0 else 1)
