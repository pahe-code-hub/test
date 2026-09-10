"""
REST-Endpunkte für Phase 1-6 entsprechend API_CONTRACT.md: Intake,
Understanding, Research, parallele Architect-/Challenger-Läufe,
Synthesizer inkl. Nutzerfreigabe 2, die interne Qualitätsschleife
Critic/Evaluator/Revision inkl. Revisionslimit und Eskalation, sowie
Final Builder inkl. Markdown-Export. Phase 7/8 (Live-Status/Kostenanzeige/
PDF-DOCX-JSON-Export) sind bewusst nicht enthalten.
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import update, func
from sqlalchemy.orm import Session, sessionmaker

from app.database import get_db
from app.models import (
    Project, Intake, Understanding, Research, ResearchSource,
    Architect, Challenger, Synthesis, Critic, Evaluation, Revision, Final, AgentRun,
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
    SynthesisOutput,
    SynthesisOut,
    SynthesisChangeRequest,
    CriticOutput,
    CriticOut,
    EvaluatorOutput,
    EvaluationOut,
    RevisionOutput,
    FinalBuilderOutput,
    FinalOut,
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
    WAITING_FOR_SYNTHESIS_APPROVAL,
    REVIEWING,
    EVALUATING,
    REVISION_REQUIRED,
    REVISING,
    FINALIZING,
    COMPLETED,
    CLARIFICATION_LIMIT,
    REVISION_LIMIT,
    InvalidTransitionError,
    require_state,
    clarification_limit_reached,
)
from app.config import (
    PROMPTS_DIR, MAX_MODEL_CALLS_PER_PROJECT,
    MAX_ESTIMATED_COST_PER_PROJECT_USD, RESEARCH_MAX_SOURCES,
    MAX_INTERNAL_REVISIONS, FINAL_BUILDER_MODEL_CLASS,
)

router = APIRouter(prefix="/api/projects", tags=["projects"])

UNDERSTANDING_PROMPT = (PROMPTS_DIR / "understanding_v1.md").read_text(encoding="utf-8")
RESEARCH_PROMPT = (PROMPTS_DIR / "research_v1.md").read_text(encoding="utf-8")
ARCHITECT_PROMPT = (PROMPTS_DIR / "architect_v1.md").read_text(encoding="utf-8")
CHALLENGER_PROMPT = (PROMPTS_DIR / "challenger_v1.md").read_text(encoding="utf-8")
SYNTHESIZER_PROMPT = (PROMPTS_DIR / "synthesizer_v1.md").read_text(encoding="utf-8")
CRITIC_PROMPT = (PROMPTS_DIR / "critic_v1.md").read_text(encoding="utf-8")
EVALUATOR_PROMPT = (PROMPTS_DIR / "evaluator_v1.md").read_text(encoding="utf-8")
REVISION_PROMPT = (PROMPTS_DIR / "revision_v1.md").read_text(encoding="utf-8")
FINAL_BUILDER_PROMPT = (PROMPTS_DIR / "final_builder_v1.md").read_text(encoding="utf-8")


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
    if project.workflow_state == SYNTHESIZING:
        _run_synthesis_agent(db, project)


def _current_synthesis_version(db: Session, project_id: str) -> int | None:
    return (
        db.query(func.max(Synthesis.version))
        .filter(Synthesis.project_id == project_id)
        .scalar()
    )


def _next_synthesis_version(db: Session, project_id: str) -> int:
    return (_current_synthesis_version(db, project_id) or 0) + 1


def _latest_done_research_run(db: Session, project_id: str) -> AgentRun | None:
    return (
        db.query(AgentRun)
        .filter(
            AgentRun.project_id == project_id,
            AgentRun.role == "research",
            AgentRun.status == "DONE",
        )
        .order_by(AgentRun.started_at.desc())
        .first()
    )


def _build_synthesis_context(db: Session, project_id: str, comment: str | None = None) -> str:
    """Wie _build_solution_context, aber research_sources MIT id (der
    Synthesizer braucht sie für existing_solutions_open_source[].source_id,
    AGENT_PROMPTS.md § synthesizer_v1) plus architect.output/
    challenger.output. Letztere werden NICHT gewrappt - eigene, bereits
    vertrauenswürdige Agenten-Ergebnisse sind keine externen Rohdaten
    (globale Regel 2, AGENT_PROMPTS.md). Die Research-Lookup-Query wird
    bewusst dupliziert statt mit _build_solution_context geteilt, um den
    bereits abgenommenen Phase-3-Code/-Tests nicht anzufassen."""
    intake = db.get(Intake, project_id)
    research = db.get(Research, project_id)
    latest_research_run = _latest_done_research_run(db, project_id)
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
            "id": source.id,
            "url": source.url,
            "title": source.title,
            "finding": source.finding,
            "license_info": source.license_info,
        } for source in sources],
    }

    architect = db.get(Architect, project_id)
    challenger = db.get(Challenger, project_id)

    context = (
        "BESTÄTIGTER INTAKE:\n"
        + _build_understanding_input(intake)
        + "\n"
        + wrap_external_research_data(research_data)
        + "\n\nARCHITECT-ENTWURF:\n"
        + architect.output
        + "\n\nCHALLENGER-ENTWURF:\n"
        + challenger.output
    )
    if comment:
        context += f"\nANMERKUNG ZUM ÄNDERUNGSWUNSCH: {comment}\n"
    return context


def _run_synthesis_agent(db: Session, project: Project, comment: str | None = None) -> AgentRun:
    """synthesizer_v1, atomar persistiert. Eine Synthesis-Zeile wird
    ausschließlich bei Erfolg angelegt (wie Research/Understanding, nicht
    wie das Architect/Challenger-Platzhaltermuster, das nur wegen der
    Thread-Koordination existiert) - dadurch ist next_version bei Erstlauf,
    technischem Retry und ÄNDERUNGSWUNSCH einheitlich MAX(version)+1, ohne
    Sonderfallbehandlung (DATA_MODEL.md: nur version = MAX(version) ist
    aktuell gültig)."""
    _check_cost_ceiling(project)
    attempts = db.query(AgentRun).filter(
        AgentRun.project_id == project.id, AgentRun.role == "synthesizer"
    ).count()
    run = AgentRun(
        project_id=project.id, role="synthesizer", attempt=attempts + 1,
        status="RUNNING", started_at=_now(), model_class="HIGH",
        prompt_id="synthesizer_v1",
    )
    db.add(run)
    db.flush()

    try:
        context = _build_synthesis_context(db, project.id, comment)
        result = call_model(
            role="synthesizer", model_class="HIGH", system_prompt=SYNTHESIZER_PROMPT,
            input_context=context, output_schema=SynthesisOutput,
        )
        output = result.parsed

        latest_research_run = _latest_done_research_run(db, project.id)
        valid_source_ids = set()
        if latest_research_run is not None:
            valid_source_ids = {
                sid for (sid,) in db.query(ResearchSource.id).filter(
                    ResearchSource.agent_run_id == latest_research_run.id
                ).all()
            }
        referenced_ids = {item.source_id for item in output.existing_solutions_open_source}
        if not referenced_ids <= valid_source_ids:
            raise ModelProviderError(
                "synthesizer_v1 referenziert eine nicht vorhandene research_sources.id"
            )  # AT-4.1

        version = _next_synthesis_version(db, project.id)
        db.add(Synthesis(
            project_id=project.id, version=version,
            output=json.dumps(output.model_dump(), ensure_ascii=False),
            approved_at=None,
        ))

        # referenced_by_synthesis gilt nur für die aktuelle Version (nicht
        # kumulativ über ÄNDERUNGSWUNSCH-Runden, siehe DATA_MODEL.md "nur
        # version = MAX(version) ist aktuell gültig").
        db.execute(
            update(ResearchSource)
            .where(ResearchSource.project_id == project.id)
            .values(referenced_by_synthesis=0)
        )
        if referenced_ids:
            db.execute(
                update(ResearchSource)
                .where(
                    ResearchSource.project_id == project.id,
                    ResearchSource.id.in_(referenced_ids),
                )
                .values(referenced_by_synthesis=1)
            )

        run.status = "DONE"
        run.finished_at = _now()
        run.provider = result.provider
        run.model = result.model
        run.token_usage_input = result.input_tokens
        run.token_usage_output = result.output_tokens
        run.estimated_cost_usd = result.estimated_cost_usd
        project.total_model_calls += 1
        project.total_estimated_cost_usd += result.estimated_cost_usd
        project.workflow_state = WAITING_FOR_SYNTHESIS_APPROVAL
        project.updated_at = _now()
    except ModelProviderError as exc:
        run.status = "FAILED"
        run.finished_at = _now()
        run.error = redact_secrets(str(exc))
        project.workflow_state = SYNTHESIZING

    db.commit()
    return run


# --- Phase 5: Critic / Evaluator / Revision --------------------------------


def _relevant_research_findings(db: Session, project_id: str) -> list[dict]:
    """'Relevante Research-Erkenntnisse' für critic_v1 (Abschnitt 23) -
    ausgelegt als die von der aktuellen Synthese tatsächlich referenzierten
    Quellen (`referenced_by_synthesis`, aus Phase 4), nicht der komplette
    Research-Fundus wie bei Architect/Challenger/Synthesizer."""
    latest_research_run = _latest_done_research_run(db, project_id)
    if latest_research_run is None:
        return []
    sources = db.query(ResearchSource).filter(
        ResearchSource.agent_run_id == latest_research_run.id,
        ResearchSource.referenced_by_synthesis == 1,
    ).all()
    return [{
        "url": s.url, "title": s.title, "finding": s.finding,
        "license_info": s.license_info,
    } for s in sources]


def _build_critic_context(db: Session, project_id: str, synthesis_output: dict) -> str:
    """Intake + relevante Research-Erkenntnisse (gewrappt, AT-SEC.1) +
    aktuelle Synthese. Erhält bewusst NICHT die Architect-/Challenger-
    Rohentwürfe (ADR-005, AGENT_PROMPTS.md § critic_v1)."""
    intake = db.get(Intake, project_id)
    findings = _relevant_research_findings(db, project_id)
    return (
        "BESTÄTIGTER INTAKE:\n"
        + _build_understanding_input(intake)
        + "\n"
        + wrap_external_research_data({"relevante_research_erkenntnisse": findings})
        + "\n\nAKTUELLE SYNTHESE:\n"
        + json.dumps(synthesis_output, ensure_ascii=False)
    )


def _run_critic_agent(db: Session, project: Project) -> AgentRun:
    """critic_v1, ausgelöst durch synthesis/approve. Schreibt eine Critic-
    Zeile nur bei Erfolg (wie Synthesis, kein Platzhalter bei FAILED) und
    kettet danach automatisch zu evaluator_v1 - REVIEWING ist kein
    Nutzer-Gate (WORKFLOW_STATES.md: REVIEWING -> EVALUATING automatisch,
    unabhängig von OK/ANMERKUNGEN)."""
    _check_cost_ceiling(project)
    version = _current_synthesis_version(db, project.id)
    synthesis_row = db.get(Synthesis, (project.id, version))
    synthesis_output = json.loads(synthesis_row.output)

    attempts = db.query(AgentRun).filter(
        AgentRun.project_id == project.id, AgentRun.role == "critic"
    ).count()
    run = AgentRun(
        project_id=project.id, role="critic", attempt=attempts + 1,
        status="RUNNING", started_at=_now(), model_class="HIGH",
        prompt_id="critic_v1",
    )
    db.add(run)
    db.flush()

    try:
        context = _build_critic_context(db, project.id, synthesis_output)
        result = call_model(
            role="critic", model_class="HIGH", system_prompt=CRITIC_PROMPT,
            input_context=context, output_schema=CriticOutput,
        )
        output = result.parsed

        db.add(Critic(
            project_id=project.id, synthesis_version=version,
            status=output.status,
            findings=json.dumps([f.model_dump() for f in output.findings], ensure_ascii=False),
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
        project.workflow_state = EVALUATING
        project.updated_at = _now()
    except ModelProviderError as exc:
        run.status = "FAILED"
        run.finished_at = _now()
        run.error = redact_secrets(str(exc))
        project.workflow_state = REVIEWING

    db.commit()
    if project.workflow_state == EVALUATING:
        _run_evaluator_agent(db, project)
    return run


def _latest_revision(db: Session, project_id: str) -> Revision | None:
    return (
        db.query(Revision)
        .filter(Revision.project_id == project_id)
        .order_by(Revision.number.desc())
        .first()
    )


def _latest_evaluation(db: Session, project_id: str) -> Evaluation | None:
    return (
        db.query(Evaluation)
        .filter(Evaluation.project_id == project_id)
        .order_by(Evaluation.created_at.desc())
        .first()
    )


def _current_synthesis_content(db: Session, project_id: str) -> dict:
    """Für Evaluator/Revision maßgeblicher Synthese-Inhalt: die letzte
    Revision, falls vorhanden, sonst die ursprünglich freigegebene
    Synthese-Version (Abschnitt 23: Evaluator erhält 'aktuelle Revision').
    Die `synthesis`-Tabellenzeile selbst bleibt unverändert - die
    Revisionsschicht liegt logisch darüber, siehe `Revision`-Modell."""
    revision = _latest_revision(db, project_id)
    if revision is not None:
        return json.loads(revision.updated_synthesis)
    version = _current_synthesis_version(db, project_id)
    synthesis_row = db.get(Synthesis, (project_id, version))
    return json.loads(synthesis_row.output)


def _build_evaluator_context(db: Session, project_id: str, synthesis_content: dict) -> str:
    """Intake, aktuelle Synthese, Critic-Ergebnis, NUR eine Diff-Notiz der
    letzten Revision (nicht die vollständige Historie, v0.2-Präzisierung
    Review 3 §3.5). Erhält bewusst KEINE Research-Daten direkt
    (WORKFLOW_STATES.md), daher kein wrap_external_research_data()."""
    intake = db.get(Intake, project_id)
    critic = db.get(Critic, (project_id, _current_synthesis_version(db, project_id)))
    critic_data = {"status": critic.status, "findings": json.loads(critic.findings)} if critic else None

    context = (
        "BESTÄTIGTER INTAKE:\n"
        + _build_understanding_input(intake)
        + "\n\nAKTUELLE SYNTHESE:\n"
        + json.dumps(synthesis_content, ensure_ascii=False)
        + "\n\nCRITIC-ERGEBNIS:\n"
        + json.dumps(critic_data, ensure_ascii=False)
    )
    revision = _latest_revision(db, project_id)
    if revision is not None:
        evaluation = db.get(Evaluation, revision.evaluation_id)
        required = json.loads(evaluation.required_changes) if evaluation and evaluation.required_changes else []
        context += (
            f"\n\nDIFF-NOTIZ LETZTE REVISION (Nr. {revision.number}, {revision.changed}):\n"
            f"adressierte geforderte Korrekturen: {json.dumps(required, ensure_ascii=False)}"
        )
    return context


def _run_evaluator_agent(db: Session, project: Project) -> AgentRun:
    """evaluator_v1. `evaluations.attempt` entspricht laut DATA_MODEL.md
    dem `revision_count` zum Zeitpunkt der Prüfung (0 vor jeder Revision,
    1/2 nach der ersten/zweiten). Kettet bei REVISION_REQUIRED automatisch
    zu revision_v1, sofern das interne Limit nicht erreicht ist; sonst
    Eskalation an den Nutzer (AT-5.4)."""
    _check_cost_ceiling(project)
    synthesis_content = _current_synthesis_content(db, project.id)

    attempts = db.query(AgentRun).filter(
        AgentRun.project_id == project.id, AgentRun.role == "evaluator"
    ).count()
    run = AgentRun(
        project_id=project.id, role="evaluator", attempt=attempts + 1,
        status="RUNNING", started_at=_now(), model_class="HIGH",
        prompt_id="evaluator_v1",
    )
    db.add(run)
    db.flush()

    try:
        context = _build_evaluator_context(db, project.id, synthesis_content)
        result = call_model(
            role="evaluator", model_class="HIGH", system_prompt=EVALUATOR_PROMPT,
            input_context=context, output_schema=EvaluatorOutput,
        )
        output = result.parsed

        db.add(Evaluation(
            project_id=project.id,
            attempt=project.revision_count,
            status=output.status,
            reasoning=output.reasoning,
            required_changes=(
                json.dumps([c.model_dump() for c in output.required_changes], ensure_ascii=False)
                if output.required_changes else None
            ),
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

        if output.status == "PASS":
            project.workflow_state = FINALIZING
        elif project.revision_count < MAX_INTERNAL_REVISIONS:
            project.workflow_state = REVISION_REQUIRED
        else:
            project.workflow_state = ESCALATION_REQUIRED
            project.escalation_reason = REVISION_LIMIT
        project.updated_at = _now()
    except ModelProviderError as exc:
        run.status = "FAILED"
        run.finished_at = _now()
        run.error = redact_secrets(str(exc))
        project.workflow_state = EVALUATING

    db.commit()
    if project.workflow_state == REVISION_REQUIRED:
        _run_revision_agent(db, project)
    elif project.workflow_state == FINALIZING:
        _run_final_builder_agent(db, project)
    return run


def _run_revision_agent(db: Session, project: Project) -> AgentRun:
    """revision_v1: korrigiert ausschließlich die zuletzt geforderten
    Punkte (`_latest_evaluation`). Erzeugt KEINE neue `synthesis`-Version,
    sondern eine `revisions`-Zeile (siehe `_current_synthesis_content`).
    Kettet danach immer zurück zu evaluator_v1, NIE zu critic_v1 (AT-5.5)."""
    _check_cost_ceiling(project)
    synthesis_content = _current_synthesis_content(db, project.id)
    evaluation = _latest_evaluation(db, project.id)
    required_changes = json.loads(evaluation.required_changes) if evaluation.required_changes else []

    attempts = db.query(AgentRun).filter(
        AgentRun.project_id == project.id, AgentRun.role == "revision"
    ).count()
    run = AgentRun(
        project_id=project.id, role="revision", attempt=attempts + 1,
        status="RUNNING", started_at=_now(), model_class="HIGH",
        prompt_id="revision_v1",
    )
    db.add(run)
    db.flush()

    try:
        context = (
            "AKTUELLE SYNTHESE:\n"
            + json.dumps(synthesis_content, ensure_ascii=False)
            + "\n\nGEFORDERTE KORREKTUREN:\n"
            + json.dumps(required_changes, ensure_ascii=False)
        )
        result = call_model(
            role="revision", model_class="HIGH", system_prompt=REVISION_PROMPT,
            input_context=context, output_schema=RevisionOutput,
        )
        output = result.parsed

        project.revision_count += 1
        db.add(Revision(
            project_id=project.id,
            number=project.revision_count,
            evaluation_id=evaluation.id,
            updated_synthesis=json.dumps(output.updated_synthesis.model_dump(), ensure_ascii=False),
            changed=output.changed,
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
        project.workflow_state = EVALUATING  # zurück zum Evaluator, kein erneuter Critic (AT-5.5)
        project.updated_at = _now()
    except ModelProviderError as exc:
        run.status = "FAILED"
        run.finished_at = _now()
        run.error = redact_secrets(str(exc))
        project.workflow_state = REVISING

    db.commit()
    if project.workflow_state == EVALUATING:
        _run_evaluator_agent(db, project)
    return run


# --- Phase 6: Final Builder --------------------------------------------------


def _open_evaluator_points(db: Session, project_id: str) -> list[str]:
    """Offene Evaluator-Punkte, die laut WORKFLOW_STATES.md bei
    ESCALATION_REQUIRED -> FINALIZING (ACCEPT_WITH_OPEN_POINTS) in
    final.open_decisions übernommen werden müssen (AT-6.2). Die letzte
    Evaluation hat nur dann noch status=REVISION_REQUIRED, wenn der
    Nutzer sie via ACCEPT_WITH_OPEN_POINTS akzeptiert hat, statt eine
    weitere Revision anzustoßen - beim normalen PASS-Pfad ist die letzte
    Evaluation immer PASS."""
    evaluation = _latest_evaluation(db, project_id)
    if evaluation is None or evaluation.status != "REVISION_REQUIRED":
        return []
    changes = json.loads(evaluation.required_changes) if evaluation.required_changes else []
    return [f"{c['problem']}: {c['required_correction']}" for c in changes]


def _build_final_builder_context(db: Session, project_id: str, synthesis_content: dict) -> str:
    """Intake, freigegebenes Zielkonzept, relevante Entscheidungen, plus
    die vom Zielkonzept referenzierten research_sources als
    <external_research_data> (v0.2-Fix, behebt Review 3 §3.1 - AGENT_PROMPTS.md
    § final_builder_v1)."""
    intake = db.get(Intake, project_id)
    referenced_ids = {
        item.get("source_id")
        for item in synthesis_content.get("existing_solutions_open_source", [])
    }
    sources = []
    if referenced_ids:
        sources = db.query(ResearchSource).filter(
            ResearchSource.project_id == project_id,
            ResearchSource.id.in_(referenced_ids),
        ).all()
    research_data = {"referenzierte_quellen": [{
        "id": s.id, "url": s.url, "title": s.title,
        "finding": s.finding, "license_info": s.license_info,
    } for s in sources]}

    context = (
        "BESTÄTIGTER INTAKE:\n"
        + _build_understanding_input(intake)
        + "\n\nFREIGEGEBENES ZIELKONZEPT:\n"
        + json.dumps(synthesis_content, ensure_ascii=False)
        + "\n\n"
        + wrap_external_research_data(research_data)
    )
    open_points = _open_evaluator_points(db, project_id)
    if open_points:
        context += (
            "\n\nOFFENE PUNKTE AUS DER ESKALATION (vom Nutzer ausdrücklich "
            "akzeptiert, müssen unter open_decisions sichtbar bleiben):\n"
            + json.dumps(open_points, ensure_ascii=False)
        )
    return context


def _run_final_builder_agent(db: Session, project: Project) -> AgentRun:
    """final_builder_v1. Prüft wie beim Synthesizer (AT-4.1) referentielle
    Integrität der referenzierten source_ids VOR jeder Persistierung
    (AT-6.1-Grundlage) und stellt die aus einer Eskalation übernommenen
    offenen Evaluator-Punkte programmatisch sicher (AT-6.2), statt sich
    allein auf Prompt-Befolgung zu verlassen."""
    _check_cost_ceiling(project)
    synthesis_content = _current_synthesis_content(db, project.id)
    open_points = _open_evaluator_points(db, project.id)
    valid_source_ids = {
        item.get("source_id")
        for item in synthesis_content.get("existing_solutions_open_source", [])
    }

    attempts = db.query(AgentRun).filter(
        AgentRun.project_id == project.id, AgentRun.role == "final_builder"
    ).count()
    run = AgentRun(
        project_id=project.id, role="final_builder", attempt=attempts + 1,
        status="RUNNING", started_at=_now(), model_class=FINAL_BUILDER_MODEL_CLASS,
        prompt_id="final_builder_v1",
    )
    db.add(run)
    db.flush()

    try:
        context = _build_final_builder_context(db, project.id, synthesis_content)
        result = call_model(
            role="final_builder", model_class=FINAL_BUILDER_MODEL_CLASS,
            system_prompt=FINAL_BUILDER_PROMPT, input_context=context,
            output_schema=FinalBuilderOutput,
        )
        output = result.parsed

        referenced_ids = {item.source_id for item in output.existing_open_source_solutions_used}
        if not referenced_ids <= valid_source_ids:
            raise ModelProviderError(
                "final_builder_v1 referenziert eine research_sources.id, die "
                "dem Zielkonzept nicht zugeordnet ist"
            )  # AT-6.1-Grundlage, analog AT-4.1

        merged_open_decisions = list(output.open_decisions)
        for point in open_points:
            if point not in merged_open_decisions:
                merged_open_decisions.append(point)
        output.open_decisions = merged_open_decisions  # AT-6.2

        db.add(Final(
            project_id=project.id,
            plan=json.dumps(output.model_dump(), ensure_ascii=False),
            presentation=output.presentation_structure,
            open_decisions=json.dumps(merged_open_decisions, ensure_ascii=False),
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
        project.workflow_state = COMPLETED
        project.updated_at = _now()
    except ModelProviderError as exc:
        run.status = "FAILED"
        run.finished_at = _now()
        run.error = redact_secrets(str(exc))
        project.workflow_state = FINALIZING

    db.commit()
    return run


_FINAL_MARKDOWN_SECTIONS = (
    ("goal_and_starting_point", "Ziel und Ausgangslage"),
    ("recommended_overall_solution", "Empfohlene Gesamtlösung"),
    ("structure_and_components", "Aufbau und Komponenten"),
    ("feature_scope", "Funktionsumfang"),
    ("core_technical_decisions", "Technische Grundentscheidungen"),
    ("implementation_plan_phases", "Umsetzungsplan in Phasen"),
    ("risks_and_mitigations", "Risiken und Gegenmaßnahmen"),
)


def _render_final_markdown(title: str, plan: dict) -> str:
    """AT-6.4: eine valide, vollständige Markdown-Datei mit allen 10 in
    AGENT_PROMPTS.md § final_builder_v1 definierten Abschnitten plus
    Präsentationsstruktur."""
    lines = [f"# {title}", ""]
    for field, heading in _FINAL_MARKDOWN_SECTIONS:
        lines += [f"## {heading}", "", str(plan.get(field, "")), ""]

    lines += ["## Verwendete bestehende/Open-Source-Lösungen", ""]
    used = plan.get("existing_open_source_solutions_used") or []
    if used:
        for item in used:
            lines.append(f"- `{item.get('source_id')}`: {item.get('how_used')}")
    else:
        lines.append("- keine")
    lines.append("")

    lines += ["## Offene Entscheidungen", ""]
    open_decisions = plan.get("open_decisions") or []
    if open_decisions:
        lines += [f"- {d}" for d in open_decisions]
    else:
        lines.append("- keine")
    lines.append("")

    lines += ["## Abnahmekriterien", ""]
    criteria = plan.get("acceptance_criteria") or []
    if criteria:
        lines += [f"- {c}" for c in criteria]
    else:
        lines.append("- keine")
    lines.append("")

    lines += ["## Präsentationsstruktur", "", str(plan.get("presentation_structure", "")), ""]
    return "\n".join(lines)


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

    synthesis_version = _current_synthesis_version(db, project.id)
    synthesis_out = None
    if synthesis_version is not None:
        synthesis_row = db.get(Synthesis, (project.id, synthesis_version))
        synthesis_out = SynthesisOut(
            version=synthesis_row.version,
            output=json.loads(synthesis_row.output),
            approved_at=synthesis_row.approved_at,
        )

    critic_out = None
    if synthesis_version is not None:
        critic_row = db.get(Critic, (project.id, synthesis_version))
        if critic_row is not None:
            critic_out = CriticOut(
                status=critic_row.status,
                findings=json.loads(critic_row.findings),
            )

    evaluations_out = [
        EvaluationOut(
            attempt=e.attempt, status=e.status, reasoning=e.reasoning,
            required_changes=json.loads(e.required_changes) if e.required_changes else [],
            created_at=e.created_at,
        )
        for e in db.query(Evaluation)
            .filter(Evaluation.project_id == project.id)
            .order_by(Evaluation.created_at.asc())
            .all()
    ]

    final_row = db.get(Final, project.id)
    final_out = None
    if final_row is not None:
        final_out = FinalOut(
            plan=json.loads(final_row.plan),
            presentation=final_row.presentation,
            open_decisions=json.loads(final_row.open_decisions),
            created_at=final_row.created_at,
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
        synthesis=synthesis_out,
        critic=critic_out,
        evaluations=evaluations_out,
        final=final_out,
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
    """Body-Form hängt vom aktuellen `escalation_reason` ab (API_CONTRACT.md).
    Eine `action`, die nicht zum aktuellen Grund passt (z.B. `RETRY_REVISION`
    bei `CLARIFICATION_LIMIT`), liefert 422."""
    project = _get_project_or_404(db, project_id)
    try:
        require_state(project, ESCALATION_REQUIRED)
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail={"error": {"code": "INVALID_STATE", "message": str(exc)}})

    if project.escalation_reason == CLARIFICATION_LIMIT:
        if payload.action != "REWORK_INTAKE":
            raise HTTPException(
                status_code=422,
                detail={"error": {"code": "INVALID_ACTION", "message": "Bei CLARIFICATION_LIMIT ist nur 'REWORK_INTAKE' gültig"}},
            )
        project.workflow_state = DRAFT
        project.escalation_reason = None
        project.clarification_round_count = 0
        project.updated_at = _now()
        db.commit()
        return _to_project_detail(db, project)

    if project.escalation_reason == REVISION_LIMIT:
        if payload.action == "RETRY_REVISION":
            # Weiterer, vom Nutzer ausdrücklich angeforderter Versuch am
            # bestehenden Zielkonzept (Abschnitt 16/WORKFLOW_STATES.md) -
            # bewusst nicht durch MAX_INTERNAL_REVISIONS selbst gedeckelt,
            # da jede Runde ohnehin wieder über dieses Nutzer-Gate läuft
            # (Leitprinzip 8: keine Endlosschleife ohne Nutzeraktion).
            project.workflow_state = REVISING
            project.escalation_reason = None
            db.commit()
            _run_revision_agent(db, project)
            db.refresh(project)
            return _to_project_detail(db, project)
        if payload.action == "ACCEPT_WITH_OPEN_POINTS":
            project.workflow_state = FINALIZING
            project.escalation_reason = None
            project.updated_at = _now()
            db.commit()
            _run_final_builder_agent(db, project)
            db.refresh(project)
            return _to_project_detail(db, project)
        raise HTTPException(
            status_code=422,
            detail={"error": {"code": "INVALID_ACTION", "message": "Bei REVISION_LIMIT ist nur 'RETRY_REVISION' oder 'ACCEPT_WITH_OPEN_POINTS' gültig"}},
        )

    raise HTTPException(
        status_code=422,
        detail={"error": {"code": "INVALID_ACTION", "message": f"Unbekannter escalation_reason: {project.escalation_reason!r}"}},
    )


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


@router.post("/{project_id}/synthesis/approve", response_model=ProjectDetail)
def approve_synthesis(project_id: str, db: Session = Depends(get_db)):
    """„ZIELKONZEPT FREIGEBEN". Löst critic_v1 aus (API_CONTRACT.md), das
    automatisch weiter zu evaluator_v1 kettet (Phase 5)."""
    project = _get_project_or_404(db, project_id)
    try:
        require_state(project, WAITING_FOR_SYNTHESIS_APPROVAL)
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail={"error": {"code": "INVALID_STATE", "message": str(exc)}})

    version = _current_synthesis_version(db, project_id)
    synthesis = db.get(Synthesis, (project_id, version))
    synthesis.approved_at = _now()
    project.workflow_state = REVIEWING
    project.updated_at = _now()
    db.commit()
    _run_critic_agent(db, project)
    db.refresh(project)
    return _to_project_detail(db, project)


@router.post("/{project_id}/synthesis/change-request", response_model=ProjectDetail)
def change_request_synthesis(project_id: str, payload: SynthesisChangeRequest, db: Session = Depends(get_db)):
    """„ÄNDERUNGSWUNSCH" (AT-4.2): erzeugt eine neue Synthesis-Version, kein
    Überschreiben der vorherigen."""
    project = _get_project_or_404(db, project_id)
    try:
        require_state(project, WAITING_FOR_SYNTHESIS_APPROVAL)
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail={"error": {"code": "INVALID_STATE", "message": str(exc)}})

    project.synthesis_revision_count += 1
    project.workflow_state = SYNTHESIZING
    db.commit()
    _run_synthesis_agent(db, project, comment=payload.comment)
    db.refresh(project)

    detail = _to_project_detail(db, project)
    if project.synthesis_revision_count >= 3:
        detail.hint = "Konzept grundlegend neu aufsetzen?"
    return detail


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

    if last_run.role == "synthesizer":
        _run_synthesis_agent(db, project)
        db.refresh(project)
        return _to_project_detail(db, project)

    if last_run.role == "critic":
        _run_critic_agent(db, project)
        db.refresh(project)
        return _to_project_detail(db, project)

    if last_run.role == "evaluator":
        _run_evaluator_agent(db, project)
        db.refresh(project)
        return _to_project_detail(db, project)

    if last_run.role == "revision":
        _run_revision_agent(db, project)
        db.refresh(project)
        return _to_project_detail(db, project)

    if last_run.role == "final_builder":
        _run_final_builder_agent(db, project)
        db.refresh(project)
        return _to_project_detail(db, project)

    raise HTTPException(status_code=409, detail={"error": {"code": "UNSUPPORTED_ROLE", "message": "Retry für diese Rolle ist noch nicht implementiert"}})


@router.get("/{project_id}/export")
def export_project(project_id: str, format: str = "markdown", db: Session = Depends(get_db)):
    """API_CONTRACT.md § Export - nur `format=markdown` (Phase 6);
    PDF/DOCX/JSON sind Phase 8 und hier nicht unterstützt."""
    project = _get_project_or_404(db, project_id)
    try:
        require_state(project, COMPLETED)
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail={"error": {"code": "INVALID_STATE", "message": str(exc)}})

    if format != "markdown":
        raise HTTPException(
            status_code=422,
            detail={"error": {"code": "UNSUPPORTED_FORMAT", "message": "Nur format=markdown ist in Phase 6 unterstützt"}},
        )

    final = db.get(Final, project_id)
    markdown = _render_final_markdown(project.title, json.loads(final.plan))
    return Response(
        content=markdown,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{project_id}.md"'},
    )
