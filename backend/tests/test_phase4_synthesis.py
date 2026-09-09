import re
from unittest.mock import patch

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import sessionmaker

from app.model_provider import ModelCallResult, ModelProviderError
from app.models import AgentRun, Project, ResearchSource, Synthesis
from app.research_provider import ExtractedPage, SearchHit
from app.schemas import (
    ResearchFinding,
    ResearchOutput,
    ResearchSolution,
    SynthesisExistingSolution,
    SynthesisOutput,
    UnderstandingOutput,
    UnderstandingStatus,
)
from tests.conftest import VALID_INTAKE


class FakeResearchProvider:
    provider_name = "tavily"

    def search(self, query, requirements, source_policy):
        return [SearchHit("https://example.test/tool", "Tool", "official", 0.9)]

    def extract(self, urls):
        return [ExtractedPage(urls[0], "Maintained MIT tool", "2026-09-09T06:00:00+00:00")]


READY = UnderstandingOutput(
    status=UnderstandingStatus.READY,
    summary="Die Idee ist klar. Habe ich das so richtig verstanden?",
)
RESEARCH = ResearchOutput(
    solutions=[ResearchSolution(
        name=f"Tool {i}", interesting="Belegt", reusable="Workflow",
        fit="TEILWEISE", constraint="Prüfen",
        source_urls=["https://example.test/tool"],
    ) for i in range(3)],
    best_practices=["Offizielle Quellen priorisieren"],
    open_source_potential="Gut",
    conclusion="Belegte Optionen vorhanden.",
    sources=[ResearchFinding(
        url="https://example.test/tool", title="Tool", finding="MIT",
        relevance=0.9, confidence=0.9, license_info="MIT",
    )],
)

# Der Synthesizer-Kontext bettet research_sources als JSON (inkl. "id")
# über wrap_external_research_data() ein - hier wird die tatsächlich vom
# Backend vergebene UUID aus dem echten input_context zurückgelesen, statt
# eine geratene ID zu verwenden.
SOURCE_ID_RE = re.compile(r'"id":\s*"([^"]+)"')


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


def synthesis_output(marker, source_id):
    return SynthesisOutput(
        approach=marker,
        adopted_core_elements=["Element"],
        discarded_or_changed_approaches=["Verworfen"],
        structure="Klare Struktur",
        existing_solutions_open_source=(
            [SynthesisExistingSolution(source_id=source_id, note="Übernommen")]
            if source_id else []
        ),
        key_decisions=["Entscheidung"],
        risks_open_points=["Offener Punkt"],
        conclusion="Fazit",
    )


def result(parsed):
    return ModelCallResult(parsed, "anthropic", "claude-opus-5", 20, 10, 0.002)


def full_cascade(marker_prefix="", bad_source_id=None, fail_synthesizer=False):
    """call_model-Mock, der alle bis SYNTHESIZING durchlaufenen Rollen
    bedient (research/architect/challenger/synthesizer) und für
    'synthesizer' die tatsächlich im Kontext gezeigte research_sources.id
    referenziert - oder bei bad_source_id bewusst eine erfundene (AT-4.1)."""
    def fake_call_model(**kwargs):
        role = kwargs["role"]
        if role == "research":
            return result(RESEARCH)
        if role in ("architect", "challenger"):
            return result(solution_output(kwargs["output_schema"], f"{marker_prefix}{role}"))
        if role == "synthesizer":
            if fail_synthesizer:
                raise ModelProviderError("simulierter Timeout")
            if bad_source_id is not None:
                source_id = bad_source_id
            else:
                match = SOURCE_ID_RE.search(kwargs["input_context"])
                source_id = match.group(1) if match else None
            return result(synthesis_output(f"{marker_prefix}synthesis", source_id))
        raise AssertionError(f"unerwartete Rolle: {role}")
    return fake_call_model


def synth_only(marker, source_id=None):
    def fake_call_model(**kwargs):
        assert kwargs["role"] == "synthesizer"
        return result(synthesis_output(marker, source_id))
    return fake_call_model


def run_to_synthesis(client, bad_source_id=None):
    project_id = client.post("/api/projects", json={
        "intake": VALID_INTAKE, "research_gate_enabled": False,
    }).json()["id"]
    with patch("app.routers.projects.call_model", return_value=result(READY)):
        client.post(f"/api/projects/{project_id}/submit")
    with patch("app.routers.projects._research_provider", return_value=FakeResearchProvider()), \
         patch("app.routers.projects.call_model", side_effect=full_cascade(bad_source_id=bad_source_id)):
        response = client.post(f"/api/projects/{project_id}/understanding/confirm")
    return project_id, response


def test_synthesis_runs_automatically_and_reaches_waiting_approval(client, test_engine):
    project_id, response = run_to_synthesis(client)
    body = response.json()
    assert body["workflow_state"] == "WAITING_FOR_SYNTHESIS_APPROVAL"
    assert body["synthesis"]["version"] == 1
    assert body["synthesis"]["approved_at"] is None
    assert body["synthesis"]["output"]["approach"] == "synthesis"
    assert body["last_run_status"] == "DONE"

    Session = sessionmaker(bind=test_engine)
    with Session() as db:
        rows = db.query(Synthesis).filter_by(project_id=project_id).all()
    assert len(rows) == 1


def test_fabricated_source_id_is_rejected(client):
    """AT-4.1: existing_solutions_open_source darf nur tatsächlich
    vorhandene research_sources.id-Werte referenzieren."""
    project_id, response = run_to_synthesis(client, bad_source_id="not-a-real-id")
    body = response.json()
    assert body["workflow_state"] == "SYNTHESIZING"
    assert body["last_run_status"] == "FAILED"
    assert body["synthesis"] is None


def test_referenced_by_synthesis_flag_recomputed_not_accumulated(client, test_engine):
    project_id, _ = run_to_synthesis(client)
    Session = sessionmaker(bind=test_engine)
    with Session() as db:
        source = db.query(ResearchSource).filter_by(project_id=project_id).one()
    assert source.referenced_by_synthesis == 1

    # ÄNDERUNGSWUNSCH mit anderer (leerer) Quellenauswahl - das Flag muss
    # zurückgesetzt werden, nicht kumulativ bleiben (nur version =
    # MAX(version) ist aktuell gültig, DATA_MODEL.md).
    with patch("app.routers.projects.call_model", side_effect=synth_only("round2")):
        change = client.post(
            f"/api/projects/{project_id}/synthesis/change-request",
            json={"comment": "Bitte ohne Altbestand-Referenz"},
        )
    assert change.json()["workflow_state"] == "WAITING_FOR_SYNTHESIS_APPROVAL"
    assert change.json()["synthesis"]["version"] == 2

    with Session() as db:
        source = db.query(ResearchSource).filter_by(project_id=project_id).one()
    assert source.referenced_by_synthesis == 0


def test_approve_transitions_to_reviewing(client):
    project_id, _ = run_to_synthesis(client)
    approved = client.post(f"/api/projects/{project_id}/synthesis/approve")
    body = approved.json()
    assert body["workflow_state"] == "REVIEWING"
    assert body["synthesis"]["approved_at"] is not None


def test_approve_guard_rejects_wrong_state(client):
    project_id = client.post(
        "/api/projects", json={"intake": VALID_INTAKE}
    ).json()["id"]
    resp = client.post(f"/api/projects/{project_id}/synthesis/approve")
    assert resp.status_code == 409


def test_change_request_creates_new_version_and_hint_from_round_three(client):
    project_id, _ = run_to_synthesis(client)

    for i in range(1, 4):
        with patch("app.routers.projects.call_model", side_effect=synth_only(f"r{i}")):
            resp = client.post(
                f"/api/projects/{project_id}/synthesis/change-request",
                json={"comment": f"Wunsch {i}"},
            )
        body = resp.json()
        assert body["synthesis"]["version"] == i + 1
        if i >= 3:
            assert body["hint"] == "Konzept grundlegend neu aufsetzen?"
        else:
            assert body["hint"] is None

    # hint ist nur Teil der change-request-Antwort, nicht des generischen
    # GET-Vertrags (API_CONTRACT.md:25 zählt die Felder explizit auf).
    get_resp = client.get(f"/api/projects/{project_id}")
    assert get_resp.json()["hint"] is None


def test_change_request_guard_rejects_wrong_state(client):
    project_id = client.post(
        "/api/projects", json={"intake": VALID_INTAKE}
    ).json()["id"]
    resp = client.post(
        f"/api/projects/{project_id}/synthesis/change-request", json={"comment": "x"}
    )
    assert resp.status_code == 409


def test_retry_repeats_only_failed_synthesizer(client, test_engine):
    project_id = client.post("/api/projects", json={
        "intake": VALID_INTAKE, "research_gate_enabled": False,
    }).json()["id"]
    with patch("app.routers.projects.call_model", return_value=result(READY)):
        client.post(f"/api/projects/{project_id}/submit")
    with patch("app.routers.projects._research_provider", return_value=FakeResearchProvider()), \
         patch("app.routers.projects.call_model", side_effect=full_cascade(fail_synthesizer=True)):
        first = client.post(f"/api/projects/{project_id}/understanding/confirm")
    assert first.json()["workflow_state"] == "SYNTHESIZING"
    assert first.json()["last_run_status"] == "FAILED"

    with patch("app.routers.projects.call_model", side_effect=synth_only("retry-ok")) as model:
        retried = client.post(f"/api/projects/{project_id}/retry")
    assert retried.json()["workflow_state"] == "WAITING_FOR_SYNTHESIS_APPROVAL"
    assert model.call_count == 1
    assert model.call_args.kwargs["role"] == "synthesizer"

    Session = sessionmaker(bind=test_engine)
    with Session() as db:
        synth_runs = db.query(AgentRun).filter_by(project_id=project_id, role="synthesizer").count()
        arch_runs = db.query(AgentRun).filter_by(project_id=project_id, role="architect").count()
    assert synth_runs == 2
    assert arch_runs == 1


def test_cost_ceiling_exceeded_during_change_request_leaves_revision_count_incremented(
    client, monkeypatch, test_engine,
):
    project_id, _ = run_to_synthesis(client)
    monkeypatch.setattr("app.routers.projects.MAX_MODEL_CALLS_PER_PROJECT", 0)

    resp = client.post(
        f"/api/projects/{project_id}/synthesis/change-request",
        json={"comment": "x"},
    )
    assert resp.status_code == 423

    Session = sessionmaker(bind=test_engine)
    with Session() as db:
        project = db.get(Project, project_id)
        assert project.synthesis_revision_count == 1
        assert project.workflow_state == "SYNTHESIZING"


def test_synthesis_output_schema_rejects_incomplete_result():
    with pytest.raises(ValidationError):
        SynthesisOutput.model_validate({"approach": "unvollständig"})
