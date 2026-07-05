from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_admin, require_operator
from app.database import get_db, get_leads_db
from app.models.user import User
from app.models.workflow_execution import WorkflowExecution
from app.services.gemini import call_gemini

router = APIRouter(prefix="/admin/insights", tags=["insights"])

# GTM targets — sourced from GTM_Master_Strategy.md
TARGET_REPLY_RATE = 8.0       # %
TARGET_MEETING_RATE = 3.0     # %
TARGET_ACTIVATION = 60.0      # % of leads contacted
TARGET_WEEKLY_OUTREACH = 100  # 100–150 / week
HOT_SCORE = 7                 # score >= 7 = MQL-eligible (24h handoff SLA)


def _pct(n: int, d: int) -> float:
    return round(n / d * 100, 1) if d else 0.0


def _status(value: float, target: float, higher_is_better: bool = True) -> str:
    if higher_is_better:
        if value >= target:
            return "green"
        return "amber" if value >= target * 0.6 else "red"
    if value <= target:
        return "green"
    return "amber" if value <= target * 1.4 else "red"


@router.get("")
def get_insights(
    days: int = Query(7, ge=1, le=90),
    leads_db: Session = Depends(get_leads_db),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    lq = lambda s, p=None: leads_db.execute(text(s), p or {}).scalar() or 0

    total = lq("SELECT count(*) FROM leads")
    contacted = lq("SELECT count(*) FROM leads WHERE email1_sent_at IS NOT NULL")

    # Real replies live in `conversations` (inbound); fall back to the leads flag.
    try:
        replied = lq("SELECT count(DISTINCT lead_id) FROM conversations WHERE direction = 'inbound'")
    except Exception:
        replied = lq("SELECT count(*) FROM leads WHERE reply_received IS TRUE")

    meetings = lq(
        "SELECT count(*) FROM leads WHERE meeting_booked_at IS NOT NULL OR meeting_scheduled_for IS NOT NULL"
    )

    reply_rate = _pct(replied, contacted)
    meeting_rate = _pct(meetings, contacted)
    activation = _pct(contacted, total)

    sent_7 = lq("SELECT count(*) FROM leads WHERE email1_sent_at >= now() - interval '7 days'")
    sent_prev_7 = lq(
        "SELECT count(*) FROM leads WHERE email1_sent_at >= now() - interval '14 days' "
        "AND email1_sent_at < now() - interval '7 days'"
    )

    kpis = [
        {"label": "Reply rate", "value": reply_rate, "target": TARGET_REPLY_RATE,
         "unit": "%", "status": _status(reply_rate, TARGET_REPLY_RATE), "link": "/emails"},
        {"label": "Meeting rate", "value": meeting_rate, "target": TARGET_MEETING_RATE,
         "unit": "%", "status": _status(meeting_rate, TARGET_MEETING_RATE), "link": "/bookings"},
        {"label": "Activation", "value": activation, "target": TARGET_ACTIVATION,
         "unit": "%", "status": _status(activation, TARGET_ACTIVATION), "link": "/pipeline"},
        {"label": "Outreach / 7d", "value": sent_7, "target": TARGET_WEEKLY_OUTREACH,
         "unit": "", "status": _status(sent_7, TARGET_WEEKLY_OUTREACH), "link": "/workflows"},
    ]

    # Sequence funnel (touches 1–5)
    sequence_funnel = [
        {"step": f"Email {n}", "count": lq(f"SELECT count(*) FROM leads WHERE email{n}_sent_at IS NOT NULL")}
        for n in (1, 2, 3, 4, 5)
    ]

    # Lead-score distribution
    score_rows = leads_db.execute(text(
        "SELECT lead_score, count(*) AS n FROM leads WHERE lead_score IS NOT NULL "
        "GROUP BY lead_score ORDER BY lead_score"
    )).mappings().all()
    score_distribution = [{"score": r["lead_score"], "count": r["n"]} for r in score_rows]

    hot = lq(f"SELECT count(*) FROM leads WHERE lead_score >= {HOT_SCORE}")
    hot_uncontacted = lq(
        f"SELECT count(*) FROM leads WHERE lead_score >= {HOT_SCORE} AND email1_sent_at IS NULL"
    )

    # Follow-ups
    overdue = lq("SELECT count(*) FROM leads WHERE next_send_date < CURRENT_DATE")
    upcoming = lq("SELECT count(*) FROM leads WHERE next_send_date >= CURRENT_DATE")

    # Segment performance (top research areas)
    seg_rows = leads_db.execute(text(
        "SELECT COALESCE(research_interest, 'general') AS area, count(*) AS total, "
        "count(*) FILTER (WHERE email1_sent_at IS NOT NULL) AS contacted "
        "FROM leads GROUP BY research_interest ORDER BY total DESC LIMIT 8"
    )).mappings().all()
    segments = [
        {"area": r["area"], "total": r["total"], "contacted": r["contacted"],
         "activation_pct": _pct(r["contacted"], r["total"])}
        for r in seg_rows
    ]

    # Week-over-week comparison
    now = datetime.utcnow()
    ex_7 = db.query(WorkflowExecution).filter(
        WorkflowExecution.started_at >= now - timedelta(days=7)
    ).count()
    ex_prev_7 = db.query(WorkflowExecution).filter(
        WorkflowExecution.started_at >= now - timedelta(days=14),
        WorkflowExecution.started_at < now - timedelta(days=7),
    ).count()
    comparison = {
        "period": "week",
        "metrics": [
            {"label": "Outreach sent", "current": sent_7, "previous": sent_prev_7, "delta": sent_7 - sent_prev_7},
            {"label": "Workflow runs", "current": ex_7, "previous": ex_prev_7, "delta": ex_7 - ex_prev_7},
        ],
    }

    # Month-over-month
    sent_30 = lq("SELECT count(*) FROM leads WHERE email1_sent_at >= now() - interval '30 days'")
    sent_prev_30 = lq(
        "SELECT count(*) FROM leads WHERE email1_sent_at >= now() - interval '60 days' "
        "AND email1_sent_at < now() - interval '30 days'"
    )
    ex_30 = db.query(WorkflowExecution).filter(WorkflowExecution.started_at >= now - timedelta(days=30)).count()
    ex_prev_30 = db.query(WorkflowExecution).filter(
        WorkflowExecution.started_at >= now - timedelta(days=60),
        WorkflowExecution.started_at < now - timedelta(days=30),
    ).count()
    monthly = [
        {"label": "Outreach sent", "current": sent_30, "previous": sent_prev_30, "delta": sent_30 - sent_prev_30},
        {"label": "Workflow runs", "current": ex_30, "previous": ex_prev_30, "delta": ex_30 - ex_prev_30},
    ]

    # Weekly outreach trend (last 8 weeks)
    try:
        trend_rows = leads_db.execute(text(
            "SELECT to_char(date_trunc('week', email1_sent_at), 'MM-DD') AS wk, count(*) AS n "
            "FROM leads WHERE email1_sent_at >= now() - interval '8 weeks' "
            "GROUP BY date_trunc('week', email1_sent_at) ORDER BY date_trunc('week', email1_sent_at)"
        )).mappings().all()
        trend = [{"label": r["wk"], "value": r["n"]} for r in trend_rows]
    except Exception:
        trend = []

    # Goal progress (GTM: 30–50 partnerships; pilots)
    qualified_contacted = lq("SELECT count(*) FROM leads WHERE lead_score >= 7 AND email1_sent_at IS NOT NULL")
    goals = {
        "partnerships": {"current": meetings, "target": 30, "label": "Partnerships (meetings)"},
        "qualified_engaged": {"current": replied, "target": qualified_contacted or 1, "label": "Replies vs qualified outreach"},
        "activation": {"current": contacted, "target": total, "label": "Leads contacted"},
    }

    # ── Recommendation engine (GTM decision levers) ──────────────────────────
    recs = []
    if sent_7 == 0:
        recs.append({
            "severity": "high", "focus": "Outreach volume",
            "title": "No outreach sent in the last 7 days",
            "detail": f"Pipeline is idle vs the 100–150/week target. {total - contacted} leads have never been emailed.",
        })
    elif sent_7 < TARGET_WEEKLY_OUTREACH:
        recs.append({
            "severity": "medium", "focus": "Outreach volume",
            "title": f"Only {sent_7} sent this week (target 100–150)",
            "detail": "Below cadence. Ramp the daily send batch (respect the 25–30/inbox/day cap).",
        })
    if hot_uncontacted > 0:
        recs.append({
            "severity": "high", "focus": "Hot-lead activation",
            "title": f"{hot_uncontacted} hot leads (score ≥ 7) never contacted",
            "detail": "High-fit leads sitting idle. Prioritise these in the next send batch — they clear the MQL bar.",
        })
    if overdue > 0:
        recs.append({
            "severity": "high" if overdue > 50 else "medium", "focus": "Follow-up cadence",
            "title": f"{overdue} follow-ups overdue",
            "detail": "next_send_date has passed. Signal-triggered leads decay fast — clear the follow-up queue.",
        })
    if contacted and reply_rate < TARGET_REPLY_RATE:
        recs.append({
            "severity": "high", "focus": "ICP & personalization",
            "title": f"Reply rate {reply_rate}% below the 8% target",
            "detail": "Tighten ICP fit (cut daily volume), lead with one specific signal, deepen personalization.",
        })
    if contacted and meeting_rate < TARGET_MEETING_RATE:
        recs.append({
            "severity": "medium", "focus": "Free-asset quality",
            "title": f"Meeting rate {meeting_rate}% below the 3% target",
            "detail": "Audit free-asset specificity — each asset should show ONE unique gap for that lead.",
        })
    e3, e4 = sequence_funnel[2]["count"], sequence_funnel[3]["count"]
    if e3 and e4 < e3 * 0.7:
        recs.append({
            "severity": "medium", "focus": "Sequence completion",
            "title": f"Sequence stalls after step 3 ({e3} → {e4})",
            "detail": "The Day-14 LinkedIn DM / Day-21 break-up touches are under-firing. Check the later-touch automation.",
        })
    if not recs:
        recs.append({
            "severity": "info", "focus": "On track",
            "title": "All tracked KPIs within target",
            "detail": "Maintain cadence and keep monitoring week-over-week trends.",
        })

    return {
        "generated_at": now.isoformat(),
        "kpis": kpis,
        "comparison": comparison,
        "monthly": monthly,
        "trend": trend,
        "goals": goals,
        "sequence_funnel": sequence_funnel,
        "score_distribution": score_distribution,
        "hot_leads": hot,
        "hot_uncontacted": hot_uncontacted,
        "followups": {"overdue": overdue, "upcoming": upcoming, "meetings": meetings},
        "segments": segments,
        "recommendations": recs,
    }


def _build_prompt(facts: dict) -> str:
    kpis = "; ".join(f"{k['label']} {k['value']}{k['unit']} (target {k['target']}{k['unit']}, {k['status']})" for k in facts["kpis"])
    recs = "; ".join(r["title"] for r in facts["recommendations"])
    fu = facts["followups"]
    seq = " → ".join(f"{s['count']}" for s in facts["sequence_funnel"])
    today = datetime.utcnow().strftime("%A, %d %B %Y")
    return (
        "You are a GTM operations strategist for eSteps Health (medical-device + RPM, plus Mitus AI sports and "
        "eSteps Studio dev partnerships). Targets: reply >8%, meeting >3%, 100-150 leads/week, score>=7 = hot/MQL "
        "(24h handoff). Write a concise weekly strategy memo in markdown with four short sections: "
        "**Current state**, **Predicted risks**, **Recommended fixes**, **Top 3 focus this week**. "
        "Be specific and reference the numbers. Do not invent data. "
        "Do NOT use any placeholders like [Current Date], [TBD], or [X]. "
        f"Start the memo with a level-1 heading and the line `**Date:** {today}`.\n\n"
        f"Today is {today}.\n"
        f"KPIs vs targets: {kpis}\n"
        f"Sequence reach (E1→E5): {seq}\n"
        f"Follow-ups: {fu['overdue']} overdue, {fu['upcoming']} upcoming, {fu['meetings']} meetings\n"
        f"Hot leads: {facts['hot_leads']} total, {facts['hot_uncontacted']} never contacted\n"
        f"Rule-engine flags: {recs}\n"
    )


@router.post("/memo")
def generate_memo(
    leads_db: Session = Depends(get_leads_db),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    facts = get_insights(days=7, leads_db=leads_db, db=db, _=user)
    prompt = _build_prompt(facts)

    try:
        memo = call_gemini(prompt)
    except HTTPException:
        raise

    return {"memo": memo, "generated_at": datetime.utcnow().isoformat()}


def _facts_context(facts: dict) -> str:
    kpis = "; ".join(f"{k['label']} {k['value']}{k['unit']} (target {k['target']}{k['unit']})" for k in facts["kpis"])
    segs = "; ".join(f"{s['area']} {s['activation_pct']}%" for s in facts["segments"][:6])
    seq = ", ".join(f"E{i + 1}={s['count']}" for i, s in enumerate(facts["sequence_funnel"]))
    fu = facts["followups"]
    recs = "; ".join(r["title"] for r in facts["recommendations"])
    return (
        f"KPIs vs targets: {kpis}\n"
        f"Sequence reach: {seq}\n"
        f"Follow-ups: {fu['overdue']} overdue, {fu['upcoming']} upcoming, {fu['meetings']} meetings\n"
        f"Hot leads: {facts['hot_leads']} total, {facts['hot_uncontacted']} never contacted\n"
        f"Segment activation %: {segs}\n"
        f"Active flags: {recs}\n"
    )


class AssistantQuery(BaseModel):
    question: str


@router.post("/assistant")
def assistant(
    payload: AssistantQuery,
    leads_db: Session = Depends(get_leads_db),
    db: Session = Depends(get_db),
    user: User = Depends(require_operator),
):
    """AI Ops Assistant — burns AI budget on every call, so readonly is blocked
    per report §II.1 ('Cannot ... alter state'). Operator+ only."""
    q = (payload.question or "").strip()
    if not q:
        raise HTTPException(status_code=422, detail="Question is required")
    facts = get_insights(days=7, leads_db=leads_db, db=db, _=user)
    prompt = (
        "You are an operations analyst for eSteps Health's GTM pipeline (targets: reply >8%, meeting >3%, "
        "100-150 leads/week, score >= 7 = hot/MQL). Answer the user's question using ONLY the data below. "
        "Be concise and specific, cite the numbers, and recommend one concrete next action. If the data is "
        "insufficient, say so plainly.\n\n"
        f"DATA:\n{_facts_context(facts)}\n"
        f"QUESTION: {q}"
    )
    return {"answer": call_gemini(prompt), "generated_at": datetime.utcnow().isoformat()}


@router.get("/heatmap")
def sequence_heatmap(
    leads_db: Session = Depends(get_leads_db),
    _: User = Depends(get_current_user),
):
    """Leads reached at each sequence touch, by research area — shows where outreach goes deep vs stalls."""
    rows = leads_db.execute(text(
        "SELECT COALESCE(research_interest, 'general') AS area, count(*) AS total, "
        "count(*) FILTER (WHERE email1_sent_at IS NOT NULL) AS e1, "
        "count(*) FILTER (WHERE email2_sent_at IS NOT NULL) AS e2, "
        "count(*) FILTER (WHERE email3_sent_at IS NOT NULL) AS e3, "
        "count(*) FILTER (WHERE email4_sent_at IS NOT NULL) AS e4, "
        "count(*) FILTER (WHERE email5_sent_at IS NOT NULL) AS e5 "
        "FROM leads GROUP BY research_interest ORDER BY total DESC LIMIT 10"
    )).mappings().all()
    return {
        "steps": ["E1", "E2", "E3", "E4", "E5"],
        "areas": [
            {"area": r["area"], "total": r["total"], "steps": [r["e1"], r["e2"], r["e3"], r["e4"], r["e5"]]}
            for r in rows
        ],
    }

