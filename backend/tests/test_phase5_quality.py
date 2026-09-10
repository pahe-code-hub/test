"""Phase 5 - Critic/Evaluator/Revision, Revisionslimit, Eskalation.

Baut auf run_to_synthesis() aus test_phase4_synthesis.py auf (bis
WAITING_FOR_SYNTHESIS_APPROVAL), mockt ab dort gezielt critic_v1/
evaluator_v1/revision_v1. Jeder Test, der synthesis/approve oder retry
aufruft, mockt call_model fuer JEDE in der Kaskade erreichbare Rolle -
seit Phase 6 kettet ein PASS/ACCEPT_WITH_OPEN_POINTS automatisch WEITER
zu final_builder_v1, siehe FINAL_NOOP unten. Test-Isolations-Lektion:
siehe test_phase4_synthesis.py."""
from unittest.mock import patch

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import sessionmaker

from app.model_provider import ModelProviderError
from app.models import AgentRun, Critic, Evaluation, Project, Revision
from app.schemas import (
    CriticOutput,
    EvaluatorOutput,
    EvaluatorRequiredChange,
    FinalBuilderOutput,
    RevisionOutput,
    SynthesisOutput,
)
from tests.conftest import VALID_INTAKE
from tests.test_phase4_synthesis import result, run_to_synthesis, synthesis_output


def critic_result(status="OK", findings=None):
    return result(CriticOutput(status=status, findings=findings or []))


def evaluator_result(status="PASS", reasoning="Passt.", required_changes=None):
    return result(EvaluatorOutput(
        status=status,
        reasoning=reasoning if status == "PASS" else None,
        required_changes=required_changes or [],
    ))


def revision_result(marker="revidiert", changed="GEÄNDERT"):
    return result(RevisionOutput(
        updated_synthesis=synthesis_output(marker, source_id=None),
        changed=changed,
    ))


def final_result(open_decisions=None):
    """Neutraler final_builder_v1-Mock - Phase 6 selbst wird in
    test_phase6_final.py geprueft, hier nur noetig, um die seit Phase 6
    automatische Weiterkettung nach PASS/ACCEPT_WITH_OPEN_POINTS
    abzuschliessen, statt unbemerkt ueber den FAILED-Pfad zu laufen."""
    return result(FinalBuilderOutput(
        goal_and_starting_point="Ziel", recommended_overall_solution="Lösung",
        structure_and_components="Struktur", feature_scope="Umfang",
        existing_open_source_solutions_used=[],
        core_technical_decisions="Entscheidung", implementation_plan_phases="Phasen",
        risks_and_mitigations="Risiken", open_decisions=open_decisions or [],
        acceptance_criteria=["Kriterium"], presentation_structure="Gliederung",
    ))


ONE_REQUIRED_CHANGE = [EvaluatorRequiredChange(problem="Lücke", required_correction="Ergänzen")]


def _cascade_mock(cascade):
    counters = {}

    def fake_call_model(**kwargs):
        role = kwargs["role"]
        entry = cascade[role]
        if isinstance(entry, list):
            i = counters.get(role, 0)
            counters[role] = i + 1
            entry = entry[i]
        if isinstance(entry, Exception):
            raise entry
        return entry

    return fake_call_model


def approve_with(client, project_id, cascade):
    """cascade: dict role -> ModelCallResult | Exception | list (sequentiell
    konsumiert). synthesis/approve loest critic_v1 -> evaluator_v1 (->
    revision_v1 -> evaluator_v1 ... -> final_builder_v1) aus - alle hier
    erreichbaren Rollen muessen im cascade-dict vorhanden sein."""
    with patch("app.routers.projects.call_model", side_effect=_cascade_mock(cascade)):
        return client.post(f"/api/projects/{project_id}/synthesis/approve")


def resolve_with(client, project_id, action, cascade):
    with patch("app.routers.projects.call_model", side_effect=_cascade_mock(cascade)):
        return client.post(
            f"/api/projects/{project_id}/escalation/resolve", json={"action": action}
        )


def test_critic_ok_and_evaluator_pass_reach_finalizing(client, test_engine):
    project_id, _ = run_to_synthesis(client)
    resp = approve_with(client, project_id, {
        "critic": critic_result("OK"),
        "evaluator": evaluator_result("PASS"),
        "final_builder": final_result(),
    })
    body = resp.json()
    assert body["workflow_state"] == "COMPLETED"  # PASS kettet seit Phase 6 bis final_builder
    assert body["critic"]["status"] == "OK"
    assert len(body["evaluations"]) == 1
    assert body["evaluations"][0]["attempt"] == 0
    assert body["evaluations"][0]["status"] == "PASS"

    Session = sessionmaker(bind=test_engine)
    with Session() as db:
        assert db.query(Critic).filter_by(project_id=project_id).count() == 1
        assert db.query(Evaluation).filter_by(project_id=project_id).count() == 1


def test_critic_anmerkungen_still_chains_to_evaluator_automatically(client):
    """REVIEWING -> EVALUATING ist unabhaengig von OK/ANMERKUNGEN
    (WORKFLOW_STATES.md) - kein Nutzer-Gate dazwischen."""
    project_id, _ = run_to_synthesis(client)
    resp = approve_with(client, project_id, {
        "critic": critic_result("ANMERKUNGEN", findings=[{
            "problem": "Ungedeckte Annahme", "why_relevant": "Kernfunktion betroffen",
            "recommended_change": "Annahme klären", "priority": "WICHTIG",
        }]),
        "evaluator": evaluator_result("PASS"),
        "final_builder": final_result(),
    })
    body = resp.json()
    assert body["critic"]["status"] == "ANMERKUNGEN"
    assert body["critic"]["findings"][0]["priority"] == "WICHTIG"
    assert body["workflow_state"] == "COMPLETED"  # trotzdem weitergelaufen


def test_revision_required_chains_to_revision_then_back_to_evaluating_not_critic(client, test_engine):
    """AT-5.5: nach REVISING geht es zurueck zu EVALUATING, kein erneuter
    critic_v1-Lauf."""
    project_id, _ = run_to_synthesis(client)
    resp = approve_with(client, project_id, {
        "critic": critic_result("OK"),
        "evaluator": [
            evaluator_result("REVISION_REQUIRED", required_changes=ONE_REQUIRED_CHANGE),
            evaluator_result("PASS"),
        ],
        "revision": revision_result(),
        "final_builder": final_result(),
    })
    body = resp.json()
    assert body["workflow_state"] == "COMPLETED"
    assert len(body["evaluations"]) == 2
    assert body["evaluations"][0]["status"] == "REVISION_REQUIRED"
    assert body["evaluations"][0]["attempt"] == 0
    assert body["evaluations"][1]["status"] == "PASS"
    assert body["evaluations"][1]["attempt"] == 1

    Session = sessionmaker(bind=test_engine)
    with Session() as db:
        assert db.query(AgentRun).filter_by(project_id=project_id, role="critic").count() == 1
        assert db.query(AgentRun).filter_by(project_id=project_id, role="evaluator").count() == 2
        assert db.query(AgentRun).filter_by(project_id=project_id, role="revision").count() == 1
        revision_row = db.query(Revision).filter_by(project_id=project_id).one()
        assert revision_row.number == 1
        assert revision_row.changed == "GEÄNDERT"
        project = db.get(Project, project_id)
        assert project.revision_count == 1


def test_revision_limit_escalates_after_two_failed_revisions(client, test_engine):
    """AT-5.4: nach MAX_INTERNAL_REVISIONS=2 erfolglosen Revisionen ->
    ESCALATION_REQUIRED(REVISION_LIMIT); REWORK_INTAKE ist dort ungueltig."""
    project_id, _ = run_to_synthesis(client)
    resp = approve_with(client, project_id, {
        "critic": critic_result("OK"),
        "evaluator": [
            evaluator_result("REVISION_REQUIRED", required_changes=ONE_REQUIRED_CHANGE),
            evaluator_result("REVISION_REQUIRED", required_changes=ONE_REQUIRED_CHANGE),
            evaluator_result("REVISION_REQUIRED", required_changes=ONE_REQUIRED_CHANGE),
        ],
        "revision": [revision_result("r1"), revision_result("r2")],
    })
    body = resp.json()
    assert body["workflow_state"] == "ESCALATION_REQUIRED"
    assert body["escalation_reason"] == "REVISION_LIMIT"
    assert len(body["evaluations"]) == 3

    Session = sessionmaker(bind=test_engine)
    with Session() as db:
        project = db.get(Project, project_id)
        assert project.revision_count == 2

    wrong = client.post(f"/api/projects/{project_id}/escalation/resolve", json={"action": "REWORK_INTAKE"})
    assert wrong.status_code == 422


def test_accept_with_open_points_finalizes_without_further_revision(client):
    """AT-6.2 (Grundlage): die zuletzt offenen Evaluator-Punkte landen in
    final.open_decisions - vollstaendig in test_phase6_final.py geprueft,
    hier nur der Workflow-Uebergang."""
    project_id, _ = run_to_synthesis(client)
    approve_with(client, project_id, {
        "critic": critic_result("OK"),
        "evaluator": [evaluator_result("REVISION_REQUIRED", required_changes=ONE_REQUIRED_CHANGE)] * 3,
        "revision": [revision_result("r1"), revision_result("r2")],
    })
    resp = resolve_with(client, project_id, "ACCEPT_WITH_OPEN_POINTS", {
        "final_builder": final_result(),
    })
    body = resp.json()
    assert body["workflow_state"] == "COMPLETED"
    assert body["escalation_reason"] is None
    assert any("Lücke" in d for d in body["final"]["open_decisions"])


def test_retry_revision_after_escalation_is_not_capped_at_two(client, test_engine):
    """Nutzergetriebenes RETRY_REVISION nach Eskalation ist bewusst nicht
    durch MAX_INTERNAL_REVISIONS selbst gedeckelt - jede weitere Runde
    laeuft ohnehin wieder ueber das Nutzer-Gate (Leitprinzip 8)."""
    project_id, _ = run_to_synthesis(client)
    approve_with(client, project_id, {
        "critic": critic_result("OK"),
        "evaluator": [evaluator_result("REVISION_REQUIRED", required_changes=ONE_REQUIRED_CHANGE)] * 3,
        "revision": [revision_result("r1"), revision_result("r2")],
    })

    resp = resolve_with(client, project_id, "RETRY_REVISION", {
        "revision": revision_result("r3"),
        "evaluator": evaluator_result("PASS"),
        "final_builder": final_result(),
    })
    body = resp.json()
    assert body["workflow_state"] == "COMPLETED"

    Session = sessionmaker(bind=test_engine)
    with Session() as db:
        project = db.get(Project, project_id)
        assert project.revision_count == 3
        numbers = sorted(r.number for r in db.query(Revision).filter_by(project_id=project_id).all())
        assert numbers == [1, 2, 3]


def test_retry_repeats_only_failed_evaluator(client, test_engine):
    project_id, _ = run_to_synthesis(client)
    resp = approve_with(client, project_id, {
        "critic": critic_result("OK"),
        "evaluator": ModelProviderError("simulierter Timeout"),
    })
    body = resp.json()
    assert body["workflow_state"] == "EVALUATING"
    assert body["last_run_status"] == "FAILED"

    with patch("app.routers.projects.call_model", side_effect=_cascade_mock({
        "evaluator": evaluator_result("PASS"),
        "final_builder": final_result(),
    })) as model:
        retried = client.post(f"/api/projects/{project_id}/retry")
    assert retried.json()["workflow_state"] == "COMPLETED"
    assert model.call_count == 2
    assert model.call_args_list[0].kwargs["role"] == "evaluator"

    Session = sessionmaker(bind=test_engine)
    with Session() as db:
        assert db.query(AgentRun).filter_by(project_id=project_id, role="critic").count() == 1
        assert db.query(AgentRun).filter_by(project_id=project_id, role="evaluator").count() == 2


def test_cost_ceiling_exceeded_during_synthesis_approve(client, monkeypatch, test_engine):
    project_id, _ = run_to_synthesis(client)
    monkeypatch.setattr("app.routers.projects.MAX_MODEL_CALLS_PER_PROJECT", 0)
    resp = client.post(f"/api/projects/{project_id}/synthesis/approve")
    assert resp.status_code == 423

    Session = sessionmaker(bind=test_engine)
    with Session() as db:
        project = db.get(Project, project_id)
        # REVIEWING wurde vor dem Ceiling-Check bereits committet (wie beim
        # SYNTHESIZING-Muster aus Phase 4), der Aufruf selbst scheiterte am Deckel.
        assert project.workflow_state == "REVIEWING"


def test_critic_output_schema_rejects_more_than_five_findings():
    finding = {
        "problem": "x", "why_relevant": "y", "recommended_change": "z",
        "priority": "OPTIONAL",
    }
    with pytest.raises(ValidationError):
        CriticOutput.model_validate({"status": "ANMERKUNGEN", "findings": [finding] * 6})


def test_evaluator_output_schema_rejects_more_than_three_required_changes():
    change = {"problem": "x", "required_correction": "y"}
    with pytest.raises(ValidationError):
        EvaluatorOutput.model_validate({
            "status": "REVISION_REQUIRED",
            "required_changes": [change] * 4,
        })


def test_revision_output_requires_full_synthesis_structure():
    with pytest.raises(ValidationError):
        RevisionOutput.model_validate({
            "updated_synthesis": {"approach": "unvollstaendig"},
            "changed": "GEÄNDERT",
        })


def test_escalation_resolve_guard_rejects_wrong_state(client):
    project_id = client.post("/api/projects", json={"intake": VALID_INTAKE}).json()["id"]
    resp = client.post(f"/api/projects/{project_id}/escalation/resolve", json={"action": "RETRY_REVISION"})
    assert resp.status_code == 409
