"""
ORM-Modelle für Phase 1-5 (DATA_MODEL.md): projects, intake,
understanding, research, research_sources, architect, challenger,
synthesis, critic, evaluations, revisions und agent_runs. `final` wird
bewusst NICHT hier definiert - das gehört zu Phase 6 und wird erst dort
ergänzt, um keine Phasen vorwegzunehmen.
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


class Research(Base):
    __tablename__ = "research"

    project_id = Column(String, ForeignKey("projects.id"), primary_key=True)
    solutions = Column(Text, nullable=False)
    best_practices = Column(Text, nullable=False)
    open_source_potential = Column(Text, nullable=False)
    conclusion = Column(Text, nullable=False)
    approved_at = Column(String, nullable=True)


class ResearchSource(Base):
    __tablename__ = "research_sources"

    id = Column(String, primary_key=True, default=_uuid)
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    agent_run_id = Column(String, ForeignKey("agent_runs.id"), nullable=False)
    url = Column(Text, nullable=False)
    title = Column(Text, nullable=False)
    finding = Column(Text, nullable=False)
    relevance = Column(Float, nullable=True)
    confidence = Column(Float, nullable=True)
    license_info = Column(Text, nullable=True)
    retrieved_at = Column(String, nullable=False)
    provider = Column(String, nullable=False)
    referenced_by_synthesis = Column(Integer, nullable=False, default=0)


class Architect(Base):
    __tablename__ = "architect"

    project_id = Column(String, ForeignKey("projects.id"), primary_key=True)
    output = Column(Text, nullable=True)
    run_status = Column(String, nullable=False, default="PENDING")


class Challenger(Base):
    __tablename__ = "challenger"

    project_id = Column(String, ForeignKey("projects.id"), primary_key=True)
    output = Column(Text, nullable=True)
    run_status = Column(String, nullable=False, default="PENDING")


class Synthesis(Base):
    """Multi-Versionen-Tabelle (nicht Single-Row wie Architect/Challenger):
    jede ÄNDERUNGSWUNSCH-Runde erzeugt eine neue Zeile statt die vorherige
    zu überschreiben (AT-4.2). Nur version = MAX(version) je project_id ist
    aktuell gültig (DATA_MODEL.md)."""

    __tablename__ = "synthesis"

    project_id = Column(String, ForeignKey("projects.id"), primary_key=True)
    version = Column(Integer, primary_key=True)
    output = Column(Text, nullable=False)
    approved_at = Column(String, nullable=True)


class Critic(Base):
    """Ein Critic-Lauf je freigegebener Synthese-Version (DATA_MODEL.md,
    PK (project_id, synthesis_version)) - critic_v1 läuft genau einmal pro
    synthesis/approve, nie erneut innerhalb derselben Revisionsschleife
    (AT-5.5). Nur bei Erfolg angelegt, wie bei `Synthesis` (kein
    Platzhalter bei FAILED)."""

    __tablename__ = "critic"

    project_id = Column(String, ForeignKey("projects.id"), primary_key=True)
    synthesis_version = Column(Integer, primary_key=True)
    status = Column(String, nullable=False)  # OK | ANMERKUNGEN
    findings = Column(Text, nullable=False)  # JSON-Array, max. 5 Einträge


class Evaluation(Base):
    """Eine Zeile je evaluator_v1-Lauf (mehrere je Projekt möglich - vor
    und nach jeder Revision, daher eigene id statt project_id als PK)."""

    __tablename__ = "evaluations"

    id = Column(String, primary_key=True, default=_uuid)
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    attempt = Column(Integer, nullable=False)  # = revision_count zum Zeitpunkt der Prüfung
    status = Column(String, nullable=False)  # PASS | REVISION_REQUIRED
    reasoning = Column(Text, nullable=True)
    required_changes = Column(Text, nullable=True)  # JSON-Array, max. 3 Einträge
    created_at = Column(String, nullable=False, default=_now)


class Revision(Base):
    """Eine Zeile je revision_v1-Lauf. `updated_synthesis` trägt die
    korrigierte Synthese-Struktur separat von der `synthesis`-Tabelle -
    die dort freigegebene Version bleibt unverändert, die Revisionsschicht
    liegt logisch darüber (nur die jeweils letzte Revision ist für
    Evaluator/Final Builder maßgeblich, siehe routers/projects.py
    `_current_synthesis_content`)."""

    __tablename__ = "revisions"

    id = Column(String, primary_key=True, default=_uuid)
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    number = Column(Integer, nullable=False)  # 1 oder 2, siehe MAX_INTERNAL_REVISIONS
    evaluation_id = Column(String, ForeignKey("evaluations.id"), nullable=False)
    updated_synthesis = Column(Text, nullable=False)  # JSON
    changed = Column(String, nullable=False)  # GEÄNDERT | UNVERÄNDERT
    created_at = Column(String, nullable=False, default=_now)


class AgentRun(Base):
    """Audit- und Fortschritts-Tabelle (ADR-010)."""

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
