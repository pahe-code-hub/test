"""
ORM-Modelle für Phase 1 (DATA_MODEL.md): projects, intake,
understanding, agent_runs. Weitere Tabellen (research, architect,
challenger, synthesis, critic, evaluations, revisions, final,
research_sources) sind bewusst NICHT hier definiert - sie gehören zu
späteren Phasen (Phase 2-6) und werden erst dort ergänzt, um keine
Phasen vorwegzunehmen.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Integer, Float, Text, ForeignKey

from app.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Project(Base):
    __tablename__ = "projects"

    id = Column(String, primary_key=True, default=_uuid)
    title = Column(String, nullable=False, default="Unbenanntes Projekt")
    created_at = Column(String, nullable=False, default=_now)
    updated_at = Column(String, nullable=False, default=_now)

    # WORKFLOW_STATES.md - Phase 1 nutzt: DRAFT, UNDERSTANDING,
    # WAITING_FOR_USER_CLARIFICATION, WAITING_FOR_USER_CONFIRMATION,
    # ESCALATION_REQUIRED, RESEARCHING (nur als Zielzustand nach
    # Bestätigung - Research Agent selbst ist Phase 2).
    workflow_state = Column(String, nullable=False, default="DRAFT")
    escalation_reason = Column(String, nullable=True)  # CLARIFICATION_LIMIT | REVISION_LIMIT

    research_gate_enabled = Column(Integer, nullable=False, default=0)

    clarification_round_count = Column(Integer, nullable=False, default=0)
    synthesis_revision_count = Column(Integer, nullable=False, default=0)
    revision_count = Column(Integer, nullable=False, default=0)

    total_model_calls = Column(Integer, nullable=False, default=0)
    total_estimated_cost_usd = Column(Float, nullable=False, default=0.0)


class Intake(Base):
    __tablename__ = "intake"

    project_id = Column(String, ForeignKey("projects.id"), primary_key=True)
    goal = Column(Text, nullable=False, default="")
    problem = Column(Text, nullable=False, default="")
    users_structure = Column(Text, nullable=False, default="")
    interface_output = Column(Text, nullable=False, default="")
    constraints = Column(Text, nullable=False, default="")
    core_features = Column(Text, nullable=False, default="")
    updated_at = Column(String, nullable=False, default=_now)


class Understanding(Base):
    __tablename__ = "understanding"

    project_id = Column(String, ForeignKey("projects.id"), primary_key=True)
    status = Column(String, nullable=True)  # READY | CLARIFICATION_REQUIRED | CONTRADICTION
    summary = Column(Text, nullable=True)
    questions = Column(Text, nullable=True)  # JSON-Array als TEXT
    contradiction_note = Column(Text, nullable=True)
    confirmed_at = Column(String, nullable=True)


class AgentRun(Base):
    """Audit- und Fortschritts-Tabelle (ADR-010) - für Phase 1 nur role='understanding'."""

    __tablename__ = "agent_runs"

    id = Column(String, primary_key=True, default=_uuid)
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    role = Column(String, nullable=False)
    attempt = Column(Integer, nullable=False, default=1)
    status = Column(String, nullable=False, default="RUNNING")  # RUNNING | DONE | FAILED
    started_at = Column(String, nullable=True)
    finished_at = Column(String, nullable=True)
    provider = Column(String, nullable=True)
    model = Column(String, nullable=True)
    model_class = Column(String, nullable=True)
    prompt_id = Column(String, nullable=True)
    error = Column(Text, nullable=True)
    token_usage_input = Column(Integer, nullable=True)
    token_usage_output = Column(Integer, nullable=True)
    estimated_cost_usd = Column(Float, nullable=True)
