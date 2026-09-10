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


class ResearchSolution(BaseModel):
    name: str
    interesting: str
    reusable: str
    fit: str = Field(pattern="^(JA|TEILWEISE|NEIN)$")
    constraint: str
    source_urls: list[str] = Field(min_length=1)


class ResearchFinding(BaseModel):
    url: str
    title: str
    finding: str
    relevance: Optional[float] = Field(None, ge=0, le=1)
    confidence: Optional[float] = Field(None, ge=0, le=1)
    license_info: Optional[str] = None


class ResearchOutput(BaseModel):
    solutions: list[ResearchSolution] = Field(min_length=3, max_length=5)
    best_practices: list[str]
    open_source_potential: str
    conclusion: str
    sources: list[ResearchFinding] = Field(min_length=1)


class ArchitectOutput(BaseModel):
    approach: str
    structure: str
    components: list[str]
    interactions: str
    technologies: list[str]
    risks: list[str]
    implementation_approach: str
    open_points: list[str]


class ChallengerOutput(ArchitectOutput):
    pass


class SynthesisExistingSolution(BaseModel):
    source_id: str
    note: str


class SynthesisOutput(BaseModel):
    approach: str
    adopted_core_elements: list[str]
    discarded_or_changed_approaches: list[str]
    structure: str
    existing_solutions_open_source: list[SynthesisExistingSolution]
    key_decisions: list[str]
    risks_open_points: list[str]
    conclusion: str


class CriticFinding(BaseModel):
    problem: str
    why_relevant: str
    recommended_change: str
    priority: str = Field(pattern="^(KRITISCH|WICHTIG|OPTIONAL)$")


class CriticOutput(BaseModel):
    status: str = Field(pattern="^(OK|ANMERKUNGEN)$")
    findings: list[CriticFinding] = Field(default_factory=list, max_length=5)


class EvaluatorRequiredChange(BaseModel):
    problem: str
    required_correction: str


class EvaluatorOutput(BaseModel):
    status: str = Field(pattern="^(PASS|REVISION_REQUIRED)$")
    reasoning: Optional[str] = None
    required_changes: list[EvaluatorRequiredChange] = Field(default_factory=list, max_length=3)


class RevisionOutput(BaseModel):
    updated_synthesis: SynthesisOutput
    changed: str = Field(pattern="^(GEÄNDERT|UNVERÄNDERT)$")


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


class ResearchSourceOut(ResearchFinding):
    id: str
    retrieved_at: str
    provider: str


class ResearchOut(BaseModel):
    solutions: list[ResearchSolution]
    best_practices: list[str]
    open_source_potential: str
    conclusion: str
    approved_at: Optional[str] = None
    sources: list[ResearchSourceOut]


class SolutionAgentOut(BaseModel):
    output: Optional[dict] = None
    run_status: str


class SynthesisOut(BaseModel):
    version: int
    output: dict
    approved_at: Optional[str] = None


class CriticOut(BaseModel):
    status: str
    findings: list[CriticFinding]


class EvaluationOut(BaseModel):
    attempt: int
    status: str
    reasoning: Optional[str] = None
    required_changes: list[EvaluatorRequiredChange]
    created_at: str


class ProjectDetail(BaseModel):
    id: str
    title: str
    workflow_state: str
    escalation_reason: Optional[str] = None
    created_at: str
    updated_at: str
    clarification_round_count: int
    research_gate_enabled: bool
    total_model_calls: int
    total_estimated_cost_usd: float
    intake: IntakeOut
    understanding: Optional[UnderstandingOut] = None
    research: Optional[ResearchOut] = None
    architect: Optional[SolutionAgentOut] = None
    challenger: Optional[SolutionAgentOut] = None
    synthesis: Optional[SynthesisOut] = None
    critic: Optional[CriticOut] = None
    evaluations: list[EvaluationOut] = Field(default_factory=list)
    last_run_status: Optional[str] = None
    # Nur im synthesis/change-request-Response gesetzt (ab Runde 3,
    # API_CONTRACT.md), NICHT generisch bei jedem GET - siehe Router.
    hint: Optional[str] = None


class ResearchRerun(BaseModel):
    comment: Optional[str] = Field(None, max_length=4000)


class SynthesisChangeRequest(BaseModel):
    comment: str = Field(..., min_length=1, max_length=4000)


class ClarificationAnswer(BaseModel):
    answers: str = Field(..., min_length=1, max_length=4000)


class EscalationResolve(BaseModel):
    action: str  # Phase 1: nur "REWORK_INTAKE" gültig (CLARIFICATION_LIMIT)


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail
