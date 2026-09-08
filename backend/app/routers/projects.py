"""
REST-Endpunkte für Phase 1-3 entsprechend API_CONTRACT.md: Intake,
Understanding, Research und parallele Architect-/Challenger-Läufe.
Synthesizer und Qualitätsrollen sind bewusst nicht enthalten.
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import update
from sqlalchemy.orm import Session, sessionmaker

from app.database import get_db
from app.models import (
    Project, Intake, Understanding, Research, ResearchSource,
    Architect, Challenger, AgentRun,
)
from app.model_provider import call_model, ModelProviderError
from app.research_provider import TavilyResearchProvider, ResearchProviderError
from app.external_data import wrap_external_research_data
from app.security import redact_secrets
from app.schemas import (
    ProjectCreate,
    ProjectSummary,
    ProjectDetail,
    IntakePatch,
    IntakeOut,
    UnderstandingOut,
    UnderstandingOutput,
    ResearchOutput,
    ResearchOut,
    ResearchSourceOut,
    ResearchRerun,
    ArchitectOutput,
    ChallengerOutput,
    SolutionAgentOut,
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
    WAITING_FOR_RESEARCH_APPROVAL,
    GENERATING_SOLUTIONS,
    SYNTHESIZING,
    CLARIFICATION_LIMIT,
    InvalidTransitionError,
    require_state,
    require_escalation_reason,
    clarification_limit_reached,
)
from app.config import (
    PROMPTS_DIR, MAX_MODEL_CALLS_PER_PROJECT,
    MAX_ESTIMATED_COST_PER_PROJECT_USD, RESEARCH_MAX_SOURCES,
)

router = APIRouter(prefix="/api/projects", tags=["projects"])

UNDERSTANDING_PROMPT = (PROMPTS_DIR / "understanding_v1.md").read_text(encoding="utf-8")
RESEARCH_PROMPT = (PROMPTS_DIR / "research_v1.md").read_text(encoding="utf-8")
ARCHITECT_PROMPT = (PROMPTS_DIR / "architect_v1.md").read_text(encoding="utf-8")
CHALLENGER_PROMPT = (PROMPTS_DIR / "challenger_v1.md").read_text(encoding="utf-8")


def _research_provider():
    return TavilyResearchProvider()


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


def _run_research_agent(db: Session, project: Project, comment: str | None = None) -> AgentRun:
    """Search → Auswahl → Extract → research_v1, atomar persistiert."""
    _check_cost_ceiling(project)
    intake = db.get(Intake, project.id)
    understanding = db.get(Understanding, project.id)
    attempts = db.query(AgentRun).filter(
        AgentRun.project_id == project.id, AgentRun.role == "research"
    ).count()
    run = AgentRun(
        project_id=project.id, role="research", attempt=attempts + 1,
        status="RUNNING", started_at=_now(), model_class="MEDIUM",
        prompt_id="research_v1",
    )
    db.add(run)
    db.flush()

    try:
        provider = _research_provider()
        requirements = _build_understanding_input(intake)
        if comment:
            requirements += f"\nANMERKUNG ZUR NEUEN RECHERCHE: {comment}\n"
        policy = "Offizielle Dokumentation, Standards und offizielle Repositories priorisieren."
        queries = (
            f"bestehende Softwarelösungen für {intake.goal}",
            f"open source GitHub {intake.goal} {intake.core_features}",
            f"offizielle Dokumentation Best Practices {intake.problem}",
        )
        hits_by_url = {}
        for query in queries:
            for hit in provider.search(query, requirements, policy):
                hits_by_url.setdefault(hit.url, hit)
        selected_urls = list(hits_by_url)[:RESEARCH_MAX_SOURCES]
        pages = provider.extract(selected_urls)
        pages_by_url = {page.url: page for page in pages}
        if not pages_by_url:
            raise ResearchProviderError("Tavily Extract lieferte keine verwertbare Quelle")

        external = [
            {
                "url": page.url,
                "title": hits_by_url[page.url].title if page.url in hits_by_url else page.url,
                "search_snippet": hits_by_url[page.url].snippet if page.url in hits_by_url else "",
                "content": page.content,
            }
            for page in pages
        ]
        context = (
            requirements
            + "\nBESTÄTIGTES VERSTÄNDNIS: "
            + (understanding.summary or "")
            + "\n\n"
            + wrap_external_research_data(external)
        )
        result = call_model(
            role="research", model_class="MEDIUM", system_prompt=RESEARCH_PROMPT,
            input_context=context, output_schema=ResearchOutput,
        )
        output = result.parsed
        extracted_urls = set(pages_by_url)
        finding_urls = {source.url for source in output.sources}
        if not finding_urls <= extracted_urls:
            raise ModelProviderError("research_v1 referenziert eine nicht extrahierte Quelle")
        if any(not set(solution.source_urls) <= finding_urls for solution in output.solutions):
            raise ModelProviderError("research_v1 lieferte eine Lösung ohne extrahierten Quellenbeleg")

        research = db.get(Research, project.id) or Research(project_id=project.id)
        db.add(research)
        research.solutions = json.dumps([x.model_dump() for x in output.solutions], ensure_ascii=False)
        research.best_practices = json.dumps(output.best_practices, ensure_ascii=False)
        research.open_source_potential = output.open_source_potential
        research.conclusion = output.conclusion
        research.approved_at = None
        for source in output.sources:
            page = pages_by_url[source.url]
            db.add(ResearchSource(
                project_id=project.id, agent_run_id=run.id, url=source.url,
                title=(hits_by_url[source.url].title if source.url in hits_by_url else source.title),
                finding=source.finding,
                relevance=source.relevance, confidence=source.confidence,
                license_info=source.license_info, retrieved_at=page.retrieved_at,
                provider="tavily",
            ))

        run.status = "DONE"
        run.finished_at = _now()
        run.provider = result.provider
        run.model = result.model
        run.token_usage_input = result.input_tokens
        run.token_usage_output = result.output_tokens
        run.estimated_cost_usd = result.estimated_cost_usd
        project.total_model_calls += 1
        project.total_estimated_cost_usd += result.estimated_cost_usd
        project.workflow_state = (
            WAITING_FOR_RESEARCH_APPROVAL
            if project.research_gate_enabled else GENERATING_SOLUTIONS
        )
        project.updated_at = _now()
    except (ResearchProviderError, ModelProviderError) as exc:
        run.status = "FAILED"
        run.finished_at = _now()
        run.error = redact_secrets(str(exc))
        project.workflow_state = RESEARCHING

    db.commit()
    if project.workflow_state == GENERATING_SOLUTIONS:
        _run_solution_agents(db, project)
    return run


def _build_solution_context(db: Session, project_id: str) -> str:
    """Identischer, rollenunabhängiger Kontext für beide Phase-3-Agenten."""
    intake = db.get(Intake, project_id)
    research = db.get(Research, project_id)
    latest_research_run = (
        db.query(AgentRun)
        .filter(
            AgentRun.project_id == project_id,
            AgentRun.role == "research",
            AgentRun.status == "DONE",
        )
        .order_by(AgentRun.started_at.desc())
        .first()
    )
    sources = []
    if latest_research_run is not None:
        sources = db.query(ResearchSource).filter(
            ResearchSource.agent_run_id == latest_research_run.id
        ).all()

    research_data = {
        "solutions": json.loads(research.solutions),
        "best_practices": json.loads(research.best_practices),
        "open_source_potential": research.open_source_potential,
        "conclusion": research.conclusion,
        "sources": [{
            "url": source.url,
            "title": source.title,
            "finding": source.finding,
            "license_info": source.license_info,
        } for source in sources],
    }
    return (
        "BESTÄTIGTER INTAKE:\n"
        + _build_understanding_input(intake)
        + "\n"
        + wrap_external_research_data(research_data)
    )


def _solution_role_config(role: str):
    if role == "architect":
        return Architect, ArchitectOutput, ARCHITECT_PROMPT
    if role == "challenger":
        return Challenger, ChallengerOutput, CHALLENGER_PROMPT
    raise ValueError(f"Unbekannte Phase-3-Rolle: {role!r}")


def _run_solution_agents(
    db: Session,
    project: Project,
    roles: tuple[str, ...] = ("architect", "challenger"),
) -> None:
    """Führt die gewählten Phase-3-Zweige mit getrennten DB-Sessions parallel aus."""
    require_state(project, GENERATING_SOLUTIONS)
    project_id = project.id
    context = _build_solution_context(db, project_id)
    pending = {}

    for role in roles:
        model, output_schema, prompt = _solution_role_config(role)
        record = db.get(model, project_id)
        if record is None:
            record = model(project_id=project_id, run_status="PENDING")
            db.add(record)
            db.flush()
        if record.run_status == "DONE":
            continue

        _check_cost_ceiling(project)
        attempts = db.query(AgentRun).filter(
            AgentRun.project_id == project_id, AgentRun.role == role
        ).count()
        run = AgentRun(
            project_id=project_id,
            role=role,
            attempt=attempts + 1,
            status="RUNNING",
            started_at=_now(),
            model_class="HIGH",
            prompt_id=f"{role}_v1",
        )
        db.add(run)
        record.run_status = "RUNNING"
        db.flush()
        pending[role] = (model, run.id, output_schema, prompt)

    # RUNNING-Zeilen müssen vor den unabhängigen Writer-Sessions sichtbar sein.
    db.commit()
    branch_session = sessionmaker(bind=db.get_bind(), expire_on_commit=False)

    def invoke(role: str):
        model, run_id, output_schema, prompt = pending[role]
        try:
            result = call_model(
                role=role,
                model_class="HIGH",
                system_prompt=prompt,
                input_context=context,
                output_schema=output_schema,
            )
            error = None
        except ModelProviderError as exc:
            result = None
            error = exc

        finished_at = _now()
        record_values = {
            "run_status": "FAILED" if error is not None else "DONE",
        }
        run_values = {
            "finished_at": finished_at,
            "status": "FAILED" if error is not None else "DONE",
        }
        if error is not None:
            run_values["error"] = redact_secrets(str(error))
        else:
            record_values["output"] = json.dumps(
                result.parsed.model_dump(), ensure_ascii=False
            )
            run_values.update({
                "provider": result.provider,
                "model": result.model,
                "token_usage_input": result.input_tokens,
                "token_usage_output": result.output_tokens,
                "estimated_cost_usd": result.estimated_cost_usd,
            })

        # Jede Rolle schreibt Ergebnis und agent_runs-Status in einer eigenen
        # Transaktion. Keine SQLAlchemy-Session wird zwischen Threads geteilt.
        with branch_session() as branch_db:
            branch_db.execute(
                update(model).where(model.project_id == project_id).values(**record_values)
            )
            branch_db.execute(
                update(AgentRun).where(AgentRun.id == run_id).values(**run_values)
            )
            branch_db.commit()
        return result, error

    outcomes = {}
    if pending:
        with ThreadPoolExecutor(max_workers=len(pending)) as executor:
            futures = {role: executor.submit(invoke, role) for role in pending}
            outcomes = {role: future.result() for role, future in futures.items()}

    db.expire_all()
    project = db.get(Project, project_id)
    for result, error in outcomes.values():
        if error is None:
            project.total_model_calls += 1
            project.total_estimated_cost_usd += result.estimated_cost_usd

    architect = db.get(Architect, project.id)
    challenger = db.get(Challenger, project.id)
    if (
        architect is not None and architect.run_status == "DONE"
        and challenger is not None and challenger.run_status == "DONE"
    ):
        project.workflow_state = SYNTHESIZING
    project.updated_at = _now()
    db.commit()


def _to_project_detail(db: Session, project: Project) -> ProjectDetail:
    intake = db.get(Intake, project.id)
    understanding = db.get(Understanding, project.id)
    architect = db.get(Architect, project.id)
    challenger = db.get(Challenger, project.id)
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

    research_out = None
    research = db.get(Research, project.id)
    latest_research_run = (
        db.query(AgentRun)
        .filter(AgentRun.project_id == project.id, AgentRun.role == "research", AgentRun.status == "DONE")
        .order_by(AgentRun.started_at.desc()).first()
    )
    if research is not None and latest_research_run is not None:
        sources = db.query(ResearchSource).filter(
            ResearchSource.agent_run_id == latest_research_run.id
        ).all()
        research_out = ResearchOut(
            solutions=json.loads(research.solutions),
            best_practices=json.loads(research.best_practices),
            open_source_potential=research.open_source_potential,
            conclusion=research.conclusion,
            approved_at=research.approved_at,
            sources=[ResearchSourceOut(
                id=s.id, url=s.url, title=s.title, finding=s.finding,
                relevance=s.relevance, confidence=s.confidence,
                license_info=s.license_info, retrieved_at=s.retrieved_at,
                provider=s.provider,
            ) for s in sources],
        )

    return ProjectDetail(
        id=project.id,
        title=project.title,
        workflow_state=project.workflow_state,
        escalation_reason=project.escalation_reason,
        created_at=project.created_at,
        updated_at=project.updated_at,
        clarification_round_count=project.clarification_round_count,
        research_gate_enabled=bool(project.research_gate_enabled),
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
        research=research_out,
        architect=(SolutionAgentOut(
            output=json.loads(architect.output) if architect.output else None,
            run_status=architect.run_status,
        ) if architect is not None else None),
        challenger=(SolutionAgentOut(
            output=json.loads(challenger.output) if challenger.output else None,
            run_status=challenger.run_status,
        ) if challenger is not None else None),
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
    project.workflow_state = RESEARCHING
    project.updated_at = _now()
    db.commit()
    _run_research_agent(db, project)
    db.refresh(project)
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


@router.post("/{project_id}/research/approve", response_model=ProjectDetail)
def approve_research(project_id: str, db: Session = Depends(get_db)):
    project = _get_project_or_404(db, project_id)
    try:
        require_state(project, WAITING_FOR_RESEARCH_APPROVAL)
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail={"error": {"code": "INVALID_STATE", "message": str(exc)}})
    research = db.get(Research, project_id)
    research.approved_at = _now()
    project.workflow_state = GENERATING_SOLUTIONS
    project.updated_at = _now()
    db.commit()
    _run_solution_agents(db, project)
    db.refresh(project)
    return _to_project_detail(db, project)


@router.post("/{project_id}/research/rerun", response_model=ProjectDetail)
def rerun_research(project_id: str, payload: ResearchRerun, db: Session = Depends(get_db)):
    project = _get_project_or_404(db, project_id)
    try:
        require_state(project, WAITING_FOR_RESEARCH_APPROVAL)
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail={"error": {"code": "INVALID_STATE", "message": str(exc)}})
    project.workflow_state = RESEARCHING
    db.commit()
    _run_research_agent(db, project, payload.comment)
    db.refresh(project)
    return _to_project_detail(db, project)


@router.post("/{project_id}/retry", response_model=ProjectDetail)
def retry_last_step(project_id: str, db: Session = Depends(get_db)):
    project = _get_project_or_404(db, project_id)
    last_run = _last_agent_run(db, project_id)
    if last_run is None or last_run.status != "FAILED":
        last_run = (
            db.query(AgentRun)
            .filter(
                AgentRun.project_id == project_id,
                AgentRun.role.in_(("architect", "challenger")),
                AgentRun.status == "FAILED",
            )
            .order_by(AgentRun.finished_at.desc())
            .first()
        )
    if last_run is None or last_run.status != "FAILED":
        raise HTTPException(
            status_code=409,
            detail={"error": {"code": "NOTHING_TO_RETRY", "message": "Kein fehlgeschlagener Schritt vorhanden"}},
        )

    if last_run.role == "understanding":
        _run_understanding_agent(db, project)
        db.refresh(project)
        return _to_project_detail(db, project)

    if last_run.role == "research":
        _run_research_agent(db, project)
        db.refresh(project)
        return _to_project_detail(db, project)

    if last_run.role in ("architect", "challenger"):
        _run_solution_agents(db, project, roles=(last_run.role,))
        db.refresh(project)
        return _to_project_detail(db, project)

    raise HTTPException(status_code=409, detail={"error": {"code": "UNSUPPORTED_ROLE", "message": "Retry für diese Rolle ist noch nicht implementiert"}})
