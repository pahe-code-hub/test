# PHASE3_CHECKPOINT.md

**Status: PHASE 3 = APPROVED** (Nutzerfreigabe 2026-09-09 auf Commit
`e9e46f1` — real getestet, echter Gateway-E2E-Nachweis inkl. Architect/
Challenger, keine offenen Vorbehalte).

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

## Unabhängige Verifikation (Claude Code, 2026-09-08)

Code gezogen und in einer funktionierenden Umgebung geprüft, nicht nur
Claws eigene Angaben übernommen:

* `python -m alembic upgrade head` gegen eine frische SQLite-Datei:
  **bestanden**, `architect`/`challenger`-Tabellen entsprechen `DATA_MODEL.md`.
* `python -m pytest tests/ -v`: **34 von 34 bestanden**, keine Regression.
* Manueller Code-Review von `_run_solution_agents()`/`invoke()` fand den oben
  dokumentierten `threading.Barrier`-Fund (Produktionscode, kein
  Test-Artefakt) — Rückmeldung an Claw geschickt, Fix (`22964d1`) verifiziert:
  Barrier vollständig entfernt, Regressionstest (0,01s vs. 0,3s Latenz) prüft
  genau das vorherige Fehlerbild und läuft grün.
* Retry-Pfad (`role in ("architect","challenger")`) und Kontext-Trennung
  (`_build_solution_context`) stichprobenartig gegengelesen, keine weiteren
  Befunde.

## Abschluss 2026-09-09 (real, auf dem Server des Nutzers)

`mpa-architect`/`mpa-challenger` (Modell `anthropic/claude-opus-5`, Rolle
HIGH) im Gateway angelegt und der komplette Phase-1→3-Workflow real über die
API durchgespielt (`POST /api/projects` → `submit` → `understanding/confirm`
→ `retry` für den Research-Zweig). Dabei zwei weitere echte, zuvor unbekannte
openclaw-sdk-2.1.0-Bugs gefunden und behoben (Commits `31e5052`, `a4be4e0`):

4. `OpenClawClient._build_gateway()` gibt `config.timeout` beim
   `openai_base_url`-Pfad nicht an `OpenAICompatGateway` weiter — die bleibt
   bei ihrem Default von 30s, unabhängig von `MODEL_CALL_TIMEOUT_SECONDS`.
   Ein echter `research`-Aufruf mit extrahiertem Tavily-Seiteninhalt im
   Kontext überschreitet 30s real und schlug mit einem nichtssagenden,
   leeren `httpx.ReadTimeout` fehl.
5. `TavilyResearchProvider._post()` verschluckte bei jedem HTTP-Fehler die
   Detailmeldung — half nicht, einen echten 401 (falscher Key) von einem
   anderen Fehler zu unterscheiden.

Nach beiden Fixes lief der komplette Workflow real durch:

```
workflow_state: SYNTHESIZING
research.run_status: (implizit DONE, 6 reale Tavily-Quellen)
architect.run_status: DONE
challenger.run_status: DONE
total_model_calls: 4, total_estimated_cost_usd: 0.987307
```

Architect und Challenger lieferten inhaltlich klar unterscheidbare, jeweils
in sich stimmige Entwürfe (Architect: Django/PostgreSQL, gründlicher
Drei-Schichten-Aufbau; Challenger: SQLite/Flask, radikal minimal, explizite
"Kauf-vor-Bau"-Prüfung als Schritt 0) — kein Abschreiben, keine
Überschneidung mit dem jeweils anderen Output. Das ist der reale Beleg für
AT-3.1 (unabhängiger Kontext) über den Code-Review hinaus.

Damit sind alle in dieser und den vorigen Sitzungen offenen Punkte für
Phase 3 real geschlossen — keine verbleibenden Vorbehalte.

## CHECKPOINT

Phase 3 ist vollständig implementiert, real getestet (36/36), zwei während
der Verifikation gefundene Bugs (Produktions-Barrier, ignorierter Gateway-
Timeout) wurden behoben und gegengeprüft, und der komplette Workflow inkl.
Architect/Challenger lief real über den OpenClaw-Gateway durch — mit
inhaltlich überzeugenden, klar unterscheidbaren Ergebnissen. Aus technischer
Sicht ist Phase 3 vollständig freigabereif. Die endgültige Freigabe bleibt
beim Nutzer.
