# PHASE4_CHECKPOINT.md

**Status: Implementiert, mocked getestet — echter Gateway-E2E-Test steht
aus.** Freigabe (APPROVED) bleibt wie bei den vorigen Phasen beim Nutzer.

Nachweis für **Phase 4 — Synthese** aus `MASTER_PLAN_v0.2.md` Abschnitt 35,
umgesetzt nach `PLAN → IMPLEMENT → TEST → REVIEW → CHECKPOINT`.

## PLAN

Umfang: `synthesizer_v1` (Modellklasse HIGH), automatisch ausgeführt sobald
`GENERATING_SOLUTIONS` mit beiden Zweigen `DONE` den Grenz-State
`SYNTHESIZING` erreicht (bislang, seit Phase 3, ein reiner Park-State ohne
Agentenausführung), sowie Nutzerfreigabe 2
(`WAITING_FOR_SYNTHESIS_APPROVAL` → „ZIELKONZEPT FREIGEBEN" /
„ÄNDERUNGSWUNSCH"). Bewusst **nicht** implementiert: Critic/Evaluator/
Revision/Final Builder (Phase 5/6) — `synthesis/approve` parkt im
Zielzustand `REVIEWING`, ohne `critic_v1` auszuführen (`API_CONTRACT.md`
sieht das dort vor, das bleibt Phase 5), exakt dieselbe Scope-Grenze wie
zuvor beim `SYNTHESIZING`-Park-State in Phase 3. Frontend und SSE wurden
nicht verändert.

Codebase-Exploration und Design wurden vor der Implementierung über zwei
Explore-Agenten (Router-/Schema-/Migrations-/Prompt-/Testmuster) und einen
Plan-Agenten (Designfragen: Versionierung, `referenced_by_synthesis`-Flag,
`hint`-Platzierung) gegen den echten Code verifiziert.

## IMPLEMENT

* Migration `0004_phase4_synthesis`: additive Tabelle `synthesis`
  (`project_id`, `version`, `output`, `approved_at`; PK
  `(project_id, version)`), Multi-Versionen- statt Single-Row-Pattern
  (anders als `architect`/`challenger`, die nur wegen der Thread-
  Koordination im Fan-out/Fan-in eine Single-Row-Platzhalterzeile brauchen).
* `app/models.py`: ORM-Modell `Synthesis`.
* `app/schemas.py`: `SynthesisOutput`/`SynthesisExistingSolution` (Agenten-
  Output-Schema nach `AGENT_PROMPTS.md` § `synthesizer_v1`), `SynthesisOut`
  (REST), `SynthesisChangeRequest` (REST-Body, `comment` **Pflichtfeld** -
  anders als das optionale `ResearchRerun.comment`, da `API_CONTRACT.md`
  hier kein `| null` kennt). `ProjectDetail` um `synthesis` und `hint`
  erweitert.
* `prompts/synthesizer_v1.md`: Rolle „Chief Solution Architect", Prosa-Stil
  identisch zu `architect_v1.md`/`challenger_v1.md`, inkl. wortwörtlichem
  `<external_research_data>`-Warnabsatz.
* `app/state_machine.py`: neue Konstanten `WAITING_FOR_SYNTHESIS_APPROVAL`,
  `REVIEWING` (letzterer nur als Zielzustand, Critic hier bewusst nicht
  ausgeführt).
* `app/routers/projects.py`:
  * `_build_synthesis_context()`: bestätigter Intake, Research-
    Zusammenfassung **inklusive `research_sources.id`** (im Gegensatz zu
    `_build_solution_context`, das `id` für Architect/Challenger bewusst
    nicht braucht — eigene, unveränderte Funktion, um den bereits
    abgenommenen Phase-3-Code/-Tests nicht anzufassen), plus
    `architect.output`/`challenger.output` **außerhalb** des
    `<external_research_data>`-Blocks (eigene Agenten-Ergebnisse, keine
    externen Rohdaten, SECURITY.md §3);
  * `_run_synthesis_agent()`: Cost-Ceiling-Check, `AgentRun`-Anlage,
    `call_model(role="synthesizer", model_class="HIGH", ...)`,
    **Referentielle-Integritäts-Prüfung** von
    `existing_solutions_open_source[].source_id` gegen die tatsächlich im
    Kontext gezeigten `research_sources.id`-Werte (AT-4.1) **vor** jeder
    Persistierung, neue `Synthesis`-Zeile nur bei Erfolg (kein Platzhalter
    bei `FAILED` — dadurch ist `next_version = MAX(version)+1` bei
    Erstlauf, technischem Retry und Änderungswunsch einheitlich korrekt,
    ohne Sonderfallcode), `referenced_by_synthesis` wird bei jedem
    erfolgreichen Lauf für das Projekt komplett neu berechnet (nicht
    kumulativ über Versionen hinweg — nur `version = MAX(version)` ist
    laut `DATA_MODEL.md` aktuell gültig, und der Final Builder (Phase 6)
    wird nur diese Version sehen);
  * Trigger: `_run_solution_agents()` ruft nach dem Setzen von
    `SYNTHESIZING` automatisch `_run_synthesis_agent()` — exakt das
    Self-Chaining-Muster, mit dem `_run_research_agent()` bereits bei
    deaktiviertem Research-Gate in `_run_solution_agents()` kettet;
  * `POST /{id}/synthesis/approve`: Guard `WAITING_FOR_SYNTHESIS_APPROVAL`,
    setzt `approved_at` auf die aktuell gültige Version, → `REVIEWING`;
  * `POST /{id}/synthesis/change-request`: Guard
    `WAITING_FOR_SYNTHESIS_APPROVAL`, `synthesis_revision_count += 1`,
    → `SYNTHESIZING`, ruft `_run_synthesis_agent()` mit dem Nutzerkommentar
    erneut auf, liefert ab Runde 3 zusätzlich `hint` **nur in dieser
    Antwort** (nicht generisch bei jedem `GET`, `API_CONTRACT.md:25` zählt
    die GET-Felder explizit ohne `hint` auf);
  * `retry`: neuer `synthesizer`-Zweig, keine Sonderfallsuche nötig
    (sequenzielle Rolle wie `understanding`/`research`, kein
    Parallelitäts-Fallback wie bei `architect`/`challenger`);
  * `_to_project_detail()`: `synthesis`-Feld ergänzt.
* `tests/test_phase3_planning.py`: vier bestehende Tests, die den
  Übergang nach `SYNTHESIZING` auslösen, mocken jetzt zusätzlich
  `_run_synthesis_agent` (analog zum bereits bestehenden
  `_run_solution_agents`-Mock in `test_phase2_research.py`), damit sie bei
  ihrer eigenen Phasengrenze isoliert bleiben.

## TEST

Neu in `tests/test_phase4_synthesis.py` (10 Tests):

| Test | Nachweis |
|---|---|
| `test_synthesis_runs_automatically_and_reaches_waiting_approval` | automatischer Übergang `SYNTHESIZING` → `WAITING_FOR_SYNTHESIS_APPROVAL`, Version 1 persistiert |
| `test_fabricated_source_id_is_rejected` | AT-4.1: erfundene `source_id` → Lauf `FAILED`, State bleibt `SYNTHESIZING` |
| `test_referenced_by_synthesis_flag_recomputed_not_accumulated` | Flag wird pro Version neu berechnet, nicht kumulativ |
| `test_approve_transitions_to_reviewing` / `test_approve_guard_rejects_wrong_state` | Nutzerfreigabe 2, Guard |
| `test_change_request_creates_new_version_and_hint_from_round_three` / `..._guard_rejects_wrong_state` | AT-4.2: neue Version statt Überschreiben, `hint` ab Runde 3 nur in der change-request-Antwort |
| `test_retry_repeats_only_failed_synthesizer` | technischer Retry wiederholt ausschließlich die fehlgeschlagene Synthesizer-Rolle |
| `test_cost_ceiling_exceeded_during_change_request_leaves_revision_count_incremented` | Kosten-Notbremse während `change-request` (bisher bei `research/rerun` ungetestete Lücke, hier geschlossen) |
| `test_synthesis_output_schema_rejects_incomplete_result` | AT-4.1-Grundlage: Schema erzwingt Vollständigkeit |

Ausführungsstand (echte Laufzeitumgebung, kein Sandbox-Vorbehalt):

* `python -m py_compile` über alle neuen/geänderten Dateien: **bestanden**.
* `python -m alembic upgrade head` gegen eine frische SQLite-Datei:
  **bestanden**, `synthesis`-Tabelle entspricht exakt `DATA_MODEL.md`.
* `python -m pytest tests/ -v`: **46 von 46 bestanden** (36 bestehende +
  10 neue), Laufzeit ~5s, **kein realer Netzwerk-/Gateway-Aufruf** (nach der
  Lektion aus dem am 2026-09-09 gefundenen Test-Isolations-Bug bei Phase 1
  wurde bei jedem neuen Test explizit geprüft, dass `call_model` für
  **alle** in der Kaskade durchlaufenen Rollen gemockt ist, nicht nur für
  die zuletzt aufgerufene).

**Kein echter Gateway-E2E-Test wurde in dieser Sitzung durchgeführt.**
Anders als beim Phase-3-Abschluss (Commit `e9e46f1`, realer Lauf über
`mpa-architect`/`mpa-challenger`) wurde `mpa-research`/`mpa-architect`/
`mpa-challenger` hier nicht erneut real durchgespielt bis
`WAITING_FOR_SYNTHESIS_APPROVAL` — ein dedizierter
`MPA_OPENCLAW_AGENT_ID_SYNTHESIZER`-Gateway-Agent (Modell
`anthropic/claude-opus-5`, Rolle HIGH) existiert noch nicht und müsste vor
einem echten Testlauf angelegt werden.

## REVIEW

Prüfung gegen AT-4.1–AT-4.3 und `SECURITY.md`:

* **AT-4.1:** Referentielle-Integritäts-Prüfung sitzt vor jeder
  Persistierung in `_run_synthesis_agent()`, testet gegen die tatsächlich
  im Kontext gezeigten `research_sources.id`-Werte (nicht gegen alle
  jemals für das Projekt erzeugten), verifiziert durch
  `test_fabricated_source_id_is_rejected`.
* **AT-4.2:** `synthesis_revision_count` und Versionierung verifiziert
  durch `test_change_request_creates_new_version_and_hint_from_round_three`
  (inkl. `hint`-Feld-Timing und -Platzierung).
* **AT-4.3:** Stichprobe von `DECISIONS.md` (ADR-001–ADR-011) weiterhin
  vollständig und aktuell — Phase 4 führte keine neue
  Architekturentscheidung ein, die einen zusätzlichen ADR-Eintrag
  erfordert hätte (die drei getroffenen Implementierungsentscheidungen -
  Versionierung, Flag-Neuberechnung, `hint`-Platzierung - sind direkte
  Ableitungen aus bereits bestehender Spezifikation, keine neuen
  Architektur-Trade-offs).
* **Security:** Research-Anteil des Synthesizer-Kontexts läuft weiterhin
  ausschließlich über `wrap_external_research_data()`; Architect-/
  Challenger-Output wird bewusst **nicht** gewrappt (eigene, bereits
  vertrauenswürdige Agenten-Ergebnisse, keine externen Rohdaten,
  SECURITY.md §3). Fehlertexte werden vor der Persistierung weiterhin über
  `redact_secrets()` bereinigt (SECURITY.md §2). Kosten-Notbremse greift
  vor jedem Synthesizer-Aufruf, auch während `change-request`
  (SECURITY.md §8, jetzt mit `test_cost_ceiling_exceeded_during_...`
  abgedeckt).
* Keine Phase-5+-Rolle, kein Critic-Aufruf, keine UI-/SSE-Änderung wurde
  eingeführt.

## CHECKPOINT

Phase 4 ist vollständig implementiert und mit einer vollständig gemockten
Testsuite (46/46, keine Netzwerkaufrufe) verifiziert. Ausstehend vor
endgültiger Freigabe: ein realer Gateway-E2E-Lauf bis
`WAITING_FOR_SYNTHESIS_APPROVAL` (analog zum Phase-3-Abschluss vom
2026-09-09), inkl. Anlage eines dedizierten
`mpa-synthesizer`-Gateway-Agenten. Die endgültige Freigabe bleibt wie bei
allen vorigen Phasen beim Nutzer.
