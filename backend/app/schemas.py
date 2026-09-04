"""
Pydantic-Schemas: sowohl das Agenten-Output-Schema (AGENT_PROMPTS.md
§ understanding_v1) als auch die REST-Request/Response-Modelle
(API_CONTRACT.md), soweit sie zu Phase 1 gehören.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# --- Agenten-Output-Schema (AGENT_PROMPTS.md § understanding_v1) ----------


class UnderstandingStatus(str, Enum):
    READY = "READY"
    CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"
    CONTRADICTION = "CONTRADICTION"


class UnderstandingOutput(BaseModel):
    status: UnderstandingStatus
    summary: Optional[str] = None
    questions: Optional[list[str]] = None
    contradiction_note: Optional[str] = None


# --- API: Intake (Abschnitt 3) ---------------------------------------------


class IntakeIn(BaseModel):
    """Erlaubt bewusst leere Felder bei der Projekterstellung (ein Projekt
    kann als leerer Entwurf angelegt und die sechs Boxen anschließend über
    PATCH gefüllt werden). Die Vollständigkeitsprüfung ("alle 6 Felder
    ausgefüllt") ist laut API_CONTRACT.md ein Guard von POST .../submit,
    nicht der Projekterstellung selbst - siehe `_require_complete_intake`
    in routers/projects.py."""

    goal: str = Field("", max_length=4000)
    problem: str = Field("", max_length=4000)
    users_structure: str = Field("", max_length=4000)
    interface_output: str = Field("", max_length=4000)
    constraints: str = Field("", max_length=4000)
    core_features: str = Field("", max_length=4000)


class IntakePatch(BaseModel):
    goal: Optional[str] = Field(None, min_length=1, max_length=4000)
    problem: Optional[str] = Field(None, min_length=1, max_length=4000)
    users_structure: Optional[str] = Field(None, min_length=1, max_length=4000)
    interface_output: Optional[str] = Field(None, min_length=1, max_length=4000)
    constraints: Optional[str] = Field(None, min_length=1, max_length=4000)
    core_features: Optional[str] = Field(None, min_length=1, max_length=4000)


class IntakeOut(IntakeIn):
    updated_at: str


class ProjectCreate(BaseModel):
    title: Optional[str] = None
    intake: IntakeIn
    research_gate_enabled: bool = False


class ProjectSummary(BaseModel):
    id: str
    title: str
    workflow_state: str
    updated_at: str


class UnderstandingOut(BaseModel):
    status: Optional[str] = None
    summary: Optional[str] = None
    questions: Optional[list[str]] = None
    contradiction_note: Optional[str] = None
    confirmed_at: Optional[str] = None


class ProjectDetail(BaseModel):
    id: str
    title: str
    workflow_state: str
    escalation_reason: Optional[str] = None
    created_at: str
    updated_at: str
    clarification_round_count: int
    total_model_calls: int
    total_estimated_cost_usd: float
    intake: IntakeOut
    understanding: Optional[UnderstandingOut] = None
    last_run_status: Optional[str] = None


class ClarificationAnswer(BaseModel):
    answers: str = Field(..., min_length=1, max_length=4000)


class EscalationResolve(BaseModel):
    action: str  # Phase 1: nur "REWORK_INTAKE" gültig (CLARIFICATION_LIMIT)


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail
