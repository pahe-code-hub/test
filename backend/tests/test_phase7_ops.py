"""Phase 7 - Live-Status (SSE), Kostenanzeige. Kosten-Notbremse (AT-7.2)
und Prompt-Versionierung (AT-7.3) sind bereits seit Phase 1/3 vollstaendig
umgesetzt (siehe test_phase1_workflow.py::test_cost_ceiling_blocks_further_calls
sowie die ADR-009-Struktur von prompts/*_v1.md) - hier nur noch eine
gezielte Bestaetigung je Kriterium, keine Doppelabdeckung.
"""
import queue
import threading
import time
from unittest.mock import patch

from app.routers.projects import _event_subscribers, _event_lock, _publish, _sse_stream
from tests.conftest import VALID_INTAKE
from tests.test_phase4_synthesis import READY, result


def test_publish_delivers_to_all_subscribers_of_a_project_only():
    q_a1 = queue.Queue()
    q_a2 = queue.Queue()
    q_b = queue.Queue()
    with _event_lock:
        _event_subscribers.setdefault("proj-a", []).extend([q_a1, q_a2])
        _event_subscribers.setdefault("proj-b", []).append(q_b)
    try:
        _publish("proj-a", "state_changed", {"workflow_state": "DRAFT"})
        assert q_a1.get(timeout=1) == ("state_changed", {"workflow_state": "DRAFT"})
        assert q_a2.get(timeout=1) == ("state_changed", {"workflow_state": "DRAFT"})
        assert q_b.empty()  # nicht Subscriber von proj-a
    finally:
        with _event_lock:
            _event_subscribers.pop("proj-a", None)
            _event_subscribers.pop("proj-b", None)


def test_submit_publishes_agent_run_and_state_changed_events(client):
    """AT-7.1 (sinngemaess, ohne echten 2s-Latenztest): ein tatsaechlicher
    State-Wechsel (submit -> understanding_v1) publiziert
    agent_run_started/agent_run_completed/cost_updated/state_changed auf
    dem projektbezogenen Event-Bus - direkt am Subscriber-Queue geprueft,
    ohne den mit der TestClient-Transportschicht riskanten Umweg über
    zwei parallele HTTP-Requests (Stream + auslösender Call koennen sich
    sonst gegenseitig blockieren)."""
    project_id = client.post("/api/projects", json={"intake": VALID_INTAKE}).json()["id"]

    q: queue.Queue = queue.Queue()
    with _event_lock:
        _event_subscribers.setdefault(project_id, []).append(q)
    try:
        with patch("app.routers.projects.call_model", return_value=result(READY)):
            client.post(f"/api/projects/{project_id}/submit")

        events = []
        while True:
            try:
                events.append(q.get_nowait())
            except queue.Empty:
                break

        names = [e for e, _ in events]
        assert "agent_run_started" in names
        assert "agent_run_completed" in names
        assert "cost_updated" in names
        assert "state_changed" in names
        state_changed = next(d for e, d in events if e == "state_changed")
        assert state_changed["workflow_state"] == "WAITING_FOR_USER_CONFIRMATION"
    finally:
        with _event_lock:
            subs = _event_subscribers.get(project_id)
            if subs and q in subs:
                subs.remove(q)


def test_sse_stream_generator_delivers_handshake_then_published_event():
    """Bestaetigt die tatsaechliche SSE-Wire-Mechanik (Handshake, Event-/
    Data-Zeilen) durch direkte Iteration des Produktions-Generators
    `_sse_stream` - Starlettes TestClient kann einen nie endenden Stream
    (Keep-Alive-Schleife) nicht inkrementell lesen (`client.stream(...)`
    wartet intern auf den vollstaendigen Response-Body und haengt sich
    dabei auf, im ersten Anlauf reproduziert), daher hier ohne den
    ASGI-/HTTP-Layer getestet - derselbe Generator, den die Route
    tatsaechlich an StreamingResponse uebergibt."""
    project_id = "sse-test-project"
    subscriber: queue.Queue = queue.Queue()
    with _event_lock:
        _event_subscribers.setdefault(project_id, []).append(subscriber)
    gen = _sse_stream(project_id, subscriber)
    try:
        assert next(gen) == ": connected\n\n"

        def publish_soon():
            time.sleep(0.1)
            _publish(project_id, "state_changed", {"workflow_state": "UNDERSTANDING"})

        threading.Thread(target=publish_soon, daemon=True).start()
        chunk = next(gen)
        assert chunk == 'event: state_changed\ndata: {"workflow_state": "UNDERSTANDING"}\n\n'
    finally:
        gen.close()  # loest den finally-Block in _sse_stream aus (Cleanup)

    with _event_lock:
        assert project_id not in _event_subscribers  # Subscriber wurde entfernt


def test_events_endpoint_returns_404_for_unknown_project(client):
    """Kein Hang-Risiko: der 404 wird geworfen, bevor der unendliche
    Stream ueberhaupt beginnt."""
    resp = client.get("/api/projects/does-not-exist/events")
    assert resp.status_code == 404


def test_cost_endpoint_breaks_down_by_role(client):
    project_id = client.post("/api/projects", json={"intake": VALID_INTAKE}).json()["id"]
    with patch("app.routers.projects.call_model", return_value=result(READY)):
        client.post(f"/api/projects/{project_id}/submit")

    resp = client.get(f"/api/projects/{project_id}/cost")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_model_calls"] == 1
    assert body["by_role"]["understanding"]["calls"] == 1
    assert body["by_role"]["understanding"]["estimated_cost_usd"] > 0


def test_cost_endpoint_unknown_project_returns_404(client):
    resp = client.get("/api/projects/does-not-exist/cost")
    assert resp.status_code == 404
