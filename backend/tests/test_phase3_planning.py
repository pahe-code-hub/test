import threading
import time
from datetime import datetime
from unittest.mock import patch

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import sessionmaker

from app.model_provider import ModelCallResult, ModelProviderError
from app.models import AgentRun
from app.research_provider import ExtractedPage, SearchHit
from app.schemas import (
    ArchitectOutput,
    ChallengerOutput,
    ResearchFinding,
    ResearchOutput,
    ResearchSolution,
    UnderstandingOutput,
    UnderstandingStatus,
)
from tests.conftest import VALID_INTAKE


class FakeResearchProvider:
    provider_name = "tavily"

    def search(self, query, requirements, source_policy):
        return [SearchHit("https://example.test/tool", "Tool", "official", 0.9)]

    def extract(self, urls):
        return [ExtractedPage(urls[0], "Maintained MIT tool", "2026-09-08T06:00:00+00:00")]


READY = UnderstandingOutput(
    status=UnderstandingStatus.READY,
    summary="Die Idee ist klar. Habe ich das so richtig verstanden?",
)
RESEARCH = ResearchOutput(
    solutions=[ResearchSolution(
        name=f"Tool {index}", interesting="Belegt", reusable="Workflow",
        fit="TEILWEISE", constraint="Prüfen",
        source_urls=["https://example.test/tool"],
    ) for index in range(3)],
    best_practices=["Offizielle Quellen priorisieren"],
    open_source_potential="Gut",
    conclusion="Belegte Optionen vorhanden.",
    sources=[ResearchFinding(
        url="https://example.test/tool", title="Tool", finding="MIT",
        relevance=0.9, confidence=0.9, license_info="MIT",
    )],
)


def solution_output(schema, marker):
    return schema(
        approach=marker,
        structure="Eine klare Struktur",
        components=["Komponente"],
        interactions="Direkte Interaktion",
        technologies=["Vorhandenes Werkzeug"],
        risks=["Risiko"],
        implementation_approach="In Schritten",
        open_points=["Offener Punkt"],
    )


def result(parsed):
    return ModelCallResult(parsed, "anthropic", "claude-opus-5", 20, 10, 0.002)


def prepare_research_gate(client):
    project_id = client.post("/api/projects", json={
        "intake": VALID_INTAKE,
        "research_gate_enabled": True,
    }).json()["id"]
    with patch("app.routers.projects.call_model", return_value=result(READY)):
        client.post(f"/api/projects/{project_id}/submit")
    with patch("app.routers.projects._research_provider", return_value=FakeResearchProvider()), \
         patch("app.routers.projects.call_model", return_value=result(RESEARCH)):
        response = client.post(f"/api/projects/{project_id}/understanding/confirm")
    assert response.json()["workflow_state"] == "WAITING_FOR_RESEARCH_APPROVAL"
    return project_id


def test_approval_runs_both_roles_in_parallel_with_identical_isolated_context(
    client, test_engine,
):
    project_id = prepare_research_gate(client)
    barrier = threading.Barrier(2)
    intervals = {}
    contexts = {}

    def fake_call_model(**kwargs):
        role = kwargs["role"]
        contexts[role] = kwargs["input_context"]
        started = time.monotonic()
        barrier.wait(timeout=2)
        time.sleep(0.05)
        intervals[role] = (started, time.monotonic())
        schema = kwargs["output_schema"]
        return result(solution_output(schema, f"{role}-only-output"))

    # Phase 4 löst automatisch synthesizer_v1 aus, sobald SYNTHESIZING
    # erreicht ist - für diesen Phase-3-Test (Fokus: Architect/Challenger-
    # Parallelität) wird das analog zu test_phase2_research.py's
    # _run_solution_agents-Patch ausgeblendet.
    with patch("app.routers.projects.call_model", side_effect=fake_call_model), \
         patch("app.routers.projects._run_synthesis_agent"):
        response = client.post(f"/api/projects/{project_id}/research/approve")

    assert response.status_code == 200
    body = response.json()
    assert body["workflow_state"] == "SYNTHESIZING"
    assert body["architect"]["run_status"] == "DONE"
    assert body["challenger"]["run_status"] == "DONE"
    assert body["architect"]["output"]["approach"] == "architect-only-output"
    assert body["challenger"]["output"]["approach"] == "challenger-only-output"
    assert contexts["architect"] == contexts["challenger"]
    assert "<external_research_data>" in contexts["architect"]
    assert "challenger-only-output" not in contexts["architect"]
    assert "architect-only-output" not in contexts["challenger"]
    assert max(value[0] for value in intervals.values()) < min(
        value[1] for value in intervals.values()
    )

    Session = sessionmaker(bind=test_engine)
    with Session() as db:
        runs = db.query(AgentRun).filter(
            AgentRun.project_id == project_id,
            AgentRun.role.in_(("architect", "challenger")),
        ).all()
    assert len(runs) == 2
    assert all(run.status == "DONE" and run.model_class == "HIGH" for run in runs)
    assert max(datetime.fromisoformat(run.started_at) for run in runs) <= min(
        datetime.fromisoformat(run.finished_at) for run in runs
    )


def test_disabled_gate_automatically_runs_phase3_and_stops_at_synthesizing(client):
    project_id = client.post("/api/projects", json={
        "intake": VALID_INTAKE,
        "research_gate_enabled": False,
    }).json()["id"]
    with patch("app.routers.projects.call_model", return_value=result(READY)):
        client.post(f"/api/projects/{project_id}/submit")

    seen_roles = []

    def fake_call_model(**kwargs):
        role = kwargs["role"]
        seen_roles.append(role)
        if role == "research":
            return result(RESEARCH)
        return result(solution_output(kwargs["output_schema"], role))

    with patch("app.routers.projects._research_provider", return_value=FakeResearchProvider()), \
         patch("app.routers.projects.call_model", side_effect=fake_call_model), \
         patch("app.routers.projects._run_synthesis_agent"):
        response = client.post(f"/api/projects/{project_id}/understanding/confirm")

    assert response.json()["workflow_state"] == "SYNTHESIZING"
    assert set(seen_roles) == {"research", "architect", "challenger"}


def test_unequal_model_latencies_persist_both_branches_independently(client):
    project_id = prepare_research_gate(client)
    both_started = threading.Barrier(2)
    completed = []

    def fake_call_model(**kwargs):
        role = kwargs["role"]
        both_started.wait(timeout=2)
        time.sleep(0.01 if role == "architect" else 0.3)
        completed.append(role)
        return result(solution_output(kwargs["output_schema"], f"{role}-ok"))

    with patch("app.routers.projects.call_model", side_effect=fake_call_model), \
         patch("app.routers.projects._run_synthesis_agent"):
        response = client.post(f"/api/projects/{project_id}/research/approve")

    assert response.status_code == 200
    assert set(completed) == {"architect", "challenger"}
    body = response.json()
    assert body["workflow_state"] == "SYNTHESIZING"
    assert body["architect"]["run_status"] == "DONE"
    assert body["challenger"]["run_status"] == "DONE"
    assert body["architect"]["output"]["approach"] == "architect-ok"
    assert body["challenger"]["output"]["approach"] == "challenger-ok"


def test_retry_repeats_only_failed_challenger_branch(client, test_engine):
    project_id = prepare_research_gate(client)

    def first_attempt(**kwargs):
        if kwargs["role"] == "challenger":
            raise ModelProviderError("simulierter Timeout")
        return result(solution_output(kwargs["output_schema"], "architect-ok"))

    with patch("app.routers.projects.call_model", side_effect=first_attempt):
        first = client.post(f"/api/projects/{project_id}/research/approve")
    assert first.json()["workflow_state"] == "GENERATING_SOLUTIONS"
    assert first.json()["architect"]["run_status"] == "DONE"
    assert first.json()["challenger"]["run_status"] == "FAILED"

    with patch("app.routers.projects.call_model", return_value=result(
        solution_output(ChallengerOutput, "challenger-retry-ok")
    )) as model, patch("app.routers.projects._run_synthesis_agent"):
        retried = client.post(f"/api/projects/{project_id}/retry")

    assert retried.json()["workflow_state"] == "SYNTHESIZING"
    assert model.call_count == 1
    assert model.call_args.kwargs["role"] == "challenger"

    Session = sessionmaker(bind=test_engine)
    with Session() as db:
        architect_runs = db.query(AgentRun).filter_by(
            project_id=project_id, role="architect"
        ).count()
        challenger_runs = db.query(AgentRun).filter_by(
            project_id=project_id, role="challenger"
        ).count()
    assert architect_runs == 1
    assert challenger_runs == 2


@pytest.mark.parametrize("schema", [ArchitectOutput, ChallengerOutput])
def test_solution_output_schema_rejects_incomplete_results(schema):
    with pytest.raises(ValidationError):
        schema.model_validate({"approach": "unvollständig"})
