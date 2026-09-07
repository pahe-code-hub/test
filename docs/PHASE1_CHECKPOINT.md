# PHASE1_CHECKPOINT.md

Nachweis für **Phase 1 — Workflow-Kern** (`MASTER_PLAN_v0.2.md` Abschnitt 35), umgesetzt nach der in Abschnitt 40 vorgegebenen Regel `PLAN → IMPLEMENT → TEST → REVIEW → COMMIT/CHECKPOINT`. Freigabegrundlage: Commit `360b24d` (Übergabepaket, `HANDOVER = APPROVED`). Umsetzung in `backend/`.

> **Nachtrag (ADR-011):** Die erste Fassung dieses Checkpoints (Commit `984c4d4`) hatte Modellaufrufe direkt gegen den `anthropic`-Client geführt statt über den im Masterplan (Abschnitt 19/33) vorgesehenen OpenClaw-Gateway — ein Implementierungsversehen, in der Nutzerprüfung gefunden und korrigiert. `app/model_provider.py` ruft jetzt ausschließlich über `openclaw-sdk` auf; siehe `DECISIONS.md` ADR-011 für die vollständige Begründung und den technischen Nachweis, dass OpenClaw ein reales, so nutzbares System ist. Dieser Checkpoint ist entsprechend aktualisiert (TEST/REVIEW/CHECKPOINT unten).

## PLAN

Phase-1-Umfang exakt nach Abschnitt 35: Projekt anlegen, Intake speichern, State Machine, Understanding Agent, Nutzerbestätigung, einfacher Model Provider. Bewusst **nicht** enthalten: Frontend, SSE, jede Rolle außer `understanding_v1`, Docker/Packaging — siehe `backend/README.md` § Umfang.

Architekturentscheidungen aus dem Übergabepaket 1:1 übernommen, keine eigene Abweichung: SQLite/WAL (DATA_MODEL.md), Alembic-Migration ab Phase 1 (DATA_MODEL.md), `call_model`-Signatur inkl. Timeout/Provider-Retries (Abschnitt 20), Zustände/Guards aus `WORKFLOW_STATES.md`, REST-Routen aus `API_CONTRACT.md`.

## IMPLEMENT

* `backend/app/models.py` — nur die für Phase 1 vorgesehenen Tabellen (`projects`, `intake`, `understanding`, `agent_runs`), keine Vorwegnahme der übrigen `DATA_MODEL.md`-Tabellen.
* `backend/alembic/` — eine Migration (`0001_phase1_initial`), per Autogenerate erzeugt und gegen `models.py` verifiziert.
* `backend/app/model_provider.py` — `call_model(role, model_class, system_prompt, input_context, output_schema, timeout, max_provider_retries)`, implementiert über `openclaw-sdk` (ADR-011): pro Rolle ein OpenClaw-`Agent` (angelegt via `AgentConfig(llm_provider="anthropic", llm_model=..., ...)`, Anthropic bleibt der tatsächliche Modellanbieter *hinter* OpenClaw), strukturierte Ausgabe über einen an `agent.execute()` angehängten Schema-Prompt + eigenes JSON-Parsing (nicht `Agent.execute_structured()`, weil diese Methode kein `ExecutionResult`/Token-Nutzung zurückgibt, die für `agent_runs`/Kostenkontrolle nötig ist). Signatur/Rückgabetyp (`ModelCallResult`) unverändert gegenüber der ersten Fassung — der Umbau war ausschließlich eine Änderung *hinter* `call_model`, `routers/projects.py` musste nicht angefasst werden.
* `backend/app/state_machine.py` — Guards für die in Phase 1 erreichbaren Zustände/Übergänge aus `WORKFLOW_STATES.md` (siehe „Bekannte Lücken" unten zur bewussten Beschränkung).
* `backend/app/routers/projects.py` — die Phase-1-Teilmenge von `API_CONTRACT.md`.
* `backend/app/security.py` — Secret-Redaction für Fehlertexte (`SECURITY.md` §2), da beim Schreiben des Codes auffiel, dass diese Anforderung im Übergabepaket zwar spezifiziert, aber noch nicht in Code gegossen war.
* `backend/prompts/understanding_v1.md` — Prompt-Datei (ADR-009), Inhalt exakt nach `AGENT_PROMPTS.md` § `understanding_v1`.

Eine Abweichung von der wörtlichen `API_CONTRACT.md`-Lesart wurde beim Implementieren nötig und korrigiert: `API_CONTRACT.md` beschreibt die Vollständigkeitsprüfung der sechs Intake-Felder als Guard von `POST .../submit`, nicht der Projekterstellung. Die erste Implementierung hatte das versehentlich an der Erstellung erzwungen; korrigiert, damit `ACCEPTANCE_TESTS.md` AT-1.1 („wird bei submit mit 422 abgelehnt") wörtlich stimmt — `IntakeIn` erlaubt jetzt leere Felder, `_require_complete_intake` prüft erst beim `submit`.

## TEST

`backend/tests/test_phase1_workflow.py`, 11 Tests (mocken `app.routers.projects.call_model`, prüfen Workflow-/State-Logik):

| Test | Deckt ab |
|---|---|
| `test_project_creation_with_six_fields` | AT-1.1 (Erstellung) |
| `test_submit_rejects_incomplete_intake` | AT-1.1 (422 bei Unvollständigkeit) |
| `test_understanding_ready_leads_to_confirmation_gate` | AT-1.2 (Struktur), AT-1.3 |
| `test_confirm_transitions_to_researching` | AT-1.3 |
| `test_correct_returns_to_draft` | AT-1.3 |
| `test_clarification_limit_escalates_and_only_rework_intake_is_valid` | AT-1.4, inkl. korrigierter Eskalations-Rückwege (Nutzerprüfung von `WORKFLOW_STATES.md`) |
| `test_provider_error_is_redacted_before_storage` | AT-1.5 (kein Secret in `agent_runs.error`) |
| `test_retry_after_failure_creates_new_run_and_keeps_old_one` | AT-1.6 |
| `test_retry_without_prior_failure_is_rejected` | Guard-Vollständigkeit zu AT-1.6 |
| `test_state_survives_restart` | AT-1.7 |
| `test_cost_ceiling_blocks_further_calls` | Kosten-Notbremse (API_CONTRACT.md, Review 4 §4.2 — vorgezogen, da die Spalten ohnehin ab Phase 1 existieren) |

`backend/tests/test_model_provider.py`, 7 Tests (mocken `openclaw_sdk` selbst — Client, `get_agent`/`create_agent`, `Agent.execute` — prüfen die ADR-011-Adapter-Schicht isoliert):

| Test | Deckt ab |
|---|---|
| `test_call_model_happy_path` | Schema-Prompt, JSON-Extraktion, `ModelCallResult`-Mapping (Tokens, Kosten, Provider/Modell) |
| `test_call_model_reuses_agent_across_calls` | Ein OpenClaw-Agent pro Rolle, nicht pro Aufruf neu angelegt |
| `test_call_model_existing_agent_is_reused_via_get_agent` | Bereits im Gateway existierender Agent wird wiederverwendet, nicht dupliziert |
| `test_call_model_gateway_error_raises_model_provider_error` | Gateway-Fehler → `ModelProviderError` (Review 1 §1.6 Übersetzung) |
| `test_call_model_unsuccessful_result_raises_model_provider_error` | `ExecutionResult.success=False` → `ModelProviderError` |
| `test_call_model_unparseable_response_raises_model_provider_error` | Keine valide JSON-Antwort → `ModelProviderError` statt stillem Fehler |
| `test_call_model_unknown_model_class_raises_model_provider_error` | Guard gegen ungültige Modellklasse |

```
18 passed in 0.57s
```

Kein Test führt einen echten Netzwerkaufruf aus — weder gegen OpenClaw noch gegen Anthropic.

## REVIEW (Selbstprüfung gegen ACCEPTANCE_TESTS.md, ehrlich mit Lücken)

**Vollständig automatisiert nachgewiesen:** AT-1.1, AT-1.3, AT-1.4, AT-1.6, AT-1.7, sowie die Kosten-Notbremse.

**Nicht vollständig automatisiert nachweisbar — ehrlicher Vorbehalt, kein stillschweigendes Abhaken:**

* **AT-1.2** verlangt laut eigener Formulierung in `ACCEPTANCE_TESTS.md` eine „manuelle Stichprobenprüfung" der tatsächlichen Modellantwort gegen die Verbotsliste in `AGENT_PROMPTS.md`. In dieser Sandbox war weder ein `ANTHROPIC_API_KEY` noch ein laufender OpenClaw-Gateway verfügbar — ein echter Modellaufruf war technisch nicht möglich. Die Tests beweisen die **Struktur** (Status-Handling, ≤3 Fragen laut Mock), nicht die inhaltliche Prompt-Treue eines echten Aufrufs. **Offener Punkt:** vor Produktivbetrieb einmal mit echtem API-Key **und laufendem Gateway** gegen 2-3 reale, absichtlich unterspezifizierte Testfälle laufen lassen und die Rückfragen manuell gegen die Verbotsliste (Technologien, Frameworks, UI-Details, ...) prüfen.
* **Kein Ende-zu-Ende-Test gegen einen echten OpenClaw-Gateway** (neu seit ADR-011): `test_model_provider.py` verifiziert die Adapter-Schicht gegen die reale `openclaw-sdk`-Schnittstelle (Methodensignaturen, Rückgabetypen, Exception-Klassen — alle am tatsächlich installierten Paket geprüft, nicht geraten), aber mit gemocktem Client/Agent. Ob ein echter Gateway-Prozess (Verbindungsaufbau, Agent-Anlage, tatsächliche `execute()`-Antwort) genauso funktioniert, ist nicht verifiziert — dafür fehlte in dieser Sandbox die Möglichkeit, einen dauerhaften Gateway-Dienst zu betreiben. **Offener Punkt:** vor Produktivbetrieb einmal gegen einen echten, lokal laufenden OpenClaw-Gateway durchtesten (deckt sich mit dem AT-1.2-Punkt oben, kann im selben Durchlauf erledigt werden).
* **AT-1.5**, Teil „API-Schlüssel nicht im Frontend-Bundle": in Phase 1 gibt es bewusst kein Frontend (siehe `README.md`), der Check ist damit vakuos erfüllt, nicht wirklich geprüft. Muss erneut geprüft werden, sobald ein Frontend existiert.

**Bewusste Vereinfachungen, keine Fehler:**

* Klärungsantworten (`POST .../clarification`) werden für Phase 1 simpel an `intake.constraints` angehängt statt in einer eigenen strukturierten Historie geführt — `DATA_MODEL.md` sieht für Phase 1 keine eigene Tabelle dafür vor, eine solche wäre eine nicht angeforderte Erweiterung.
* Kein In-Prozess-Retry mit Backoff in `model_provider.py` — bewusst entfernt (siehe Commit-Historie), da Workflow-Retry ausschließlich über `POST /retry` läuft (Review 1 §1.6) und ein zusätzlicher interner Retry-Layer unnötige Komplexität gewesen wäre.

## CHECKPOINT

Phase 1 gilt hiermit als abgeschlossen **mit den drei oben benannten, expliziten Vorbehalten** (AT-1.2 real-API-Nachweis aussteht, kein Test gegen einen echten OpenClaw-Gateway, AT-1.5-Frontend-Teil nicht anwendbar). Architektur jetzt konsistent mit `MASTER_PLAN_v0.2.md` Abschnitt 19/33 (ADR-011) — Modellaufrufe laufen über OpenClaw, nicht direkt gegen Anthropic. Keine Phase-2-Arbeit begonnen — `research`, `research_sources`, Tavily-Anbindung etc. existieren nicht im Code.

**Vor Beginn von Phase 2:** OpenClaw-Gateway lokal betreiben, `ANTHROPIC_API_KEY` konfigurieren, damit sowohl den AT-1.2-Realdatentest als auch den ausstehenden Ende-zu-Ende-Test gegen den echten Gateway in einem Durchlauf nachholen, dann formale Freigabe für Phase 2 einholen (die laut ADR-003 ohnehin an die dortige 5-Testfälle-Validation gebunden ist).
