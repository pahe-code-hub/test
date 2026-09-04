# WORKFLOW_STATES.md

Vollständige Zustands- und Übergangstabelle für MASTER PLAN AI, Stand nach Review 1 (Logik). Ergänzt MASTER_PLAN_v0.2.md Abschnitt 5.

## Grundsätze

* `FAILED` ist kein State in dieser Tabelle, sondern ein Attribut `last_run_status` am jeweils aktiven State (Review 1 §1.6). Ein technischer Fehlschlag hält den Workflow im selben State; Retry führt denselben Übergang erneut aus.
* Guards (`[...]`) sind vom Backend zu prüfen, bevor ein Übergang ausgeführt wird. Kein Agent darf einen Übergang selbst auslösen.

## Zustände

| State | Bedeutung |
|---|---|
| `DRAFT` | Intake wird erfasst, noch nicht eingereicht |
| `UNDERSTANDING` | Verständnis-Agent läuft |
| `WAITING_FOR_USER_CLARIFICATION` | Wartet auf Antwort des Nutzers (inkl. Sub-Status `CONTRADICTION`) |
| `WAITING_FOR_USER_CONFIRMATION` | Wartet auf „RICHTIG VERSTANDEN" / „KORRIGIEREN" |
| `RESEARCHING` | Research Agent läuft |
| `RESEARCH_READY` | Research-Ergebnis liegt vor |
| `WAITING_FOR_RESEARCH_APPROVAL` | *(neu, Review 1 §1.1)* nur wenn Research-Gate konfiguriert aktiv ist |
| `GENERATING_SOLUTIONS` | Architect + Challenger laufen parallel (interne Sub-Status `architect.run_status`, `challenger.run_status`) |
| `SYNTHESIZING` | Synthesizer läuft |
| `WAITING_FOR_SYNTHESIS_APPROVAL` | *(neu, Review 1 §1.1)* wartet auf „ZIELKONZEPT FREIGEBEN" / „ÄNDERUNGSWUNSCH" |
| `REVIEWING` | Critic läuft |
| `EVALUATING` | Evaluator läuft |
| `REVISION_REQUIRED` | Evaluator hat Korrekturen gefordert |
| `REVISING` | Revision Agent läuft |
| `ESCALATION_REQUIRED` | Nutzer muss Grundsatzentscheidung treffen. Trägt `escalation_reason ∈ {CLARIFICATION_LIMIT, REVISION_LIMIT}` — die beiden Auslöser führen zu unterschiedlichen Rückwegen (siehe Übergangstabelle), da bei `CLARIFICATION_LIMIT` noch gar kein Zielkonzept existiert, das revidiert oder finalisiert werden könnte |
| `FINALIZING` | Final Builder läuft |
| `COMPLETED` | Endzustand — Plan fertiggestellt |

## Übergangstabelle

| Von | Nach | Auslöser | Guard |
|---|---|---|---|
| `DRAFT` | `UNDERSTANDING` | Nutzer klickt „IDEE PRÜFEN" | alle 6 Intake-Felder ausgefüllt |
| `UNDERSTANDING` | `WAITING_FOR_USER_CONFIRMATION` | Agent-Output = `READY` | — |
| `UNDERSTANDING` | `WAITING_FOR_USER_CLARIFICATION` | Agent-Output = `CLARIFICATION_REQUIRED` oder `CONTRADICTION` (Sub-Status) | — |
| `WAITING_FOR_USER_CLARIFICATION` | `UNDERSTANDING` | Nutzer beantwortet Rückfrage | `clarification_round_count < MAX_CLARIFICATION_ROUNDS (3)` |
| `WAITING_FOR_USER_CLARIFICATION` | `ESCALATION_REQUIRED` | Nutzer beantwortet Rückfrage | `clarification_round_count >= MAX_CLARIFICATION_ROUNDS`; setzt `escalation_reason = CLARIFICATION_LIMIT` *(neu, Review 1 §1.4; Reason-Feld ergänzt nach Nutzer-Review v0.2)* |
| `WAITING_FOR_USER_CONFIRMATION` | `RESEARCHING` | Nutzer klickt „RICHTIG VERSTANDEN" | — |
| `WAITING_FOR_USER_CONFIRMATION` | `DRAFT` | Nutzer klickt „KORRIGIEREN" | Intake wird editierbar |
| `RESEARCHING` | `RESEARCH_READY` | Research Agent abgeschlossen | — |
| `RESEARCH_READY` | `WAITING_FOR_RESEARCH_APPROVAL` | — | nur wenn Research-Gate aktiv konfiguriert |
| `RESEARCH_READY` | `GENERATING_SOLUTIONS` | — | nur wenn Research-Gate **nicht** aktiv |
| `WAITING_FOR_RESEARCH_APPROVAL` | `GENERATING_SOLUTIONS` | Nutzer klickt „RECHERCHE FREIGEBEN" | — |
| `WAITING_FOR_RESEARCH_APPROVAL` | `RESEARCHING` | Nutzer klickt „NEU RECHERCHIEREN" oder gibt „ANMERKUNG" | — |
| `GENERATING_SOLUTIONS` | `SYNTHESIZING` | beide Sub-Status = abgeschlossen | `architect.run_status == DONE AND challenger.run_status == DONE` |
| `SYNTHESIZING` | `WAITING_FOR_SYNTHESIS_APPROVAL` | Synthesizer abgeschlossen | — |
| `WAITING_FOR_SYNTHESIS_APPROVAL` | `REVIEWING` | Nutzer klickt „ZIELKONZEPT FREIGEBEN" | — |
| `WAITING_FOR_SYNTHESIS_APPROVAL` | `SYNTHESIZING` | Nutzer klickt „ÄNDERUNGSWUNSCH" | `synthesis_revision_count++` (kein hartes Limit, UI-Hinweis ab Runde 3, Review 1 §1.2) |
| `REVIEWING` | `EVALUATING` | Critic abgeschlossen (STATUS OK oder ANMERKUNGEN) | — |
| `EVALUATING` | `FINALIZING` | Evaluator-Output = `PASS` | — |
| `EVALUATING` | `REVISION_REQUIRED` | Evaluator-Output = `REVISION_REQUIRED` | `revision_count < MAX_INTERNAL_REVISIONS (2)` |
| `EVALUATING` | `ESCALATION_REQUIRED` | Evaluator-Output = `REVISION_REQUIRED` | `revision_count >= MAX_INTERNAL_REVISIONS`; setzt `escalation_reason = REVISION_LIMIT` |
| `REVISION_REQUIRED` | `REVISING` | automatisch | — |
| `REVISING` | `EVALUATING` | Revision Agent abgeschlossen | zurück zum Evaluator, **nicht** zu `REVIEWING` (kein erneuter Critic-Durchlauf) |
| `ESCALATION_REQUIRED` (`escalation_reason = REVISION_LIMIT`) | `REVISING` | Nutzer trifft Grundsatzentscheidung, wünscht weiteren Versuch am bestehenden Zielkonzept | *(neu, Review 1 §1.5)* |
| `ESCALATION_REQUIRED` (`escalation_reason = REVISION_LIMIT`) | `FINALIZING` | Nutzer akzeptiert das bestehende Zielkonzept trotz offener Punkte ausdrücklich | *(neu, Review 1 §1.5)*; offene Punkte werden in Final-Builder-Output unter „OFFENE ENTSCHEIDUNGEN" geführt |
| `ESCALATION_REQUIRED` (`escalation_reason = CLARIFICATION_LIMIT`) | `DRAFT` | Nutzer überarbeitet die Idee grundlegend | *(neu, Nutzer-Review v0.2)*; **nicht** `REVISING`/`FINALIZING` — an diesem Punkt existiert noch kein Zielkonzept, das revidiert oder finalisiert werden könnte, da der Workflow das Verständnis-Gate (Abschnitt 6/7) nie passiert hat; `clarification_round_count` wird auf 0 zurückgesetzt |
| `FINALIZING` | `COMPLETED` | Final Builder abgeschlossen | — |

## Technischer Fehlschlag (orthogonal zur obigen Tabelle)

Jeder State mit einem laufenden Agentenaufruf (`UNDERSTANDING`, `RESEARCHING`, `GENERATING_SOLUTIONS`, `SYNTHESIZING`, `REVIEWING`, `EVALUATING`, `REVISING`, `FINALIZING`) kann `last_run_status = FAILED` annehmen (Timeout, Provider-Fehler nach Ausschöpfung von `max_provider_retries`, siehe MASTER_PLAN_v0.2.md Abschnitt 20/27). Der State selbst ändert sich nicht. Der Nutzer kann den fehlgeschlagenen Schritt erneut auslösen; der Agentenlauf wird als neue Zeile in `agent_runs` mit erhöhtem `attempt` geführt (Review 1 §1.6, Review 4 §4.3).
