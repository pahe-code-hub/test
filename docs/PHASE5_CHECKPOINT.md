# PHASE5_CHECKPOINT.md

**Status: Implementiert, mocked getestet — echter Gateway-E2E-Test steht
aus.** Freigabe (APPROVED) bleibt wie bei den vorigen Phasen beim Nutzer.

Nachweis für **Phase 5 — Qualität** aus `MASTER_PLAN_v0.1.md` Abschnitt
35, umgesetzt nach `PLAN → IMPLEMENT → TEST → REVIEW → CHECKPOINT`.

## PLAN

Umfang: `critic_v1`, `evaluator_v1`, `revision_v1` (alle Modellklasse
HIGH), automatisch ausgeführt entlang der in `WORKFLOW_STATES.md`
festgelegten internen Qualitätsschleife:

```
REVIEWING -> EVALUATING (automatisch, unabhängig von OK/ANMERKUNGEN)
EVALUATING -> FINALIZING (PASS)
EVALUATING -> REVISION_REQUIRED -> REVISING (automatisch, revision_count < 2)
REVISING -> EVALUATING (automatisch, KEIN erneuter critic_v1-Lauf, AT-5.5)
EVALUATING -> ESCALATION_REQUIRED(REVISION_LIMIT) (revision_count >= 2)
ESCALATION_REQUIRED(REVISION_LIMIT) -> REVISING (RETRY_REVISION, Nutzer)
                                     -> FINALIZING (ACCEPT_WITH_OPEN_POINTS, Nutzer)
```

Bewusst **nicht** implementiert: Final Builder (Phase 6) — `FINALIZING`
bleibt reiner Zielzustand ohne Agentenlauf, exakt dieselbe Scope-Grenze
wie zuvor bei `SYNTHESIZING`/`REVIEWING` in Phase 3/4.

Codebase-Exploration erfolgte über die bestehenden Dokumente
(`ACCEPTANCE_TESTS.md` AT-5.1–5.5, `AGENT_PROMPTS.md` §§ critic_v1/
evaluator_v1/revision_v1, `DATA_MODEL.md` §§ critic/evaluations/
revisions, `WORKFLOW_STATES.md`, `API_CONTRACT.md` § Eskalation) sowie
einen vollständigen Reread von `routers/projects.py`, um das
Phase-3/4-Muster (eigene `_run_<rolle>_agent()`-Funktion, Self-Chaining
über Commits hinweg, `_check_cost_ceiling` vor jedem Lauf) exakt
fortzusetzen.

Zwei Designentscheidungen, die die Spezifikation offenlässt:

1. **`critic.PK`** ist laut `DATA_MODEL.md` `(project_id,
   synthesis_version)` — wörtlich übernommen (nicht wie Architect/
   Challenger auf `project_id` allein vereinfacht), obwohl im
   implementierten Zustandsgraphen pro Projekt aktuell nur eine
   Synthese-Version je einen Critic-Lauf erreichen kann.
2. **Ein manuelles `RETRY_REVISION`** nach Eskalation ist bewusst NICHT
   durch `MAX_INTERNAL_REVISIONS` selbst gedeckelt — jede weitere Runde
   läuft ohnehin wieder über das Nutzer-Gate `escalation/resolve`, das
   erfüllt Leitprinzip 8 ("keine Endlosschleifen ohne Nutzeraktion") ohne
   eine zusätzliche, in der Spezifikation nicht geforderte Hartgrenze.
   `revisions.number` kann dadurch über 2 hinausgehen; der
   `DATA_MODEL.md`-Kommentar "1 oder 2" gilt für den automatischen
   Pfad, nicht für nutzergetriebene Wiederholungen.

## IMPLEMENT

* Migration `0005_phase5_quality`: additive Tabellen `critic`
  (PK `(project_id, synthesis_version)`), `evaluations` (PK `id`, mehrere
  Zeilen je Projekt möglich — vor/nach jeder Revision) und `revisions`
  (PK `id`, FK `evaluation_id` → `evaluations.id`).
* `app/models.py`: ORM-Modelle `Critic`, `Evaluation`, `Revision`.
* `app/schemas.py`: Agenten-Output-Schemas `CriticOutput`
  (`status: OK|ANMERKUNGEN`, `findings` max. 5), `EvaluatorOutput`
  (`status: PASS|REVISION_REQUIRED`, `required_changes` max. 3),
  `RevisionOutput` (`updated_synthesis: SynthesisOutput` — dieselbe
  Struktur wie `synthesizer_v1`, per verschachteltem Pydantic-Modell
  erzwungen statt als freies `dict`, plus `changed: GEÄNDERT|UNVERÄNDERT`);
  REST-Out-Schemas `CriticOut`, `EvaluationOut`; `ProjectDetail` um
  `critic` und `evaluations` (Liste, chronologisch) erweitert.
* `prompts/critic_v1.md`, `evaluator_v1.md`, `revision_v1.md`: Prosa-Stil
  identisch zu den bestehenden Prompts. Nur `critic_v1.md` enthält den
  `<external_research_data>`-Warnabsatz (AT-SEC.1) — Evaluator/Revision
  erhalten laut `WORKFLOW_STATES.md` keine Research-Daten direkt.
* `app/state_machine.py`: neue Konstanten `EVALUATING`,
  `REVISION_REQUIRED`, `REVISING`, `FINALIZING`, `REVISION_LIMIT`.
* `app/config.py`: `MAX_INTERNAL_REVISIONS = 2`.
* `app/routers/projects.py`:
  * `_relevant_research_findings()` + `_build_critic_context()`: Critic
    erhält nur die von der aktuellen Synthese tatsächlich referenzierten
    Quellen (`referenced_by_synthesis`, aus Phase 4) statt des kompletten
    Research-Fundus — ausgelegt als "relevante Research-Erkenntnisse"
    (Abschnitt 23). Architect-/Challenger-Rohentwürfe werden bewusst NICHT
    mitgegeben (ADR-005).
  * `_run_critic_agent()`: Cost-Ceiling-Check, `Critic`-Zeile nur bei
    Erfolg (wie `Synthesis`, kein Platzhalter bei `FAILED`), kettet
    danach immer zu `_run_evaluator_agent()` — `REVIEWING` ist kein
    Nutzer-Gate.
  * `_current_synthesis_content()`: liefert die letzte Revision (falls
    vorhanden) oder die ursprünglich freigegebene Synthese-Version — die
    `synthesis`-Tabellenzeile selbst bleibt unverändert, die
    Revisionsschicht liegt logisch darüber.
  * `_build_evaluator_context()`: Intake, aktuelle Synthese, Critic-
    Ergebnis, NUR eine Diff-Notiz der letzten Revision statt der
    vollständigen Historie (v0.2-Präzisierung, Review 3 §3.5).
  * `_run_evaluator_agent()`: `evaluations.attempt = revision_count` zum
    Zeitpunkt der Prüfung (`DATA_MODEL.md`); verzweigt nach `PASS` ->
    `FINALIZING`, `REVISION_REQUIRED` mit `revision_count <
    MAX_INTERNAL_REVISIONS` -> `REVISION_REQUIRED` -> kettet zu
    `_run_revision_agent()`, sonst -> `ESCALATION_REQUIRED(REVISION_LIMIT)`.
  * `_run_revision_agent()`: korrigiert anhand der zuletzt geforderten
    Punkte (`_latest_evaluation()`), erzeugt eine `revisions`-Zeile (KEINE
    neue `synthesis`-Version), erhöht `revision_count`, kettet immer
    zurück zu `_run_evaluator_agent()` — nie zu `_run_critic_agent()`
    (AT-5.5).
  * `POST /{id}/synthesis/approve`: löst jetzt tatsächlich
    `_run_critic_agent()` aus (vorher reiner Park-Zustand, Phase 4).
  * `POST /{id}/escalation/resolve`: komplett umgebaut — verzweigt jetzt
    nach `escalation_reason` (`CLARIFICATION_LIMIT` wie bisher,
    `REVISION_LIMIT` neu mit `RETRY_REVISION`/`ACCEPT_WITH_OPEN_POINTS`);
    eine zum `escalation_reason` nicht passende `action` liefert weiterhin
    `422` (API_CONTRACT.md).
  * `retry`: neue Zweige `critic`/`evaluator`/`revision`.
  * `_to_project_detail()`: `critic`- und `evaluations`-Felder ergänzt.
* `tests/test_phase4_synthesis.py`: `test_approve_transitions_to_reviewing`
  umbenannt/neu geschrieben zu
  `test_approve_sets_approved_at_and_triggers_review_cascade` — die alte
  Fassung rief `synthesis/approve` ohne Mock für `critic`/`evaluator` auf
  und bestand nur zufällig über den `FAILED`-Pfad (fehlender
  `MPA_OPENCLAW_AGENT_ID_CRITIC` in der Testumgebung), ohne das neue
  Verhalten tatsächlich zu prüfen — exakt die in der Projekt-Historie
  bereits einmal gefundene Test-Isolationsfalle (`git log` Commit
  `2f980fa`), hier präventiv vor dem ersten echten Lauf behoben statt erst
  danach.

## TEST

Neu in `tests/test_phase5_quality.py` (13 Tests):

| Test | Nachweis |
|---|---|
| `test_critic_ok_and_evaluator_pass_reach_finalizing` | Grundkaskade REVIEWING → EVALUATING → FINALIZING |
| `test_critic_anmerkungen_still_chains_to_evaluator_automatically` | REVIEWING → EVALUATING unabhängig von OK/ANMERKUNGEN |
| `test_revision_required_chains_to_revision_then_back_to_evaluating_not_critic` | AT-5.5: genau ein `critic`-Lauf über die ganze Revisionsschleife |
| `test_revision_limit_escalates_after_two_failed_revisions` | AT-5.4: Eskalation nach 2 Revisionen, `REWORK_INTAKE` dort ungültig (422) |
| `test_accept_with_open_points_finalizes_without_further_revision` | Eskalationsausgang `ACCEPT_WITH_OPEN_POINTS` → `FINALIZING` |
| `test_retry_revision_after_escalation_is_not_capped_at_two` | Designentscheidung 2: manuelles `RETRY_REVISION` läuft über 2 hinaus |
| `test_retry_repeats_only_failed_evaluator` | technischer Retry wiederholt ausschließlich die fehlgeschlagene Rolle |
| `test_cost_ceiling_exceeded_during_synthesis_approve` | Kosten-Notbremse vor `critic_v1` |
| `test_critic_output_schema_rejects_more_than_five_findings` | Schema erzwingt `findings` ≤ 5 |
| `test_evaluator_output_schema_rejects_more_than_three_required_changes` | Schema erzwingt `required_changes` ≤ 3 |
| `test_revision_output_requires_full_synthesis_structure` | Schema erzwingt vollständige `SynthesisOutput`-Struktur |
| `test_escalation_resolve_guard_rejects_wrong_state` | Guard: `escalation/resolve` nur bei `ESCALATION_REQUIRED` |

Plus die korrigierte `test_approve_sets_approved_at_and_triggers_review_cascade`
in `test_phase4_synthesis.py`.

Ausführungsstand (echte Laufzeitumgebung, kein Sandbox-Vorbehalt):

* `python -m py_compile` über alle neuen/geänderten Dateien: **bestanden**.
* `python -m alembic upgrade head` gegen eine frische SQLite-Datei:
  **bestanden**, `critic`/`evaluations`/`revisions`-Tabellen entsprechen
  exakt `DATA_MODEL.md` (Spalten und PKs geprüft).
* `python -m pytest tests/ -v`: **58 von 58 bestanden** (46 bestehende +
  13 neue - 1 umgeschriebene), Laufzeit ~8s, **kein realer Netzwerk-/
  Gateway-Aufruf**.

**Kein echter Gateway-E2E-Test wurde in dieser Sitzung durchgeführt.**
Dedizierte `MPA_OPENCLAW_AGENT_ID_CRITIC`/`_EVALUATOR`/`_REVISION`-
Gateway-Agenten existieren noch nicht und müssten vor einem echten
Testlauf angelegt werden. Geplant: EIN gemeinsamer realer E2E-Lauf nach
Abschluss von Phase 6 (statt separat je Phase), der den gesamten
verbleibenden Pfad bis `COMPLETED` durchspielt — kosteneffizienter als
mehrfach die volle Kaskade ab `understanding` real zu wiederholen.

## REVIEW

Prüfung gegen AT-5.1–AT-5.5 und `SECURITY.md`:

* **AT-5.1/5.2/5.3** (inhaltliche Modellqualität: relevante Findings statt
  Kosmetik, Schema-Konformität, punktgenaue Revision): mechanisch über
  Schema-Validierung und Plumbing-Tests abgedeckt; die eigentliche
  inhaltliche Bewertung folgt beim realen E2E-Lauf (wie schon bei Phase 3/4
  praktiziert — reale Modellqualität lässt sich nicht sinnvoll mocken).
* **AT-5.4:** `test_revision_limit_escalates_after_two_failed_revisions`
  verifiziert Eskalation nach genau 2 Revisionen inkl. ungültigem
  `REWORK_INTAKE`-Ausgang; `test_accept_with_open_points_finalizes...` und
  `test_retry_revision_after_escalation_...` verifizieren beide gültigen
  Ausgänge.
* **AT-5.5:** `test_revision_required_chains_to_revision_then_back_to_evaluating_not_critic`
  zählt die `agent_runs`-Einträge je Rolle explizit (`critic` == 1 über
  die gesamte Schleife).
* **Security:** `critic_v1` bettet die relevanten Research-Erkenntnisse
  ausschließlich über `wrap_external_research_data()` ein (AT-SEC.1);
  `evaluator_v1`/`revision_v1` erhalten keine Research-Daten direkt, daher
  kein Wrapper nötig (WORKFLOW_STATES.md). Fehlertexte laufen weiterhin
  über `redact_secrets()` vor der Persistierung (SECURITY.md §2).
  Kosten-Notbremse greift vor jedem der drei neuen Agentenaufrufe.
* Keine Phase-6-Rolle (`final_builder`), keine UI-/SSE-Änderung wurde
  eingeführt — `FINALIZING` bleibt reiner Zielzustand.

## CHECKPOINT

Phase 5 ist vollständig implementiert und mit einer vollständig gemockten
Testsuite (58/58, keine Netzwerkaufrufe) verifiziert, inklusive der
kompletten internen Revisions-/Eskalationsschleife (AT-5.4/5.5). Ausstehend
vor endgültiger Freigabe: ein realer Gateway-E2E-Lauf (geplant gemeinsam
mit Phase 6, siehe TEST). Die endgültige Freigabe bleibt wie bei allen
vorigen Phasen beim Nutzer.
