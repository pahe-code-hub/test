# PHASE7_CHECKPOINT.md

**Status: PHASE 7 = APPROVED** (Nutzerfreigabe 2026-09-10, zusammen mit
Phase 5/6 auf Basis des realen Ende-zu-Ende-Laufs Commit `fb0f953` —
74/74 Tests unabhängig nachvollzogen, keine offenen Vorbehalte).

Nachweis für **Phase 7 — UX/Betrieb** aus `MASTER_PLAN_v0.1.md` Abschnitt
35 (Live-Status, Kostenanzeige, Retry, Prompt-Versionierung,
Projektübersicht, Logging), umgesetzt nach `PLAN → IMPLEMENT → TEST →
REVIEW → CHECKPOINT`.

## PLAN

Von den sechs in Abschnitt 35 genannten Themen waren vier bereits durch
frühere Phasen vollständig erledigt (siehe `DATA_MODEL.md`: "Phase 7/8:
keine Schemaänderung erwartet"):

* **Retry** — seit Phase 1, um jede neue Rolle erweitert (zuletzt Phase 6:
  `final_builder`-Zweig).
* **Prompt-Versionierung** (ADR-009) — `prompts/*_v1.md` + `agent_runs.
  prompt_id`, kein `active`-Flag-Schema nötig (AT-7.3).
  seit Phase 1.
* **Projektübersicht** — `GET /api/projects` seit Phase 1.
* **Logging/Auditierbarkeit** — `agent_runs`-Tabelle (ADR-010) seit
  Phase 1, um jede Rolle erweitert.
* **Kosten-Notbremse** (AT-7.2) — `_check_cost_ceiling()` seit Phase 1,
  vor jedem der inzwischen 8 Agentenaufrufe geprüft.

Neu in Phase 7: **Live-Status** (SSE, `GET /events`, AT-7.1) und
**Kostenanzeige** (`GET /cost`, API_CONTRACT.md § Kosten, Abschnitt 32).
Keine Schema-Änderung nötig — beide Endpunkte lesen ausschließlich
bestehende Spalten (`projects.total_model_calls`/
`total_estimated_cost_usd`, `agent_runs.*`).

**Scope-Entscheidung:** Events werden gezielt an den bereits etablierten
Transaktionsgrenzen jeder `_run_<rolle>_agent()`-Funktion publiziert
(AgentRun-Anlage = `agent_run_started`, abschließendes `db.commit()` =
`agent_run_completed`/`agent_run_failed` + `state_changed` + ggf.
`cost_updated`) — nicht an jedem einzelnen Guard-Übergang ohne
Agentenlauf (z.B. `understanding/correct`), da dort der HTTP-Response
selbst bereits sofort den neuen State trägt und "Live-Status" (Abschnitt
26) explizit für länger dauernde Schritte gilt, die die UI nicht
blockieren dürfen.

## IMPLEMENT

* `app/schemas.py`: `CostByRole`, `CostOut` (REST).
* `app/routers/projects.py`:
  * Leichtgewichtiges In-Prozess-Pub/Sub (`_event_subscribers`,
    `_event_lock`, `_publish()`) statt Message-Broker — V1 ist
    Single-User/lokal in einem Prozess (ADR-004). Endpunkte laufen als
    sync `def` in FastAPIs Threadpool, ein offener SSE-Stream blockiert
    daher keine parallel laufenden Agentenläufe anderer Requests.
  * `_publish_run_started()`/`_publish_run_result()`: an allen 7
    sequenziellen `_run_<rolle>_agent()`-Funktionen ergänzt (nach
    `db.add(run)`/`db.flush()` bzw. nach dem abschließenden `db.commit()`).
    `_run_solution_agents()` (Architect/Challenger parallel) bekam ein
    eigenes, auf die Thread-Koordination zugeschnittenes Muster:
    `agent_run_started` für beide Rollen direkt nach der ersten
    RUNNING-Commit, `agent_run_completed`/`agent_run_failed` pro Rolle aus
    der jeweiligen Branch-Session heraus (sobald der jeweilige Future
    fertig ist), `cost_updated`/`state_changed` einmalig nach der
    äußeren Aggregation (da `project.total_model_calls` erst dort
    korrekt aufsummiert vorliegt).
  * `GET /{id}/cost`: Aufschlüsselung je Rolle über
    `agent_runs.status = DONE` gruppiert (`FAILED`-Versuche trugen keine
    erfolgreichen Kosten bei).
  * `GET /{id}/events`: SSE-Endpunkt, registriert einen `queue.Queue`-
    Subscriber, gibt eine `StreamingResponse` über die eigenständige
    (nicht als Closure definierte) Generatorfunktion `_sse_stream()`
    zurück — bewusst als Modul-Funktion statt Closure, um sie direkt
    (ohne ASGI-/TestClient-Stack) testen zu können (siehe TEST).
    Sofortiges `: connected`-Handshake-Byte, danach Events oder alle 15s
    ein Keep-Alive-Kommentar; Cleanup (Subscriber-Entfernung) im
    `finally`-Block bei Verbindungsende.

## TEST

Neu in `tests/test_phase7_ops.py` (6 Tests):

| Test | Nachweis |
|---|---|
| `test_publish_delivers_to_all_subscribers_of_a_project_only` | Pub/Sub isoliert nach `project_id` |
| `test_submit_publishes_agent_run_and_state_changed_events` | AT-7.1 (sinngemäß): ein echter Router-Aufruf publiziert `agent_run_started`/`_completed`/`cost_updated`/`state_changed` |
| `test_sse_stream_generator_delivers_handshake_then_published_event` | SSE-Wire-Mechanik (Handshake, `event:`/`data:`-Zeilen, Cleanup) |
| `test_events_endpoint_returns_404_for_unknown_project` | Guard ohne Hang-Risiko (404 vor Stream-Start) |
| `test_cost_endpoint_breaks_down_by_role` | `GET /cost` liefert korrekte Aufschlüsselung |
| `test_cost_endpoint_unknown_project_returns_404` | Guard |

**Wichtiger Test-Infrastruktur-Fund:** Der erste Anlauf, den SSE-Stream
end-to-end über `TestClient.stream(...)` zu lesen, während parallel ein
zweiter `TestClient`-Request die auslösende Aktion schickt, **hing
unbegrenzt** — isoliert reproduziert: `with client.stream(...) as resp:`
blockiert bereits beim Betreten des Context-Managers, weil der
Test-Transport (`portal.call(self.app, ...)`) erst zurückkehrt, wenn der
komplette ASGI-Response-Body-Iterator erschöpft ist, nicht nach dem
ersten Chunk - gegen einen absichtlich nie endenden Generator (Keep-Alive-
Schleife) also niemals. Behoben, indem die Stream-Generatorfunktion
(`_sse_stream()`) als eigenständige Modul-Funktion statt Router-Closure
definiert und direkt per `next()` iteriert wird, ohne den ASGI-/
TestClient-Stack zu durchlaufen — **in Memory festgehalten**, damit
zukünftige SSE-Tests in diesem Projekt nicht denselben Hang erneut
provozieren.

Ausführungsstand (echte Laufzeitumgebung, kein Sandbox-Vorbehalt):

* `python -m py_compile` über alle geänderten Dateien: **bestanden**.
* `python -m pytest tests/ -v`: **74 von 74 bestanden** (68 bestehende +
  6 neue), Laufzeit ~10s, **kein realer Netzwerk-/Gateway-Aufruf**, kein
  Hang.
* Keine Migration nötig (keine Schema-Änderung, s.o.) — bestätigt durch
  vollständigen Reread von `DATA_MODEL.md` § Migrationen.

## REVIEW

Prüfung gegen AT-7.1–AT-7.3:

* **AT-7.1** (sinngemäß, kein echter 2s-Latenztest): `state_changed`
  wird beim tatsächlichen State-Wechsel synchron im selben Request
  publiziert, in dem der Wechsel passiert — es gibt keine Verzögerung
  durch Polling oder einen separaten Broadcast-Zyklus, die publizierende
  Zeile liegt unmittelbar nach dem jeweiligen `db.commit()`.
* **AT-7.2:** durch die bestehende, in jeder vorigen Phase getestete
  `_check_cost_ceiling()`-Funktion bereits erfüllt — keine neue
  Implementierung in Phase 7 nötig, hier nur bestätigt.
* **AT-7.3:** `prompts/*_v1.md` (9 Dateien: understanding, research,
  architect, challenger, synthesizer, critic, evaluator, revision,
  final_builder) liegen versioniert im Repository, referenziert über
  `agent_runs.prompt_id` — kein `active`-Flag-Schema, wie in ADR-009
  festgelegt.
* Keine Phase-8-Funktionalität (PDF/DOCX/JSON-Export, Windows-Paket)
  wurde eingeführt.

## CHECKPOINT

## Abschluss 2026-09-10 (real, auf dem Server des Nutzers)

`GET /cost` real gegen das komplette Phase-5/6-E2E-Projekt (siehe
`docs/PHASE6_CHECKPOINT.md`) abgerufen: liefert die korrekte
Gesamtsumme (10 Aufrufe, \$2.893205) aufgeschlüsselt auf alle 9 Rollen
inkl. `evaluator` mit 2 Aufrufen (ein `FAILED`-Versuch zählt nicht mit,
da die Aufschlüsselung nur `status = DONE` filtert — genau wie geplant).
Die Pub/Sub-Instrumentierung (`_publish_run_started`/`_publish_run_result`)
lief während des gesamten realen Laufs durch alle 10 Agentenaufrufe ohne
Fehler (keine Exception im Server-Log durch die Publish-Aufrufe) - ein
zusätzlicher Live-Rauchtest der Instrumentierung selbst, auch ohne einen
tatsächlich angeschlossenen SSE-Client während dieses Laufs.

## CHECKPOINT

Phase 7 ist vollständig implementiert, mocked getestet (74/74) und der
Kosten-Endpunkt zusätzlich real gegen einen kompletten Projektdurchlauf
verifiziert. Die SSE-Mechanik selbst bleibt beim dokumentierten
Generator-Unit-Test (TestClient kann keine Endlos-Streams lesen, siehe
TEST oben) - das Pub/Sub lief im realen Lauf nachweislich fehlerfrei
durch. Die endgültige Freigabe bleibt beim Nutzer.
