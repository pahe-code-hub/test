"""Phase 6 - Final Builder, Markdown-Export.

Baut auf run_to_synthesis() (Phase 4) und den Cascade-Helfern aus
test_phase5_quality.py auf. Jeder Test, der synthesis/approve oder retry
aufruft, mockt call_model fuer JEDE in der Kaskade erreichbare Rolle
(critic -> evaluator -> ggf. revision -> final_builder) - siehe die
Test-Isolations-Lektion in test_phase4_synthesis.py.
"""
from unittest.mock import patch

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import sessionmaker

from app.model_provider import ModelProviderError
from app.models import AgentRun, Final, Project, ResearchSource
from app.schemas import FinalBuilderOutput
from tests.test_phase4_synthesis import result, run_to_synthesis
from tests.test_phase5_quality import (
    ONE_REQUIRED_CHANGE,
    _cascade_mock,
    approve_with,
    critic_result,
    evaluator_result,
    final_result,
    resolve_with,
    revision_result,
)


def _real_source_id(test_engine, project_id):
    Session = sessionmaker(bind=test_engine)
    with Session() as db:
        return db.query(ResearchSource).filter_by(project_id=project_id).one().id


def test_final_builder_runs_on_pass_and_reaches_completed(client, test_engine):
    project_id, _ = run_to_synthesis(client)
    resp = approve_with(client, project_id, {
        "critic": critic_result("OK"),
        "evaluator": evaluator_result("PASS"),
        "final_builder": final_result(),
    })
    body = resp.json()
    assert body["workflow_state"] == "COMPLETED"
    plan = body["final"]["plan"]
    for field in (
        "goal_and_starting_point", "recommended_overall_solution",
        "structure_and_components", "feature_scope",
        "existing_open_source_solutions_used", "core_technical_decisions",
        "implementation_plan_phases", "risks_and_mitigations",
        "open_decisions", "acceptance_criteria", "presentation_structure",
    ):
        assert field in plan  # AT-6.1: alle 10 Abschnitte + Praesentationsstruktur
    assert body["final"]["presentation"] == "Gliederung"

    Session = sessionmaker(bind=test_engine)
    with Session() as db:
        assert db.query(Final).filter_by(project_id=project_id).count() == 1
        assert db.query(AgentRun).filter_by(project_id=project_id, role="final_builder", status="DONE").count() == 1


def test_final_builder_can_reference_valid_synthesis_source_id(client, test_engine):
    """Gegenstueck zum Ablehnungstest: eine tatsaechlich von der Synthese
    referenzierte research_sources.id darf final_builder_v1 verwenden
    (AT-6.1-Grundlage, Review 3 §3.1-Fix)."""
    project_id, _ = run_to_synthesis(client)
    source_id = _real_source_id(test_engine, project_id)
    resp = approve_with(client, project_id, {
        "critic": critic_result("OK"),
        "evaluator": evaluator_result("PASS"),
        "final_builder": result(FinalBuilderOutput(
            goal_and_starting_point="Ziel", recommended_overall_solution="Lösung",
            structure_and_components="Struktur", feature_scope="Umfang",
            existing_open_source_solutions_used=[{"source_id": source_id, "how_used": "Vorbild"}],
            core_technical_decisions="Entscheidung", implementation_plan_phases="Phasen",
            risks_and_mitigations="Risiken", open_decisions=[], acceptance_criteria=["Kriterium"],
            presentation_structure="Gliederung",
        )),
    })
    body = resp.json()
    assert body["workflow_state"] == "COMPLETED"
    assert body["final"]["plan"]["existing_open_source_solutions_used"][0]["source_id"] == source_id


def test_fabricated_source_id_in_final_builder_is_rejected(client):
    """AT-6.1-Grundlage (analog AT-4.1): eine erfundene source_id fuehrt zu
    FAILED, workflow bleibt FINALIZING."""
    project_id, _ = run_to_synthesis(client)
    resp = approve_with(client, project_id, {
        "critic": critic_result("OK"),
        "evaluator": evaluator_result("PASS"),
        "final_builder": result(FinalBuilderOutput(
            goal_and_starting_point="Ziel", recommended_overall_solution="Lösung",
            structure_and_components="Struktur", feature_scope="Umfang",
            existing_open_source_solutions_used=[{"source_id": "not-a-real-id", "how_used": "x"}],
            core_technical_decisions="Entscheidung", implementation_plan_phases="Phasen",
            risks_and_mitigations="Risiken", open_decisions=[], acceptance_criteria=["Kriterium"],
            presentation_structure="Gliederung",
        )),
    })
    body = resp.json()
    assert body["workflow_state"] == "FINALIZING"
    assert body["last_run_status"] == "FAILED"
    assert body["final"] is None


def test_open_points_from_escalation_are_merged_into_final_open_decisions(client, test_engine):
    """AT-6.2: die zuletzt offenen Evaluator-Punkte (ACCEPT_WITH_OPEN_POINTS)
    landen in final.open_decisions, zusaetzlich zu den vom final_builder
    selbst gelieferten - deterministisch code-seitig zusammengefuehrt, nicht
    nur per Prompt erhofft."""
    project_id, _ = run_to_synthesis(client)
    approve_with(client, project_id, {
        "critic": critic_result("OK"),
        "evaluator": [evaluator_result("REVISION_REQUIRED", required_changes=ONE_REQUIRED_CHANGE)] * 3,
        "revision": [revision_result("r1"), revision_result("r2")],
    })
    resp = resolve_with(client, project_id, "ACCEPT_WITH_OPEN_POINTS", {
        "final_builder": final_result(open_decisions=["Eigener offener Punkt"]),
    })
    body = resp.json()
    open_decisions = body["final"]["open_decisions"]
    assert "Eigener offener Punkt" in open_decisions
    assert any("Lücke" in d and "Ergänzen" in d for d in open_decisions)


def test_retry_repeats_only_failed_final_builder(client, test_engine):
    project_id, _ = run_to_synthesis(client)
    resp = approve_with(client, project_id, {
        "critic": critic_result("OK"),
        "evaluator": evaluator_result("PASS"),
        "final_builder": ModelProviderError("simulierter Timeout"),
    })
    assert resp.json()["workflow_state"] == "FINALIZING"
    assert resp.json()["last_run_status"] == "FAILED"

    with patch("app.routers.projects.call_model", side_effect=_cascade_mock({
        "final_builder": final_result(),
    })) as model:
        retried = client.post(f"/api/projects/{project_id}/retry")
    assert retried.json()["workflow_state"] == "COMPLETED"
    assert model.call_count == 1
    assert model.call_args.kwargs["role"] == "final_builder"

    Session = sessionmaker(bind=test_engine)
    with Session() as db:
        assert db.query(AgentRun).filter_by(project_id=project_id, role="final_builder").count() == 2


def test_cost_ceiling_exceeded_during_final_builder(client, monkeypatch, test_engine):
    """Deckel knapp so gesetzt, dass critic+evaluator noch durchlaufen,
    final_builder aber daran scheitert - Notbremse gilt fuer jeden der
    Phase-6-Aufrufe genauso wie fuer die vorigen Phasen."""
    project_id, _ = run_to_synthesis(client)
    Session = sessionmaker(bind=test_engine)
    with Session() as db:
        calls_before = db.get(Project, project_id).total_model_calls
    monkeypatch.setattr("app.routers.projects.MAX_MODEL_CALLS_PER_PROJECT", calls_before + 2)

    resp = approve_with(client, project_id, {
        "critic": critic_result("OK"),
        "evaluator": evaluator_result("PASS"),
    })
    assert resp.status_code == 423

    with Session() as db:
        assert db.query(AgentRun).filter_by(project_id=project_id, role="evaluator", status="DONE").count() == 1
        assert db.query(AgentRun).filter_by(project_id=project_id, role="final_builder").count() == 0


def test_export_markdown_returns_all_sections(client):
    project_id, _ = run_to_synthesis(client)
    approve_with(client, project_id, {
        "critic": critic_result("OK"),
        "evaluator": evaluator_result("PASS"),
        "final_builder": final_result(),
    })
    resp = client.get(f"/api/projects/{project_id}/export?format=markdown")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/markdown")
    body = resp.text
    for heading in (
        "Ziel und Ausgangslage", "Empfohlene Gesamtlösung", "Aufbau und Komponenten",
        "Funktionsumfang", "Verwendete bestehende/Open-Source-Lösungen",
        "Technische Grundentscheidungen", "Umsetzungsplan in Phasen",
        "Risiken und Gegenmaßnahmen", "Offene Entscheidungen", "Abnahmekriterien",
        "Präsentationsstruktur",
    ):
        assert heading in body  # AT-6.4: alle 10 Abschnitte + Praesentationsstruktur


def test_export_guard_rejects_wrong_state(client):
    project_id, _ = run_to_synthesis(client)
    resp = client.get(f"/api/projects/{project_id}/export?format=markdown")
    assert resp.status_code == 409


def test_export_unsupported_format_returns_422(client):
    project_id, _ = run_to_synthesis(client)
    approve_with(client, project_id, {
        "critic": critic_result("OK"),
        "evaluator": evaluator_result("PASS"),
        "final_builder": final_result(),
    })
    resp = client.get(f"/api/projects/{project_id}/export?format=pdf")
    assert resp.status_code == 422


def test_final_builder_output_schema_requires_all_fields():
    with pytest.raises(ValidationError):
        FinalBuilderOutput.model_validate({"goal_and_starting_point": "nur ein Feld"})
