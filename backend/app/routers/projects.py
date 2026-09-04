"""
REST-Endpunkte für Phase 1, entsprechend API_CONTRACT.md, beschränkt
auf die dort für Phase 1 relevanten Routen (Projekte, Verständnis-Gate,
Klärung, Eskalation-CLARIFICATION_LIMIT, Retry). Recherche-, Synthese-
und Qualitäts-Endpunkte sind bewusst nicht enthalten - spätere Phasen.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Project, Intake, Understanding, AgentRun
from app.model_provider import call_model, ModelProviderError
from app.security import redact_secrets
from app.schemas import (
    ProjectCreate,
    ProjectSummary,
    ProjectDetail,
    IntakePatch,
    IntakeOut,
    UnderstandingOut,
    UnderstandingOutput,
    ClarificationAnswer,
    EscalationResolve,
)
from app.state_machine import (
    DRAFT,
    UNDERSTANDING,
    WAITING_FOR_USER_CLARIFICATION,
    WAITING_FOR_USER_CONFIRMATION,
    ESCALATION_REQUIRED,
    RESEARCHING,
    CLARIFICATION_LIMIT,
    InvalidTransitionError,
    require_state,
    require_escalation_reason,
    clarification_limit_reached,
)
from app.config import PROMPTS_DIR, MAX_MODEL_CALLS_PER_PROJECT, MAX_ESTIMATED_COST_PER_PROJECT_USD

router = APIRouter(prefix="/api/projects", tags=["projects"])

UNDERSTANDING_PROMPT = (PROMPTS_DIR / "understanding_v1.md").read_text(encoding="utf-8")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_project_or_404(db: Session, project_id: str) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": "Projekt nicht gefunden"}})
    return project


def _last_agent_run(db: Session, project_id: str) -> AgentRun | None:
    return (
        db.query(AgentRun)
        .filter(AgentRun.project_id == project_id)
        .order_by(AgentRun.started_at.desc())
        .first()
    )


def _check_cost_ceiling(project: Project) -> None:
    """Harte, von jedem Revisions-/Klärungszähler unabhängige Notbremse
    (API_CONTRACT.md § Kosten-Notbremse, Review 4 §4.2)."""
    if project.total_model_calls >= MAX_MODEL_CALLS_PER_PROJECT or (
        project.total_estimated_cost_usd >= MAX_ESTIMATED_COST_PER_PROJECT_USD
    ):
        raise HTTPException(
            status_code=423,
            detail={"error": {"code": "COST_LIMIT_EXCEEDED", "message": "Kosten-/Aufruf-Deckel für dieses Projekt erreicht"}},
        )


_INTAKE_FIELDS = (
    "goal",
    "problem",
    "users_structure",
    "interface_output",
    "constraints",
    "core_features",
)


def _require_complete_intake(intake: Intake) -> None:
    """Guard für POST .../submit (API_CONTRACT.md): 'alle 6 Intake-Felder
    ausgefüllt'. Projekterstellung selbst erlaubt leere Felder (leerer
    Entwurf), siehe IntakeIn in schemas.py."""
    missing = [f for f in _INTAKE_FIELDS if not getattr(intake, f).strip()]
    if missing:
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "INCOMPLETE_INTAKE",
                    "message": f"Pflichtfelder nicht ausgefüllt: {', '.join(missing)}",
                }
            },
        )


def _build_understanding_input(intake: Intake) -> str:
    return (
        f"ZIEL: {intake.goal}\n"
        f"PROBLEM: {intake.problem}\n"
        f"NUTZER/STRUKTUR: {intake.users_structure}\n"
        f"INTERFACE/AUSGABE: {intake.interface_output}\n"
        f"EINSCHRÄNKUNGEN: {intake.constraints}\n"
        f"KERNFUNKTIONEN: {intake.core_features}\n"
    )


def _run_understanding_agent(db: Session, project: Project) -> AgentRun:
    """Führt understanding_v1 aus, schreibt Ergebnis + Statuswechsel in
    EINER Transaktion (Review 4 §4.3: kein von außen sichtbarer
    Zwischenzustand). Wirft HTTPException(423) vorher, falls der
    Kostendeckel bereits erreicht ist."""
    _check_cost_ceiling(project)

    intake = db.get(Intake, project.id)
    previous_attempts = (
        db.query(AgentRun)
        .filter(AgentRun.project_id == project.id, AgentRun.role == "understanding")
        .count()
    )
    run = AgentRun(
        project_id=project.id,
        role="understanding",
        attempt=previous_attempts + 1,
        status="RUNNING",
        started_at=_now(),
        model_class="MEDIUM",
        prompt_id="understanding_v1",
    )
    db.add(run)

    try:
        result = call_model(
            role="understanding",
            model_class="MEDIUM",
            system_prompt=UNDERSTANDING_PROMPT,
            input_context=_build_understanding_input(intake),
            output_schema=UnderstandingOutput,
        )
    except ModelProviderError as exc:
        run.status = "FAILED"
        run.finished_at = _now()
        run.error = redact_secrets(str(exc))  # SECURITY.md §2 - nie ungeprüft speichern
        project.workflow_state = UNDERSTANDING
        db.commit()
        return run

    output = result.parsed

    understanding = db.get(Understanding, project.id)
    if understanding is None:
        understanding = Understanding(project_id=project.id)
        db.add(understanding)

    understanding.status = output.status.value
    understanding.summary = output.summary
    understanding.questions = json.dumps(output.questions) if output.questions else None
    understanding.contradiction_note = output.contradiction_note

    if output.status.value == "READY":
        project.workflow_state = WAITING_FOR_USER_CONFIRMATION
    else:  # CLARIFICATION_REQUIRED oder CONTRADICTION (Sub-Status, Review 1 §1.3)
        project.workflow_state = WAITING_FOR_USER_CLARIFICATION

    run.status = "DONE"
    run.finished_at = _now()
    run.provider = result.provider
    run.model = result.model
    run.token_usage_input = result.input_tokens
    run.token_usage_output = result.output_tokens
    run.estimated_cost_usd = result.estimated_cost_usd

    project.total_model_calls += 1
    project.total_estimated_cost_usd += result.estimated_cost_usd
    project.updated_at = _now()

    db.commit()
    return run


def _to_project_detail(db: Session, project: Project) -> ProjectDetail:
    intake = db.get(Intake, project.id)
    understanding = db.get(Understanding, project.id)
    last_run = _last_agent_run(db, project.id)

    understanding_out = None
    if understanding is not None:
        understanding_out = UnderstandingOut(
            status=understanding.status,
            summary=understanding.summary,
            questions=json.loads(understanding.questions) if understanding.questions else None,
            contradiction_note=understanding.contradiction_note,
            confirmed_at=understanding.confirmed_at,
        )

    return ProjectDetail(
        id=project.id,
        title=project.title,
        workflow_state=project.workflow_state,
        escalation_reason=project.escalation_reason,
        created_at=project.created_at,
        updated_at=project.updated_at,
        clarification_round_count=project.clarification_round_count,
        total_model_calls=project.total_model_calls,
        total_estimated_cost_usd=project.total_estimated_cost_usd,
        intake=IntakeOut(
            goal=intake.goal,
            problem=intake.problem,
            users_structure=intake.users_structure,
            interface_output=intake.interface_output,
            constraints=intake.constraints,
            core_features=intake.core_features,
            updated_at=intake.updated_at,
        ),
        understanding=understanding_out,
        last_run_status=last_run.status if last_run else None,
    )


@router.post("", response_model=ProjectDetail, status_code=201)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)):
    project = Project(
        title=payload.title or "Unbenanntes Projekt",
        research_gate_enabled=1 if payload.research_gate_enabled else 0,
    )
    db.add(project)
    db.flush()  # project.id verfügbar machen, ohne bereits final zu committen

    intake = Intake(
        project_id=project.id,
        goal=payload.intake.goal,
        problem=payload.intake.problem,
        users_structure=payload.intake.users_structure,
        interface_output=payload.intake.interface_output,
        constraints=payload.intake.constraints,
        core_features=payload.intake.core_features,
    )
    db.add(intake)
    db.commit()
    db.refresh(project)
    return _to_project_detail(db, project)


@router.get("", response_model=list[ProjectSummary])
def list_projects(db: Session = Depends(get_db)):
    projects = db.query(Project).order_by(Project.updated_at.desc()).all()
    return [
        ProjectSummary(id=p.id, title=p.title, workflow_state=p.workflow_state, updated_at=p.updated_at)
        for p in projects
    ]


@router.get("/{project_id}", response_model=ProjectDetail)
def get_project(project_id: str, db: Session = Depends(get_db)):
    project = _get_project_or_404(db, project_id)
    return _to_project_detail(db, project)


@router.patch("/{project_id}/intake", response_model=ProjectDetail)
def patch_intake(project_id: str, payload: IntakePatch, db: Session = Depends(get_db)):
    project = _get_project_or_404(db, project_id)
    try:
        require_state(project, DRAFT)
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail={"error": {"code": "INVALID_STATE", "message": str(exc)}})

    intake = db.get(Intake, project_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(intake, field, value)
    intake.updated_at = _now()
    project.updated_at = _now()
    db.commit()
    return _to_project_detail(db, project)


@router.post("/{project_id}/submit", response_model=ProjectDetail)
def submit_project(project_id: str, db: Session = Depends(get_db)):
    """„IDEE PRÜFEN" (Abschnitt 25) - löst understanding_v1 aus."""
    project = _get_project_or_404(db, project_id)
    try:
        require_state(project, DRAFT)
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail={"error": {"code": "INVALID_STATE", "message": str(exc)}})

    intake = db.get(Intake, project_id)
    _require_complete_intake(intake)

    project.workflow_state = UNDERSTANDING
    db.commit()

    _run_understanding_agent(db, project)
    db.refresh(project)
    return _to_project_detail(db, project)


@router.post("/{project_id}/understanding/confirm", response_model=ProjectDetail)
def confirm_understanding(project_id: str, db: Session = Depends(get_db)):
    """„RICHTIG VERSTANDEN" (Abschnitt 7)."""
    project = _get_project_or_404(db, project_id)
    try:
        require_state(project, WAITING_FOR_USER_CONFIRMATION)
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail={"error": {"code": "INVALID_STATE", "message": str(exc)}})

    understanding = db.get(Understanding, project_id)
    understanding.confirmed_at = _now()
    # Ziel-State gemäß WORKFLOW_STATES.md - Research Agent selbst ist Phase 2,
    # das Projekt "parkt" hier bis Phase 2 implementiert ist.
    project.workflow_state = RESEARCHING
    project.updated_at = _now()
    db.commit()
    return _to_project_detail(db, project)


@router.post("/{project_id}/understanding/correct", response_model=ProjectDetail)
def correct_understanding(project_id: str, db: Session = Depends(get_db)):
    """„KORRIGIEREN" (Abschnitt 7)."""
    project = _get_project_or_404(db, project_id)
    try:
        require_state(project, WAITING_FOR_USER_CONFIRMATION)
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail={"error": {"code": "INVALID_STATE", "message": str(exc)}})

    project.workflow_state = DRAFT
    project.updated_at = _now()
    db.commit()
    return _to_project_detail(db, project)


@router.post("/{project_id}/clarification", response_model=ProjectDetail)
def answer_clarification(project_id: str, payload: ClarificationAnswer, db: Session = Depends(get_db)):
    project = _get_project_or_404(db, project_id)
    try:
        require_state(project, WAITING_FOR_USER_CLARIFICATION)
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail={"error": {"code": "INVALID_STATE", "message": str(exc)}})

    project.clarification_round_count += 1

    if clarification_limit_reached(project):
        project.workflow_state = ESCALATION_REQUIRED
        project.escalation_reason = CLARIFICATION_LIMIT
        project.updated_at = _now()
        db.commit()
        return _to_project_detail(db, project)

    # Antwort in die Intake-Felder einfließen lassen: an Constraints
    # angehängt, damit understanding_v1 sie beim nächsten Lauf sieht.
    # (Phase 1 hält das bewusst simpel - eine strukturierte
    # Rückfrage-Historie ist keine Phase-1-Anforderung.)
    intake = db.get(Intake, project_id)
    intake.constraints = f"{intake.constraints}\n\nRückfrage-Antwort: {payload.answers}"
    intake.updated_at = _now()

    project.workflow_state = UNDERSTANDING
    db.commit()

    _run_understanding_agent(db, project)
    db.refresh(project)
    return _to_project_detail(db, project)


@router.post("/{project_id}/escalation/resolve", response_model=ProjectDetail)
def resolve_escalation(project_id: str, payload: EscalationResolve, db: Session = Depends(get_db)):
    project = _get_project_or_404(db, project_id)

    if payload.action != "REWORK_INTAKE":
        # RETRY_REVISION / ACCEPT_WITH_OPEN_POINTS gehören zu escalation_reason=
        # REVISION_LIMIT, der erst ab Phase 5 (Evaluator) überhaupt entstehen
        # kann - in Phase 1 immer ein Fehleingabe-Fall.
        raise HTTPException(
            status_code=422,
            detail={"error": {"code": "INVALID_ACTION", "message": "In Phase 1 ist nur 'REWORK_INTAKE' gültig"}},
        )

    try:
        require_escalation_reason(project, CLARIFICATION_LIMIT)
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail={"error": {"code": "INVALID_STATE", "message": str(exc)}})

    project.workflow_state = DRAFT
    project.escalation_reason = None
    project.clarification_round_count = 0
    project.updated_at = _now()
    db.commit()
    return _to_project_detail(db, project)


@router.post("/{project_id}/retry", response_model=ProjectDetail)
def retry_last_step(project_id: str, db: Session = Depends(get_db)):
    project = _get_project_or_404(db, project_id)
    last_run = _last_agent_run(db, project_id)
    if last_run is None or last_run.status != "FAILED":
        raise HTTPException(
            status_code=409,
            detail={"error": {"code": "NOTHING_TO_RETRY", "message": "Kein fehlgeschlagener Schritt vorhanden"}},
        )

    if last_run.role == "understanding":
        _run_understanding_agent(db, project)
        db.refresh(project)
        return _to_project_detail(db, project)

    raise HTTPException(status_code=409, detail={"error": {"code": "UNSUPPORTED_ROLE", "message": "Retry für diese Rolle ist in Phase 1 nicht implementiert"}})
