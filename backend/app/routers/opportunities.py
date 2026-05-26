from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_leads_db
from app.models.user import User
from app.schemas.responses import (
    OpportunityRow,
    OpportunityStats,
    OpportunityStageSummary,
    OpportunityTierSummary,
    PaginatedOpportunities,
)

router = APIRouter(prefix="/admin/opportunities", tags=["opportunities"])

STAGE_ORDER = ["meeting_booked", "meeting_held", "proposal_sent", "pilot_active",
               "closed_won", "closed_lost"]


@router.get("/stats", response_model=OpportunityStats)
def get_opportunity_stats(
    db: Session = Depends(get_leads_db),
    _: User = Depends(get_current_user),
):
    # Combine: opportunities table + leads at call_requested/pitching stage (pipeline)
    # Real opportunities from DB
    opp_count = db.execute(text("SELECT COUNT(*) FROM opportunities")).scalar() or 0
    pipeline_val = db.execute(text(
        "SELECT COALESCE(SUM(deal_value_usd), 0) FROM opportunities WHERE stage != 'closed_lost'"
    )).scalar() or 0
    won_val = db.execute(text(
        "SELECT COALESCE(SUM(deal_value_usd), 0) FROM opportunities WHERE stage = 'closed_won'"
    )).scalar() or 0

    # Leads at advanced stages = potential deals
    advanced = db.execute(text(
        "SELECT COUNT(*) FROM leads WHERE stage IN ('call_requested', 'pitching') AND lead_score >= 7"
    )).scalar() or 0

    # Conversations with positive intent = warm opportunities
    warm = db.execute(text(
        "SELECT COUNT(*) FROM conversations WHERE direction = 'inbound' "
        "AND (body ILIKE '%collaboration%' OR body ILIKE '%happy to%' "
        "OR body ILIKE '%interested%' OR body ILIKE '%discuss%')"
    )).scalar() or 0

    active_deals = opp_count + warm
    avg_deal = 15000.0 if opp_count == 0 else float(pipeline_val) / max(opp_count, 1)

    # Stage breakdown
    stages = []
    if opp_count > 0:
        stage_rows = db.execute(text(
            "SELECT stage, COUNT(*) as cnt, COALESCE(SUM(deal_value_usd), 0) as val "
            "FROM opportunities GROUP BY stage"
        )).fetchall()
        stages = [
            OpportunityStageSummary(stage=r.stage, count=r.cnt, total_value_usd=round(float(r.val), 2))
            for r in stage_rows
        ]

    # Add derived stages from leads
    stages.append(OpportunityStageSummary(
        stage="qualified_lead", count=advanced,
        total_value_usd=round(advanced * 15000, 2),
    ))
    stages.append(OpportunityStageSummary(
        stage="warm_reply", count=warm,
        total_value_usd=round(warm * 10000, 2),
    ))

    estimated_pipeline = float(pipeline_val) + advanced * 15000 + warm * 10000

    # Tier breakdown
    tiers = []
    tier_rows = db.execute(text(
        "SELECT partnership_tier, COUNT(*) as cnt, "
        "COALESCE(AVG(deal_value_usd), 0) as avg_val, "
        "COALESCE(SUM(deal_value_usd), 0) as total_val "
        "FROM opportunities WHERE partnership_tier IS NOT NULL "
        "GROUP BY partnership_tier"
    )).fetchall()
    tiers = [
        OpportunityTierSummary(
            tier=r.partnership_tier, count=r.cnt,
            avg_deal_value_usd=round(float(r.avg_val), 2),
            total_value_usd=round(float(r.total_val), 2),
        )
        for r in tier_rows
    ]

    # Add lead-derived tiers based on campaign_tag
    for tag, tier_name in [("Priority_A", "strategic_partner"), ("Priority_B", "research_partner")]:
        cnt = db.execute(text(
            "SELECT COUNT(*) FROM leads WHERE campaign_tag = :tag AND stage IN ('call_requested','pitching') AND lead_score >= 7"
        ), {"tag": tag}).scalar() or 0
        if cnt > 0:
            tiers.append(OpportunityTierSummary(
                tier=tier_name, count=cnt,
                avg_deal_value_usd=15000.0 if tag == "Priority_A" else 10000.0,
                total_value_usd=cnt * (15000.0 if tag == "Priority_A" else 10000.0),
            ))

    return OpportunityStats(
        total_pipeline_value=round(estimated_pipeline, 2),
        won_value=round(float(won_val), 2),
        active_deals=active_deals,
        avg_deal_value=round(avg_deal, 2),
        stages=stages,
        tiers=tiers,
    )


@router.get("", response_model=PaginatedOpportunities)
def list_opportunities(
    stage: Optional[str] = Query(None),
    partnership_tier: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_leads_db),
    _: User = Depends(get_current_user),
):
    parts = []

    # Real opportunities
    parts.append(
        "SELECT o.id, o.created_at, "
        "COALESCE(CONCAT(l.first_name, ' ', l.last_name), o.assigned_to) as lead_name, "
        "l.institution, o.stage, o.partnership_tier, o.deal_value_usd, "
        "o.expected_close_date::timestamptz as expected_close_date, "
        "NULL::timestamptz as closed_at, o.notes "
        "FROM opportunities o LEFT JOIN leads l ON o.lead_id = l.id"
    )

    # Conversations with positive intent → warm opportunities
    parts.append(
        "SELECT c.id, c.created_at, "
        "CONCAT(l.first_name, ' ', l.last_name) as lead_name, "
        "l.institution, 'warm_reply' as stage, "
        "CASE WHEN l.campaign_tag = 'Priority_A' THEN 'strategic_partner' "
        "     ELSE 'research_partner' END as partnership_tier, "
        "NULL::numeric as deal_value_usd, "
        "NULL::timestamptz as expected_close_date, "
        "NULL::timestamptz as closed_at, "
        "LEFT(c.body, 200) as notes "
        "FROM conversations c JOIN leads l ON c.lead_id = l.id "
        "WHERE c.direction = 'inbound'"
    )

    union_sql = " UNION ALL ".join(parts)

    filters = []
    params: dict = {"limit": limit, "offset": offset}
    if stage:
        filters.append("stage = :stage")
        params["stage"] = stage
    if partnership_tier:
        filters.append("partnership_tier = :partnership_tier")
        params["partnership_tier"] = partnership_tier
    where = ("WHERE " + " AND ".join(filters)) if filters else ""

    total = db.execute(text(
        f"SELECT COUNT(*) FROM ({union_sql}) sub {where}"
    ), params).scalar() or 0

    rows = db.execute(text(
        f"SELECT * FROM ({union_sql}) sub {where} "
        f"ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
    ), params).mappings().all()

    opportunities = [
        OpportunityRow(
            id=r["id"], created_at=r["created_at"],
            lead_name=r["lead_name"], institution=r["institution"],
            stage=r["stage"], partnership_tier=r["partnership_tier"],
            deal_value_usd=float(r["deal_value_usd"]) if r["deal_value_usd"] else None,
            expected_close_date=r["expected_close_date"],
            closed_at=r["closed_at"], notes=r["notes"],
        )
        for r in rows
    ]
    return PaginatedOpportunities(total=total, offset=offset, limit=limit, opportunities=opportunities)
