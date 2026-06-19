"""Pydantic schemas for the GTM plan endpoints + the Anthropic JSONB output.

Mirrors the spec at docs/superpowers/specs/2026-06-07-gtm-strategy-ingest-design.md.
"""
from datetime import datetime
from typing import List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ── Anthropic output shape (validated on response.text) ───────────────────────

class KpiTarget(BaseModel):
    period: Literal["30d", "60d", "90d"]
    objective: str
    target: Optional[float] = None
    unit: Optional[str] = None
    rationale: str
    assignee_label: Optional[str] = None


class RiskFlag(BaseModel):
    label: str
    severity: Literal["low", "medium", "high"]
    source: Optional[str] = None


class SourceFile(BaseModel):
    name: str
    path: str
    tokens: int = Field(ge=0)


class GtmAiOutput(BaseModel):
    model_config = ConfigDict(extra="allow")
    executive_summary: str
    kpi_targets: List[KpiTarget]
    risk_flags: List[RiskFlag]
    recommended_focus: List[str]
    source_files: List[SourceFile]


# ── API response shapes ──────────────────────────────────────────────────────

class GtmPlanResponse(BaseModel):
    ai_request_id: Optional[UUID] = None
    generated_at: Optional[datetime] = None
    age_seconds: Optional[int] = None
    status: str  # 'none' | 'completed' | 'rejected' | 'running'
    output: Optional[GtmAiOutput] = None
    error_message: Optional[str] = None


class InitiativeRow(BaseModel):
    id: UUID
    period: str
    objective_label: str
    target_value: Optional[float]
    target_unit: Optional[str]
    rationale: Optional[str]
    assignee_label: Optional[str]
    assignee_user_id: Optional[UUID]
    assignee_display: Optional[str]
    due_at: Optional[datetime]
    status: str
    created_at: datetime
    applied_at: Optional[datetime]


class GenerateRequest(BaseModel):
    force: bool = False


class GenerateAccepted(BaseModel):
    execution_id: str
    status: Literal["queued", "in_flight"]


class AssignRequest(BaseModel):
    user_id: Optional[UUID] = None


class CalendarItem(BaseModel):
    id: UUID
    label: str
    due_at: datetime
    period: str
    status: str
    assignee_display: Optional[str]
