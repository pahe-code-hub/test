# Phase 3 — Multi-Agent Planning (Architect + Challenger)

Auftrag für `phase2-builder` (Workspace `~/test`). Folge strikt
`PLAN → IMPLEMENT → TEST → REVIEW → CHECKPOINT` (Masterplan Abschnitt 40).
Phase 1 und Phase 2 sind **APPROVED** (siehe `docs/PHASE1_CHECKPOINT.md`,
`docs/PHASE2_CHECKPOINT.md`) — nicht anfassen, außer ein Bug wird dabei
zufällig entdeckt (dann separat melden, nicht im selben Commit fixen).

## PLAN — exakter Scope, nicht mehr und nicht weniger

Referenz: `MASTER_PLAN_v0.2.md` Abschnitt 9 (Architect), 10 (Challenger), 34
(Parallelisierung), `AGENT_PROMPTS.md` § `architect_v1`/`challenger_v1`,
`DATA_MODEL.md` § `architect`/`challenger`, `WORKFLOW_STATES.md` (State
`GENERATING_SOLUTIONS`), `ACCEPTANCE_TESTS.md` AT-3.1 bis AT-3.4.

Phase 3 implementiert **ausschließlich** den State `GENERATING_SOLUTIONS`:

* Zwei neue Rollen `architect`/`challenger`, Modellklasse **HIGH**
  (`claude-opus-5` laut `MODEL_CLASS_MAP`).
* Beide erhalten denselben Kontext (bestätigter Intake + Research-Ergebnis
  als `<external_research_data>`), **aber nicht gegenseitig ihr Ergebnis**
  — das ist kein Implementierungsdetail, sondern eine harte Anforderung
  (AT-3.1, per Code-Review-Kontrolle des Kontextaufbaus geprüft).
* Beide laufen **echt parallel**, nicht nacheinander (Abschnitt 34,
  AT-3.1/3.2). Getrennte Tabellen `architect`/`challenger`
  (`project_id` PK/FK, `output` JSON, `run_status` ∈
  `PENDING`/`RUNNING`/`DONE`/`FAILED`) — genau deshalb getrennte Zeilen
  statt eines gemeinsamen JSON-Blobs (Review 2 §2.2, verhindert
  Schreibkonflikte bei paralleler Ausführung).
* Übergang `GENERATING_SOLUTIONS → SYNTHESIZING` automatisch, sobald
  **beide** `run_status == DONE` sind (`WORKFLOW_STATES.md`). Der
  Synthesizer selbst ist **nicht** Teil dieses Auftrags (Phase 4) — genau
  wie Phase 1 an der Grenze zu `RESEARCHING` und Phase 2 an der Grenze zu
  `GENERATING_SOLUTIONS` gestoppt hat, stoppt Phase 3 an der Grenze zu
  `SYNTHESIZING`: der State wird gesetzt, aber kein Agent darin ausgeführt.
  Das Projekt bleibt dort "geparkt" bis Phase 4.

**Bewusst NICHT Teil dieses Auftrags:** Synthesizer, Critic, Evaluator,
Revision Agent, Final Builder, jede UI-Änderung über das bestehende
`ResearchPanel.tsx` hinaus, SSE/Live-Status (Phase 7).

## Bereits vorhandene Infrastruktur (wiederverwenden, nicht neu bauen)

* `call_model(role, model_class, system_prompt, input_context, output_schema, ...)`
  aus `app/model_provider.py` — funktioniert real verifiziert gegen den
  Gateway (`docs/PHASE1_CHECKPOINT.md` Abschnitt „Abschluss 2026-09-07").
  Für Architect/Challenger sind zwei weitere dedizierte Gateway-Agenten
  nötig (`MPA_OPENCLAW_AGENT_ID_ARCHITECT`/`MPA_OPENCLAW_AGENT_ID_CHALLENGER`)
  — das Anlegen dieser Agenten im Gateway ist **Infrastrukturaufgabe des
  Nutzers** (`openclaw agents add ...`), nicht deines. Code, der ohne
  gesetzte Env-Var hart fehlschlägt (kein stiller Fallback), ist bereits
  vorhanden (`_get_agent()`) — für die neuen Rollen genauso nutzen.
* `call_model()` ist absichtlich **nicht global gesperrt** (siehe Docstring
  in `_get_agent()`/`call_model()`) — exakt damit paralleles Aufrufen aus
  Architect und Challenger möglich ist. Für echte Parallelität in Python
  (FastAPI-Router sind synchron, `def` nicht `async def`) reicht ein
  `concurrent.futures.ThreadPoolExecutor(max_workers=2)` o. Ä. im Router,
  das beide `call_model()`-Aufrufe gleichzeitig startet — nicht
  nacheinander mit `await`/sequenziellem Aufruf.
* `wrap_external_research_data()` aus `app/external_data.py` — für den
  Research-Kontext in beiden Prompts wiederverwenden (gleicher
  Fremddaten-Schutz wie bei `research_v1`).
* `_run_understanding_agent`/`_run_research_agent` in
  `routers/projects.py` als Vorbild für Struktur (State setzen,
  `agent_runs`-Zeile anlegen, `call_model` aufrufen, Ergebnis
  persistieren, Fehler abfangen und in `agent_runs.status = FAILED`
  übersetzen, Secrets redigieren via `app/security.py`).

## IMPLEMENT

* Migration `0003_phase3_architect_challenger`: Tabellen `architect`,
  `challenger` gemäß `DATA_MODEL.md`.
* `backend/prompts/architect_v1.md`, `backend/prompts/challenger_v1.md` —
  Inhalt exakt nach `AGENT_PROMPTS.md` § `architect_v1`/`challenger_v1`
  (Output-Schema, Systemprompt-Kernpunkte).
* `app/schemas.py`: `ArchitectOutput`/`ChallengerOutput` (identisches
  Schema laut `AGENT_PROMPTS.md`: `approach`, `structure`, `components`,
  `interactions`, `technologies`, `risks`, `implementation_approach`,
  `open_points`).
* `routers/projects.py`: eine Funktion, die aus **beiden** Aufrufstellen
  (dem automatischen Übergang in `_run_research_agent` bei deaktiviertem
  Research-Gate, Zeile ~303, und `approve_research` bei aktiviertem Gate)
  aufgerufen wird, sobald `workflow_state = GENERATING_SOLUTIONS` gesetzt
  wird — beide bestehenden Aufrufstellen bereits vorhanden, nur die
  tatsächliche Agentenausführung fehlt noch (aktuell wird der State
  gesetzt, aber nichts läuft).
* `retry_last_step`: `role == "architect"`/`"challenger"`-Zweige ergänzen,
  die **nur den fehlgeschlagenen Zweig** erneut ausführen (AT-3.3) — der
  bereits erfolgreiche Zweig (`run_status == DONE`) bleibt unangetastet,
  nicht neu aufgerufen.
* `_to_project_detail`: `architect`/`challenger`-Ergebnisse in die
  Projekt-Detail-Antwort aufnehmen (API_CONTRACT.md Zeile 25 nennt sie
  bereits als Teil des vollständigen State).

## TEST

* Unit-Tests analog `test_phase1_workflow.py`/`test_phase2_research.py`:
  `call_model` gemockt, State-Übergänge geprüft (AT-3.4: beide Outputs
  schema-valide).
* Ein Test, der **erzwungene Gleichzeitigkeit** simuliert (künstliche
  Verzögerung eines der beiden gemockten `call_model`-Aufrufe) und prüft,
  dass beide Tabellenzeilen ohne `database is locked`-Fehler geschrieben
  werden (AT-3.2) — WAL-Modus ist bereits aktiv (`app/database.py`), aber
  das muss unter echter Parallelität nachgewiesen werden, nicht nur
  angenommen werden.
* Ein Test für AT-3.3 (Retry trifft nur den fehlgeschlagenen Zweig).
* Ein Test, der den Kontextaufbau beider Prompts prüft: Architect-Prompt
  darf keinen String aus dem Challenger-Output enthalten und umgekehrt
  (AT-3.1, Code-Review-Kontrolle als Assertion).

## REVIEW

Gegen AT-3.1–AT-3.4 und `SECURITY.md` (Fremddaten-Wrapper in beiden
Prompts korrekt angewendet?). Ehrlich dokumentieren, was in der eigenen
Sandbox nicht real verifiziert werden konnte (echte Parallelität gegen den
laufenden Gateway, analog zum bisherigen Muster) — das wird wie bisher vom
Nutzer/Claude-Code-Review nachgeholt.

## CHECKPOINT

`docs/PHASE3_CHECKPOINT.md` anlegen, gleicher Aufbau wie
`PHASE1_CHECKPOINT.md`/`PHASE2_CHECKPOINT.md`. Committen und pushen auf
`claude/test-akso67`.
