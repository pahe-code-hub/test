"""
Tests für ACCEPTANCE_TESTS.md Phase 1 (AT-1.1 bis AT-1.7). Der
Modellaufruf wird gemockt (app.routers.projects.call_model) - Phase 1
soll die Workflow-/State-Logik beweisen, nicht die Qualität echter
Anthropic-Antworten (das ist Aufgabe der Prompt-Iteration, nicht
dieser Checkpoint-Tests).
"""
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.model_provider import ModelCallResult, ModelProviderError
from app.schemas import UnderstandingOutput, UnderstandingStatus
from app.models import Project, AgentRun

from tests.conftest import VALID_INTAKE


def _result(parsed, cost=0.0002):
    return ModelCallResult(
        parsed=parsed,
        provider="anthropic",
        model="claude-sonnet-5",
        input_tokens=120,
        output_tokens=60,
        estimated_cost_usd=cost,
    )


READY_OUTPUT = UnderstandingOutput(
    status=UnderstandingStatus.READY,
    summary="Ziel: Angebote schneller erstellen. Problem: manuelle Word-Angebote. "
    "Für ein 5-köpfiges Vertriebsteam. Richtung: lokale Web-App. "
    "Habe ich das so richtig verstanden?",
)

CLARIFICATION_OUTPUT = UnderstandingOutput(
    status=UnderstandingStatus.CLARIFICATION_REQUIRED,
    questions=["Soll die Lösung offline nutzbar sein?"],
)


# --- AT-1.1 -----------------------------------------------------------------


def test_project_creation_with_six_fields(client):
    resp = client.post("/api/projects", json={"intake": VALID_INTAKE})
    assert resp.status_code == 201
    body = resp.json()
    assert body["workflow_state"] == "DRAFT"
    assert body["intake"]["goal"] == VALID_INTAKE["goal"]


def test_submit_rejects_incomplete_intake(client):
    incomplete = dict(VALID_INTAKE)
    incomplete["core_features"] = ""
    resp = client.post("/api/projects", json={"intake": incomplete})
    project_id = resp.json()["id"]

    resp = client.post(f"/api/projects/{project_id}/submit")
    assert resp.status_code == 422
    assert resp.json()["detail"]["error"]["code"] == "INCOMPLETE_INTAKE"


# --- AT-1.2 / AT-1.3 ---------------------------------------------------------


def test_understanding_ready_leads_to_confirmation_gate(client):
    resp = client.post("/api/projects", json={"intake": VALID_INTAKE})
    project_id = resp.json()["id"]

    with patch("app.routers.projects.call_model", return_value=_result(READY_OUTPUT)):
        resp = client.post(f"/api/projects/{project_id}/submit")
    assert resp.status_code == 200
    body = resp.json()
    assert body["workflow_state"] == "WAITING_FOR_USER_CONFIRMATION"
    assert body["understanding"]["status"] == "READY"
    assert body["understanding"]["summary"].endswith("Habe ich das so richtig verstanden?")


def test_confirm_transitions_to_researching(client):
    resp = client.post("/api/projects", json={"intake": VALID_INTAKE})
    project_id = resp.json()["id"]
    with patch("app.routers.projects.call_model", return_value=_result(READY_OUTPUT)):
        client.post(f"/api/projects/{project_id}/submit")

    resp = client.post(f"/api/projects/{project_id}/understanding/confirm")
    assert resp.status_code == 200
    assert resp.json()["workflow_state"] == "RESEARCHING"


def test_correct_returns_to_draft(client):
    resp = client.post("/api/projects", json={"intake": VALID_INTAKE})
    project_id = resp.json()["id"]
    with patch("app.routers.projects.call_model", return_value=_result(READY_OUTPUT)):
        client.post(f"/api/projects/{project_id}/submit")

    resp = client.post(f"/api/projects/{project_id}/understanding/correct")
    assert resp.status_code == 200
    assert resp.json()["workflow_state"] == "DRAFT"


# --- AT-1.4: Klärungsrunden-Limit und korrekte Eskalations-Rückwege --------


def test_clarification_limit_escalates_and_only_rework_intake_is_valid(client):
    resp = client.post("/api/projects", json={"intake": VALID_INTAKE})
    project_id = resp.json()["id"]

    with patch("app.routers.projects.call_model", return_value=_result(CLARIFICATION_OUTPUT)):
        resp = client.post(f"/api/projects/{project_id}/submit")
        assert resp.json()["workflow_state"] == "WAITING_FOR_USER_CLARIFICATION"
        assert len(resp.json()["understanding"]["questions"]) <= 3

        # Runde 1 und 2: bleibt bei WAITING_FOR_USER_CLARIFICATION
        for _ in range(2):
            resp = client.post(f"/api/projects/{project_id}/clarification", json={"answers": "..."})
            assert resp.json()["workflow_state"] == "WAITING_FOR_USER_CLARIFICATION"

        # Runde 3 (MAX_CLARIFICATION_ROUNDS erreicht): Eskalation
        resp = client.post(f"/api/projects/{project_id}/clarification", json={"answers": "..."})

    assert resp.json()["workflow_state"] == "ESCALATION_REQUIRED"
    assert resp.json()["escalation_reason"] == "CLARIFICATION_LIMIT"

    # Falscher Action-Typ für diesen escalation_reason -> 422
    resp = client.post(f"/api/projects/{project_id}/escalation/resolve", json={"action": "RETRY_REVISION"})
    assert resp.status_code == 422

    # Einziger gültiger Ausgang: REWORK_INTAKE -> DRAFT, Zähler zurückgesetzt
    resp = client.post(f"/api/projects/{project_id}/escalation/resolve", json={"action": "REWORK_INTAKE"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["workflow_state"] == "DRAFT"
    assert body["escalation_reason"] is None
    assert body["clarification_round_count"] == 0


# --- AT-1.5: keine Secrets im Frontend/Fehlertext ---------------------------


def test_provider_error_is_redacted_before_storage(client):
    resp = client.post("/api/projects", json={"intake": VALID_INTAKE})
    project_id = resp.json()["id"]

    leaking_error = ModelProviderError(
        "understanding: Anthropic-API-Fehler: 401 - authorization: Bearer sk-ant-api03-XXXXXXXXXXXXXXXXXXXX"
    )
    with patch("app.routers.projects.call_model", side_effect=leaking_error):
        resp = client.post(f"/api/projects/{project_id}/submit")

    assert resp.status_code == 200  # technischer Fehlschlag ist kein HTTP-Fehler des Endpunkts
    assert resp.json()["last_run_status"] == "FAILED"
    assert resp.json()["workflow_state"] == "UNDERSTANDING"

    # Der gespeicherte Fehlertext darf keinen Schlüssel/Bearer-Token enthalten.
    # (Der Fehlertext selbst ist nicht Teil der ProjectDetail-Response -
    # direkter DB-Check über die Test-Session.)
    import app.database as dbmod

    # Zugriff über dieselbe Engine wie der überschriebene Dependency:
    from app.main import app as fastapi_app

    db_gen = fastapi_app.dependency_overrides[dbmod.get_db]()
    db = next(db_gen)
    run = db.query(AgentRun).filter(AgentRun.project_id == project_id).first()
    assert run.status == "FAILED"
    assert "sk-ant-" not in run.error
    assert "[REDACTED]" in run.error
    db.close()


# --- AT-1.6: Retry ohne State-Verlust ---------------------------------------


def test_retry_after_failure_creates_new_run_and_keeps_old_one(client):
    resp = client.post("/api/projects", json={"intake": VALID_INTAKE})
    project_id = resp.json()["id"]

    with patch("app.routers.projects.call_model", side_effect=ModelProviderError("timeout")):
        resp = client.post(f"/api/projects/{project_id}/submit")
    assert resp.json()["workflow_state"] == "UNDERSTANDING"
    assert resp.json()["last_run_status"] == "FAILED"

    with patch("app.routers.projects.call_model", return_value=_result(READY_OUTPUT)):
        resp = client.post(f"/api/projects/{project_id}/retry")
    assert resp.status_code == 200
    assert resp.json()["workflow_state"] == "WAITING_FOR_USER_CONFIRMATION"
    assert resp.json()["last_run_status"] == "DONE"

    import app.database as dbmod
    from app.main import app as fastapi_app

    db = next(fastapi_app.dependency_overrides[dbmod.get_db]())
    runs = (
        db.query(AgentRun)
        .filter(AgentRun.project_id == project_id, AgentRun.role == "understanding")
        .order_by(AgentRun.attempt)
        .all()
    )
    assert [r.status for r in runs] == ["FAILED", "DONE"]
    assert [r.attempt for r in runs] == [1, 2]
    db.close()


def test_retry_without_prior_failure_is_rejected(client):
    resp = client.post("/api/projects", json={"intake": VALID_INTAKE})
    project_id = resp.json()["id"]
    resp = client.post(f"/api/projects/{project_id}/retry")
    assert resp.status_code == 409


# --- AT-1.7: Zustand übersteht einen simulierten Neustart -------------------


def test_state_survives_restart(test_engine, client):
    resp = client.post("/api/projects", json={"intake": VALID_INTAKE})
    project_id = resp.json()["id"]
    with patch("app.routers.projects.call_model", return_value=_result(READY_OUTPUT)):
        client.post(f"/api/projects/{project_id}/submit")
    client.post(f"/api/projects/{project_id}/understanding/confirm")

    # "Neustart" simulieren: frische Session/Engine auf derselben Datei,
    # ohne den bisherigen SessionLocal/Cache wiederzuverwenden.
    fresh_engine = create_engine(str(test_engine.url), connect_args={"check_same_thread": False})
    FreshSession = sessionmaker(bind=fresh_engine)
    db = FreshSession()
    project = db.get(Project, project_id)
    assert project.workflow_state == "RESEARCHING"
    db.close()
    fresh_engine.dispose()


# --- Kosten-Notbremse (Review 4 §4.2, hier bereits mit ausgeliefert) -------


def test_cost_ceiling_blocks_further_calls(client, monkeypatch):
    monkeypatch.setattr("app.routers.projects.MAX_MODEL_CALLS_PER_PROJECT", 0)

    resp = client.post("/api/projects", json={"intake": VALID_INTAKE})
    project_id = resp.json()["id"]

    with patch("app.routers.projects.call_model", return_value=_result(READY_OUTPUT)) as mocked:
        resp = client.post(f"/api/projects/{project_id}/submit")
        mocked.assert_not_called()

    assert resp.status_code == 423
    assert resp.json()["detail"]["error"]["code"] == "COST_LIMIT_EXCEEDED"
