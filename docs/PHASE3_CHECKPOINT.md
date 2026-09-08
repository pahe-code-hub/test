# PHASE3_CHECKPOINT.md

Nachweis für **Phase 3 — Multi-Agent Planning** aus
`MASTER_PLAN_v0.2.md` Abschnitt 35, umgesetzt nach
`PLAN → IMPLEMENT → TEST → REVIEW → CHECKPOINT`.

## PLAN

Umfang: ausschließlich Ausführung des States `GENERATING_SOLUTIONS` mit den
Rollen `architect_v1` und `challenger_v1`, Modellklasse `HIGH`, echtem
parallelem Fan-out, getrennten Ergebnistabellen und anschließendem Fan-in nach
`SYNTHESIZING`. Der Synthesizer selbst und alle Rollen aus Phase 4–6 wurden
bewusst nicht implementiert. Frontend und SSE wurden nicht verändert.

## IMPLEMENT

* Migration `0003_phase3_architect_challenger`: additive Tabellen
  `architect` und `challenger` mit getrennten `project_id`-Primärschlüsseln,
  JSON-Output und `run_status`.
* `app/models.py` und `app/schemas.py`: ORM-Modelle sowie identische,
  strukturierte `ArchitectOutput`-/`ChallengerOutput`-Schemas nach
  `AGENT_PROMPTS.md`.
* `prompts/architect_v1.md` und `prompts/challenger_v1.md`: getrennte
  Rollenanweisungen mit den verbindlichen Robustheits-/Einfachheitsregeln und
  Prompt-Injection-Hinweisen.
* `routers/projects.py`:
  * bildet einmalig einen für beide Rollen identischen Kontext aus bestätigtem
    Intake und Research-Ergebnis;
  * kapselt das gesamte Research-Ergebnis mit
    `<external_research_data>`;
  * startet beide `call_model()`-Aufrufe über einen
    `ThreadPoolExecutor(max_workers=2)` parallel;
  * verwendet für die anschließenden Rollen-Schreibvorgänge getrennte
    SQLAlchemy-Sessions und Transaktionen, ohne eine Session zwischen Threads
    zu teilen;
  * setzt `SYNTHESIZING` erst, wenn beide `run_status == DONE` sind, und
    führt dort keinen Agenten aus;
  * wird sowohl nach Research ohne Gate als auch nach
    `POST .../research/approve` aufgerufen;
  * wiederholt bei `POST .../retry` ausschließlich den fehlgeschlagenen
    Architect- oder Challenger-Zweig.
* `GET /api/projects/{id}` enthält die beiden Outputs und Run-Status.
* Dedizierte Gateway-Agenten bleiben Pflicht:
  `MPA_OPENCLAW_AGENT_ID_ARCHITECT` und
  `MPA_OPENCLAW_AGENT_ID_CHALLENGER`; es gibt keinen Fallback-Agenten.

## TEST

Neu in `tests/test_phase3_planning.py`:

| Test | Nachweis |
|---|---|
| `test_approval_runs_both_roles_in_parallel_with_identical_isolated_context` | AT-3.1/3.2: Barrier-erzwungene Überlappung, identischer Fremddaten-Kontext, getrennte Ergebnisse, überlappende Run-Zeiten und kein DB-Lock |
| `test_disabled_gate_automatically_runs_phase3_and_stops_at_synthesizing` | beide Eintrittspfade und Parken an der Phase-4-Grenze |
| `test_unequal_model_latencies_persist_both_branches_independently` | stark unterschiedliche Abschlusszeiten verlieren kein Ergebnis und erreichen weiterhin `SYNTHESIZING` |
| `test_retry_repeats_only_failed_challenger_branch` | AT-3.3: erfolgreicher Architect bleibt unverändert, nur Challenger erhält Attempt 2 |
| `test_solution_output_schema_rejects_incomplete_results` | AT-3.4 für beide strukturierten Schemas |

Die bestehenden Phase-2-Tests mocken den neuen Phase-3-Aufruf an ihrer
bisherigen Phasengrenze, damit ihre ursprünglichen Assertions isoliert bleiben.

Tatsächlicher Ausführungsstand in dieser Sandbox:

* `python3 -m compileall -q backend/app backend/tests backend/alembic`:
  **bestanden**.
* `python3 -m py_compile` für Router, Phase-3-Test und Migration:
  **bestanden**.
* `git diff --check`: **bestanden**.
* `python3 -m pytest tests/ -v`: **BLOCKED** mit
  `No module named pytest`.
* `.venv/bin/python -m pytest tests/ -v`: **BLOCKED** mit
  `No module named pytest`; das vorhandene Virtualenv verweist weiterhin auf
  die inkompatible Python-3.11-Laufzeit.
* `.venv/bin/python -m alembic upgrade head`: **BLOCKED**, weil Alembic in
  dieser Laufzeit nicht ausführbar ist.
* Ein realer Paralleltest gegen den Gateway wurde nicht ausgeführt. Die dafür
  erforderlichen dedizierten Architect-/Challenger-Agenten sind laut Auftrag
  Nutzer-Infrastruktur und nicht Teil dieser Implementierung.
* Nachgelagerte Review-Umgebung: ursprüngliche Phase-3-Suite **33/33 grün**,
  Migration verifiziert. Der anschließend ergänzte Test für ungleiche
  Modelllatenzen konnte in dieser Sandbox wegen des fehlenden Pytest-Moduls
  nur per `compileall`/`py_compile`, nicht als Pytest-Lauf geprüft werden.

## REVIEW

Prüfung gegen AT-3.1–AT-3.4 und `SECURITY.md`:

* **AT-3.1:** Fan-out ist im Code tatsächlich parallel. Beide Futures erhalten
  exakt denselben unveränderlichen Kontext; weder Output kann beim
  Kontextaufbau des anderen existieren. Der automatisierte Test erzwingt die
  Überlappung, konnte in dieser Sandbox aber nicht ausgeführt werden.
* **AT-3.2:** Rollen schreiben über getrennte Tabellen, Sessions und
  Transaktionen. Nur der Mock im Parallelitätstest synchronisiert den Beginn
  beider Modellaufrufe; der Produktionspfad enthält keine Barrier und jeder
  Zweig persistiert unabhängig, sobald sein Aufruf beendet ist. Der reale
  Testlauf bleibt wegen der Python-Toolchain offen; kein grünes Ergebnis wird
  angenommen.
* **AT-3.3:** Der Retry wählt einen fehlgeschlagenen Phase-3-Lauf und ruft den
  Fan-out-Helfer mit genau dieser einen Rolle auf. Ein bereits erfolgreicher
  Zweig wird übersprungen und nicht überschrieben.
* **AT-3.4:** Beide Rollen besitzen vollständige Pydantic-Schemas; unvollständige
  Outputs werden im Test abgelehnt.
* **Security:** Research-Zusammenfassung und Quellen werden für beide Rollen
  ausschließlich über `wrap_external_research_data()` eingebettet. Die
  Prompt-Dateien wiederholen, dass Fremddaten keine Anweisungen sind.
* Keine Phase-4+-Rolle, kein Synthesizer-Aufruf, keine UI- oder SSE-Änderung
  wurde eingeführt.

Beim Review wurde kein separater Phase-1/2-Bug gefunden.

Ein Folge-Review fand eine irrtümlich im Produktionspfad platzierte
`threading.Barrier(timeout=5)`, durch die unterschiedlich schnelle Modellläufe
beide Ergebnisse verlieren konnten. Die Barrier wurde vollständig aus
`_run_solution_agents()` entfernt. Ein Regressionstest startet beide
Modell-Mocks gemeinsam, lässt Architect nach 0,01 Sekunden und Challenger erst
nach 0,3 Sekunden fertig werden und verlangt dennoch zwei persistierte
`DONE`-Ergebnisse sowie den Übergang nach `SYNTHESIZING`.

## CHECKPOINT

Phase 3 ist code-seitig vollständig implementiert und an der Grenze
`SYNTHESIZING` geparkt. Eine endgültige Freigabe wird hier nicht behauptet:
offen bleiben die Ausführung der Testsuite und Migration in einer kompatiblen
Python-Umgebung sowie optional der reale Parallelitätsnachweis gegen zwei vom
Nutzer eingerichtete HIGH-Gateway-Agenten. Die endgültige Freigabe bleibt beim
Nutzer/Claude-Code-Review.
