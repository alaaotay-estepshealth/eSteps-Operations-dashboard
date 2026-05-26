from datetime import date, datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel


# ─── Auth ────────────────────────────────────────────────────────────────────

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str


# ─── Overview / Global KPIs ──────────────────────────────────────────────────

class PipelineFunnelStep(BaseModel):
    label: str
    count: int
    pct: Optional[float] = None


class PriorityCount(BaseModel):
    tag: str
    count: int
    color: str


class WorkflowSummary(BaseModel):
    workflow_id: str
    name: str
    status: str
    last_run_at: Optional[datetime]
    total_runs: int
    success_count: int
    failure_count: int
    success_rate_pct: float
    avg_duration_seconds: float
    retries_today: int
    last_error: Optional[str] = None


class DashboardMetrics(BaseModel):
    # Global KPIs
    hours_saved_week: float
    leads_processed_week: int
    automation_rate_pct: float
    avg_lead_process_time_min: float
    ai_accuracy_pct: float
    human_review_queue_count: int

    # Deltas vs previous week
    delta_hours_saved: float
    delta_leads_processed: int
    delta_automation_rate: float
    delta_ai_accuracy: float

    # Pipeline
    pipeline_funnel: List[PipelineFunnelStep]
    priority_breakdown: List[PriorityCount]
    total_leads: int

    # AI summary
    ai_calls_today: int
    ai_cost_today_usd: float
    ai_budget_usd: float
    ai_confidence_avg: float

    # System
    errors_today: int
    warnings_today: int
    workflows: List[WorkflowSummary]


# ─── Workflows ───────────────────────────────────────────────────────────────

class WorkflowStatusDetail(BaseModel):
    workflow_id: str
    name: str
    status: str
    last_run_at: Optional[datetime]
    total_runs: int
    success_count: int
    failure_count: int
    success_rate_pct: float
    avg_duration_seconds: float
    retries_today: int
    last_error: Optional[str] = None
    recent_failures: List[Dict[str, Any]] = []


class ActivityEvent(BaseModel):
    type: str
    title: str
    detail: Optional[str] = None
    timestamp: datetime
    status: Optional[str] = None


class SystemHealthDot(BaseModel):
    slug: str
    name: str
    status: str
    last_run_ago: Optional[str] = None


class AlertItem(BaseModel):
    severity: str          # error | warning | info
    type: str              # workflow_failures | review_pending | sla_breach | budget
    message: str
    count: int
    link: Optional[str] = None   # frontend route to resolve it


class DailyExecutionPoint(BaseModel):
    date: str
    workflow_id: str
    workflow_name: str
    executions: int
    successes: int
    failures: int


# ─── AI ──────────────────────────────────────────────────────────────────────

class AIDecision(BaseModel):
    id: UUID
    created_at: datetime
    request_type: str
    workflow_source: Optional[str]
    provider: str
    model: Optional[str]
    tokens_used: Optional[int]
    cost_usd: Optional[float]
    latency_ms: Optional[int]
    confidence_score: Optional[float]
    used_fallback: bool
    fallback_reason: Optional[str]
    human_verified: bool
    human_override: bool
    status: str
    input_preview: Optional[str]

    class Config:
        from_attributes = True


class ConfidenceBucket(BaseModel):
    bucket: str
    count: int
    color: str


class AITypeBreakdown(BaseModel):
    request_type: str
    count: int
    avg_confidence: float
    avg_cost_usd: float


class AIStats(BaseModel):
    calls_today: int
    cost_today_usd: float
    budget_usd: float
    budget_pct_used: float
    avg_confidence: float
    fallback_rate_pct: float
    accuracy_pct: float
    pending_review: int
    confidence_buckets: List[ConfidenceBucket]
    type_breakdown: List[AITypeBreakdown]
    decisions: List[AIDecision]


# ─── Logs ────────────────────────────────────────────────────────────────────

class LogEntry(BaseModel):
    id: UUID
    created_at: datetime
    level: str
    source: str
    message: str
    correlation_id: Optional[str]
    duration_ms: Optional[int]

    class Config:
        from_attributes = True


class LogStats(BaseModel):
    errors_today: int
    warnings_today: int
    info_today: int
    error_rate_pct: float
    logs: List[LogEntry]


# ─── Pipeline ─────────────────────────────────────────────────────────────────

class LeadRow(BaseModel):
    id: Optional[UUID] = None
    lead_id: Optional[str]
    first_name: Optional[str]
    last_name: Optional[str]
    institution: Optional[str]
    research_interest: Optional[str]
    campaign_tag: Optional[str]
    lead_score: int
    stage: str
    touch_number: int
    reply_received: bool
    ab_variant: Optional[str]
    ai_classified: bool
    human_verified: bool
    next_send_date: Optional[date] = None

    class Config:
        from_attributes = True


class LeadActionRequest(BaseModel):
    action: str                    # pause | resume | mark_cold | set_priority
    value: Optional[str] = None    # set_priority → Priority_A | Priority_B | Priority_C


class ResearchAreaStats(BaseModel):
    research_interest: str
    total: int
    contacted: int
    replied: int
    meetings: int
    reply_rate_pct: float


class ABComparison(BaseModel):
    variant_a_sent: int
    variant_b_sent: int
    variant_a_open_rate: float
    variant_b_open_rate: float
    winner: Optional[str]


# ─── Human Review ────────────────────────────────────────────────────────────

class ReviewItem(BaseModel):
    id: UUID
    created_at: datetime
    request_type: str
    input_preview: Optional[str]
    confidence_score: Optional[float]
    age_hours: float
    sla_breach: bool

    class Config:
        from_attributes = True


class ReviewResolution(BaseModel):
    action: str   # approve | override | reject
    corrected_output: Optional[Dict[str, Any]] = None
    reviewer_notes: Optional[str] = None


# ─── Email Logs ──────────────────────────────────────────────────────────────

class EmailLogRow(BaseModel):
    id: UUID
    created_at: datetime
    lead_id: UUID
    lead_name: Optional[str] = None
    sequence_step: int
    ab_variant: Optional[str]
    email_status: str
    open_detected: bool
    sent_at: Optional[datetime]
    subject: Optional[str]
    provider: Optional[str]
    bounce_reason: Optional[str]

    class Config:
        from_attributes = True


class EmailStepMetrics(BaseModel):
    step: int
    sent: int
    delivered: int
    bounced: int
    opened: int
    delivery_rate_pct: float
    open_rate_pct: float


class EmailStats(BaseModel):
    total_sent: int
    total_delivered: int
    total_bounced: int
    total_opened: int
    delivery_rate_pct: float
    open_rate_pct: float
    bounce_rate_pct: float
    step_metrics: List[EmailStepMetrics]
    ab_comparison: Optional[ABComparison] = None


class PaginatedEmailLogs(BaseModel):
    total: int
    offset: int
    limit: int
    logs: List[EmailLogRow]


# ─── Bookings ────────────────────────────────────────────────────────────────

class BookingRow(BaseModel):
    id: UUID
    created_at: datetime
    lead_name: Optional[str] = None
    institution: Optional[str] = None
    status: str
    scheduled_for: Optional[datetime]
    completed_at: Optional[datetime]
    canceled_at: Optional[datetime]
    no_show_detected: bool
    source: Optional[str]

    class Config:
        from_attributes = True


class BookingStats(BaseModel):
    total: int
    upcoming: int
    completed: int
    canceled: int
    no_shows: int
    no_show_rate_pct: float
    completion_rate_pct: float


class PaginatedBookings(BaseModel):
    total: int
    offset: int
    limit: int
    bookings: List[BookingRow]


# ─── Opportunities ───────────────────────────────────────────────────────────

class OpportunityRow(BaseModel):
    id: UUID
    created_at: datetime
    lead_name: Optional[str] = None
    institution: Optional[str] = None
    stage: str
    partnership_tier: Optional[str]
    deal_value_usd: Optional[float]
    expected_close_date: Optional[datetime]
    closed_at: Optional[datetime]
    notes: Optional[str]

    class Config:
        from_attributes = True


class OpportunityStageSummary(BaseModel):
    stage: str
    count: int
    total_value_usd: float


class OpportunityTierSummary(BaseModel):
    tier: str
    count: int
    avg_deal_value_usd: float
    total_value_usd: float


class OpportunityStats(BaseModel):
    total_pipeline_value: float
    won_value: float
    active_deals: int
    avg_deal_value: float
    stages: List[OpportunityStageSummary]
    tiers: List[OpportunityTierSummary]


class PaginatedOpportunities(BaseModel):
    total: int
    offset: int
    limit: int
    opportunities: List[OpportunityRow]


# ─── Tickets ─────────────────────────────────────────────────────────────────

class TicketRow(BaseModel):
    id: UUID
    created_at: datetime
    source: str
    subject: str
    body_preview: Optional[str]
    ai_category: str
    ai_priority_score: int
    ai_confidence: float
    assigned_to: str
    status: str
    resolved_at: Optional[datetime]
    response_time_min: Optional[float]
    human_verified: bool

    class Config:
        from_attributes = True


class TicketCategoryBreakdown(BaseModel):
    category: str
    count: int
    avg_priority: float
    avg_confidence: float


class TicketStats(BaseModel):
    open_count: int
    in_progress_count: int
    resolved_count: int
    avg_response_time_min: Optional[float]
    avg_ai_confidence: float
    human_verification_rate_pct: float
    categories: List[TicketCategoryBreakdown]


class PaginatedTickets(BaseModel):
    total: int
    offset: int
    limit: int
    tickets: List[TicketRow]


class TicketStatusUpdate(BaseModel):
    status: str
    assigned_to: Optional[str] = None


# ─── GTM Strategy ────────────────────────────────────────────────────────────

class StrategyFile(BaseModel):
    name: str
    directory: str
    path: str
    modified_at: Optional[datetime] = None
    size_bytes: int = 0


class StrategyContent(BaseModel):
    path: str
    name: str
    content: str


# ─── Pipeline Paginated ──────────────────────────────────────────────────────

class PaginatedLeads(BaseModel):
    total: int
    offset: int
    limit: int
    leads: List[LeadRow]


# ─── Webhook ─────────────────────────────────────────────────────────────────

class N8NCallbackPayload(BaseModel):
    workflow_id: str
    workflow_name: str
    execution_id: str
    status: str            # success | failed | retrying
    duration_seconds: Optional[float] = None
    error_message: Optional[str] = None
    error_type: Optional[str] = None
    correlation_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class AIDecisionIngest(BaseModel):
    # Identity of the decision being recorded
    request_type: str                              # lead_classify | email_summarize | priority_score | draft_reply | chatbot_reply
    workflow_source: Optional[str] = None          # e.g. "EST-3: Reply Handler"
    decision_id: Optional[str] = None              # idempotency key (n8n execution/item id)
    entity_id: Optional[UUID] = None               # lead/ticket this decision is about
    entity_type: Optional[str] = None              # lead | ticket

    # Provider/cost telemetry
    provider: str = "gemini"                       # gemini | openai | grok
    model: Optional[str] = None
    tokens_used: Optional[int] = None
    cost_usd: Optional[float] = None
    latency_ms: Optional[int] = None

    # The decision itself
    input_preview: Optional[str] = None            # truncated to 200 chars server-side
    ai_output: Optional[Dict[str, Any]] = None
    confidence_score: Optional[float] = None        # 0.0–1.0

    # Safety / routing
    used_fallback: bool = False
    fallback_reason: Optional[str] = None
    status: Optional[str] = None                    # omit → auto: <0.70 conf routes to pending_review
