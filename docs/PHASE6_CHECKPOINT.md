# PHASE6_CHECKPOINT.md

**Status: Implementiert, mocked getestet — echter Gateway-E2E-Test steht
aus.** Freigabe (APPROVED) bleibt wie bei den vorigen Phasen beim Nutzer.

Nachweis für **Phase 6 — Final Output** aus `MASTER_PLAN_v0.1.md`
Abschnitt 35, umgesetzt nach `PLAN → IMPLEMENT → TEST → REVIEW →
CHECKPOINT`.

## PLAN

Umfang: `final_builder_v1` (Modellklasse konfigurierbar, Default HIGH),
automatisch ausgeführt sobald `EVALUATING`/`ESCALATION_REQUIRED` den
Grenz-State `FINALIZING` erreichen (bislang, seit Phase 5, ein reiner
Park-State ohne Agentenausführung), plus Markdown-Export
(`GET /export?format=markdown`, `COMPLETED`-Guard). Bewusst **nicht**
implementiert: Live-Status/Kostenanzeige (Phase 7), weitere Exportformate
PDF/DOCX/JSON (Phase 8).

Zwei Designentscheidungen, die AT-6.1/6.2 hart (code-seitig) statt nur
prompt-seitig erzwingen, konsistent mit dem AT-4.1-Muster aus Phase 4:

1. **Referentielle Integrität** von
   `existing_open_source_solutions_used[].source_id` wird vor jeder
   Persistierung gegen die tatsächlich im Kontext gezeigten
   `research_sources.id`-Werte geprüft (dieselbe Prüfung wie beim
   Synthesizer, hier gegen die von der Synthese referenzierte Teilmenge).
2. **Offene Evaluator-Punkte** aus einer `ACCEPT_WITH_OPEN_POINTS`-
   Eskalation werden programmatisch in `final.open_decisions` gemergt
   (`_open_evaluator_points()`), nicht nur per Prompt-Anweisung erhofft -
   AT-6.2 ist damit unabhängig von Modellverhalten deterministisch erfüllt.

## IMPLEMENT

* Migration `0006_phase6_final`: additive Tabelle `final` (PK
  `project_id`, `plan`/`presentation`/`open_decisions`/`created_at`).
* `app/models.py`: ORM-Modell `Final`.
* `app/schemas.py`: `FinalBuilderOutput` (10 Felder + `presentation_
  structure`, nach `AGENT_PROMPTS.md` § `final_builder_v1`), `FinalOut`
  (REST); `ProjectDetail` um `final` erweitert.
* `prompts/final_builder_v1.md`: Prosa-Stil identisch zu den bestehenden
  Prompts, inkl. `<external_research_data>`-Warnabsatz (die Rolle erhält
  laut `WORKFLOW_STATES.md` referenzierte Research-Daten) und expliziter
  Anweisung, offene Eskalationspunkte unter `open_decisions` zu führen.
* `app/state_machine.py`: neue Konstante `COMPLETED` (Endzustand).
* `app/config.py`: `FINAL_BUILDER_MODEL_CLASS` (env-konfigurierbar,
  Default `HIGH`) - laut Masterplan bewusst "MITTEL oder HOCH
  (konfigurierbar)", anders als die anderen Rollen nicht hart codiert.
* `app/routers/projects.py`:
  * `_open_evaluator_points()`: liefert die zuletzt offenen
    Evaluator-Punkte nur dann, wenn die letzte `Evaluation` noch
    `REVISION_REQUIRED` ist (das ist nur nach `ACCEPT_WITH_OPEN_POINTS`
    der Fall - beim normalen `PASS`-Pfad ist die letzte Evaluation immer
    `PASS`, daher leer).
  * `_build_final_builder_context()`: Intake, freigegebenes Zielkonzept
    (`_current_synthesis_content()` aus Phase 5 - liefert die letzte
    Revision, falls vorhanden), die von der Synthese referenzierten
    `research_sources` gewrappt, plus ggf. die offenen Eskalationspunkte
    als expliziter Kontext-Hinweis.
  * `_run_final_builder_agent()`: Cost-Ceiling-Check, `AgentRun`-Anlage,
    referentielle Prüfung (Designentscheidung 1) vor jeder Persistierung,
    `open_decisions`-Merge (Designentscheidung 2), `Final`-Zeile nur bei
    Erfolg, → `COMPLETED`.
  * Self-Chaining an BEIDEN Stellen ergänzt, die bislang in `FINALIZING`
    parkten: `_run_evaluator_agent()` bei `PASS` und `escalation/resolve`
    bei `ACCEPT_WITH_OPEN_POINTS`.
  * `retry`: neuer `final_builder`-Zweig.
  * `GET /{id}/export`: Guard `workflow_state = COMPLETED`,
    `format=markdown` (alles andere → `422 UNSUPPORTED_FORMAT`, Hinweis
    auf Phase 8), liefert `_render_final_markdown()` als
    `text/markdown`-Datei mit `Content-Disposition: attachment`.
  * `_render_final_markdown()`: rendert alle 10 Abschnitte + Präsentations-
    struktur als Markdown-Überschriften (AT-6.4).
  * `_to_project_detail()`: `final`-Feld ergänzt.
* `tests/test_phase4_synthesis.py`/`test_phase5_quality.py`: bestehende
  Tests, deren Kaskade jetzt bis `PASS`/`ACCEPT_WITH_OPEN_POINTS` läuft,
  mocken zusätzlich `final_builder` und prüfen `COMPLETED` statt
  `FINALIZING` als Endzustand - dieselbe Test-Isolationsfalle wie beim
  Phase-4→5-Übergang, hier präventiv korrigiert (siehe Kommentare in den
  jeweiligen Testdateien).

## TEST

Neu in `tests/test_phase6_final.py` (10 Tests):

| Test | Nachweis |
|---|---|
| `test_final_builder_runs_on_pass_and_reaches_completed` | AT-6.1: alle 10 Abschnitte + Präsentationsstruktur vorhanden, `COMPLETED` erreicht |
| `test_final_builder_can_reference_valid_synthesis_source_id` | eine echte, von der Synthese referenzierte `source_id` wird akzeptiert (Review 3 §3.1-Fix real nutzbar) |
| `test_fabricated_source_id_in_final_builder_is_rejected` | AT-6.1-Grundlage: erfundene `source_id` → `FAILED`, State bleibt `FINALIZING` |
| `test_open_points_from_escalation_are_merged_into_final_open_decisions` | AT-6.2: Evaluator-Punkte + eigene `open_decisions` werden deterministisch gemergt |
| `test_retry_repeats_only_failed_final_builder` | technischer Retry wiederholt ausschließlich `final_builder` |
| `test_cost_ceiling_exceeded_during_final_builder` | Kosten-Notbremse greift auch vor `final_builder_v1` |
| `test_export_markdown_returns_all_sections` | AT-6.4: Markdown-Export enthält alle 10 Abschnitte + Präsentationsstruktur |
| `test_export_guard_rejects_wrong_state` | Guard: Export nur bei `COMPLETED` (409 sonst) |
| `test_export_unsupported_format_returns_422` | nicht unterstütztes Format → 422 |
| `test_final_builder_output_schema_requires_all_fields` | Schema erzwingt Vollständigkeit |

Ausführungsstand (echte Laufzeitumgebung, kein Sandbox-Vorbehalt):

* `python -m py_compile` über alle neuen/geänderten Dateien: **bestanden**.
* `python -m alembic upgrade head` gegen eine frische SQLite-Datei:
  **bestanden**, `final`-Tabelle entspricht exakt `DATA_MODEL.md`.
* `python -m pytest tests/ -v`: **68 von 68 bestanden** (58 bestehende +
  10 neue), Laufzeit ~10s, **kein realer Netzwerk-/Gateway-Aufruf**.

**Kein echter Gateway-E2E-Test wurde in dieser Sitzung durchgeführt.** Ein
dedizierter `MPA_OPENCLAW_AGENT_ID_FINAL_BUILDER`-Gateway-Agent existiert
noch nicht. Geplant ist EIN gemeinsamer realer E2E-Lauf über Phase 5+6
zusammen (siehe `docs/PHASE5_CHECKPOINT.md`), sobald alle dafür nötigen
Gateway-Agenten (`critic`, `evaluator`, `revision`, `final_builder`)
angelegt sind.

## REVIEW

Prüfung gegen AT-6.1–AT-6.4 und `SECURITY.md`:

* **AT-6.1:** alle 10 Abschnitte strukturell erzwungen (Pydantic-Schema,
  keine optionalen Felder); `existing_open_source_solutions_used` ist
  strukturell befüllbar, weil `final_builder_v1` jetzt tatsächlich die
  referenzierten `research_sources` im Kontext erhält (`test_final_builder_
  can_reference_valid_synthesis_source_id` belegt das mit einer echten,
  aus dem Cascade-Kontext gelesenen ID, nicht nur einer geratenen).
* **AT-6.2:** `test_open_points_from_escalation_are_merged_into_final_open_decisions`
  verifiziert den Merge inkl. Dedupe-Verhalten.
* **AT-6.3** (Diff-Vergleich `synthesis.output.key_decisions` gegen
  `final.plan.core_technical_decisions`, keine widersprüchliche Aussage):
  inhaltliche Modellqualität, mechanisch nicht sinnvoll mockbar - wie
  AT-5.1/5.3 auf den realen E2E-Lauf verschoben.
* **AT-6.4:** `test_export_markdown_returns_all_sections` prüft alle 10
  Abschnitts-Überschriften plus Präsentationsstruktur im gerenderten
  Markdown.
* **Security:** die von der Synthese referenzierten `research_sources`
  laufen weiterhin ausschließlich über `wrap_external_research_data()`
  (globale Regel 2/AT-SEC.1-Muster). Fehlertexte weiterhin über
  `redact_secrets()` vor der Persistierung. Kosten-Notbremse greift vor
  `final_builder_v1` genauso wie vor allen vorigen Rollen.
* Keine Phase-7/8-Funktionalität (Live-Status, Kostenanzeige, weitere
  Exportformate) wurde eingeführt.

## CHECKPOINT

Phase 6 ist vollständig implementiert und mit einer vollständig gemockten
Testsuite (68/68, keine Netzwerkaufrufe) verifiziert, inklusive
Markdown-Export. Der Workflow erreicht damit erstmals `COMPLETED` -
Phasen 1-6 des MVP sind vollständig durchimplementiert. Ausstehend vor
endgültiger Freigabe: ein realer Gateway-E2E-Lauf (siehe TEST). Die
endgültige Freigabe bleibt wie bei allen vorigen Phasen beim Nutzer.
