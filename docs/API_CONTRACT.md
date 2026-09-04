# API_CONTRACT.md

REST- + SSE-Vertrag für MASTER PLAN AI V1. Basierend auf `MASTER_PLAN_v0.2.md` Abschnitt 18–20, 26 und `WORKFLOW_STATES.md`.

## Grundsätze

* Ein gemeinsam deploybares Artefakt (ADR-004): FastAPI liefert REST + SSE **und** den gebauten React-Build im selben Prozess.
* Transport: REST für alle zustandsändernden Aktionen, **SSE** für Fortschritts-Updates (ADR-002 — kein WebSocket in V1).
* **Kein Auth-Layer in V1** (Review 4 §4.4): Single-User/lokal. Jeder Netzwerk-Zugriff über `localhost` hinaus erfordert vorher einen Auth-Mechanismus (siehe `SECURITY.md`) — diese API-Spezifikation setzt das für V1 nicht um.
* Jede zustandsändernde Aktion wird serverseitig gegen die Guards aus `WORKFLOW_STATES.md` geprüft. Eine Aktion, die im aktuellen `workflow_state` nicht zulässig ist, liefert `409 Conflict`.
* Antwortformat durchgehend JSON; Fehler als `{"error": {"code": "string", "message": "string"}}`.

## Endpunkte

### Projekte

**`POST /api/projects`**
Legt ein neues Projekt an (Intake). Body: die sechs Intake-Felder (Abschnitt 3).
→ `201 Created`, `workflow_state = DRAFT`. Enthält keine automatische Auslösung von `UNDERSTANDING` — das erfolgt erst über `POST /api/projects/{id}/submit`.

**`GET /api/projects`**
Projektübersicht (Titel, `workflow_state`, `updated_at`) für die Projektliste (Abschnitt 27 „Projektübersicht", Phase 7).

**`GET /api/projects/{id}`**
Vollständiger aktueller State (für die 8-Schritt-Navigation aus Abschnitt 2): `workflow_state`, `escalation_reason`, alle bislang erzeugten Ergebnisse (`intake`, `understanding`, `research`, `architect`, `challenger`, `synthesis`, `critic`, `evaluations`, `final`, je nach Fortschritt), sowie `last_run_status` des zuletzt gelaufenen Agenten.

**`PATCH /api/projects/{id}/intake`**
Bearbeitet die Intake-Felder. Guard: nur bei `workflow_state = DRAFT`.

**`POST /api/projects/{id}/submit`**
„IDEE PRÜFEN". Guard: `workflow_state = DRAFT`, alle 6 Intake-Felder ausgefüllt. → löst `understanding_v1` aus, `workflow_state → UNDERSTANDING`.

### Verständnis-Gate

**`POST /api/projects/{id}/understanding/confirm`**
„RICHTIG VERSTANDEN". Guard: `workflow_state = WAITING_FOR_USER_CONFIRMATION`. → `workflow_state → RESEARCHING`, löst `research_v1` aus.

**`POST /api/projects/{id}/understanding/correct`**
„KORRIGIEREN". Guard: `workflow_state = WAITING_FOR_USER_CONFIRMATION`. → `workflow_state → DRAFT`.

**`POST /api/projects/{id}/clarification`**
Body: `{"answers": "string"}`. Guard: `workflow_state = WAITING_FOR_USER_CLARIFICATION`. → löst `understanding_v1` erneut aus (`clarification_round_count += 1`), oder bei Limit-Überschreitung `workflow_state → ESCALATION_REQUIRED` mit `escalation_reason = CLARIFICATION_LIMIT`.

### Recherche-Gate (nur wenn `research_gate_enabled`)

**`POST /api/projects/{id}/research/approve`**
„RECHERCHE FREIGEBEN". Guard: `workflow_state = WAITING_FOR_RESEARCH_APPROVAL`. → `workflow_state → GENERATING_SOLUTIONS`, löst `architect_v1` und `challenger_v1` parallel aus.

**`POST /api/projects/{id}/research/rerun`**
„NEU RECHERCHIEREN" oder „ANMERKUNG". Body: `{"comment": "string | null"}`. Guard: `workflow_state = WAITING_FOR_RESEARCH_APPROVAL`. → `workflow_state → RESEARCHING`.

### Synthese-Gate

**`POST /api/projects/{id}/synthesis/approve`**
„ZIELKONZEPT FREIGEBEN". Guard: `workflow_state = WAITING_FOR_SYNTHESIS_APPROVAL`. → `workflow_state → REVIEWING`, löst `critic_v1` aus.

**`POST /api/projects/{id}/synthesis/change-request`**
„ÄNDERUNGSWUNSCH". Body: `{"comment": "string"}`. Guard: `workflow_state = WAITING_FOR_SYNTHESIS_APPROVAL`. → `synthesis_revision_count += 1`, `workflow_state → SYNTHESIZING`. Ab `synthesis_revision_count >= 3` liefert die Antwort zusätzlich `{"hint": "Konzept grundlegend neu aufsetzen?"}` (Abschnitt 12).

### Eskalation

**`POST /api/projects/{id}/escalation/resolve`**
Body-Form abhängig von `escalation_reason` (aus `GET /api/projects/{id}` bekannt):

* Bei `escalation_reason = CLARIFICATION_LIMIT`: Body `{"action": "REWORK_INTAKE"}`. Einziger gültiger Wert — siehe `WORKFLOW_STATES.md`, kein `REVISING`/`FINALIZING` möglich. → `workflow_state → DRAFT`, `clarification_round_count = 0`, `escalation_reason = null`.
* Bei `escalation_reason = REVISION_LIMIT`: Body `{"action": "RETRY_REVISION"}` → `workflow_state → REVISING`, `escalation_reason = null`; oder `{"action": "ACCEPT_WITH_OPEN_POINTS"}` → `workflow_state → FINALIZING`, `escalation_reason = null`, offene Evaluator-Punkte werden nach `final.open_decisions` übernommen.

Ein Body, dessen `action` nicht zum aktuellen `escalation_reason` passt (z. B. `RETRY_REVISION` bei `CLARIFICATION_LIMIT`), liefert `422 Unprocessable Entity`.

### Retry (technischer Fehlschlag)

**`POST /api/projects/{id}/retry`**
Guard: der zuletzt für dieses Projekt gestartete `agent_runs`-Eintrag hat `status = FAILED`. → startet denselben Agentenlauf erneut (neue `agent_runs`-Zeile, `attempt + 1`), `workflow_state` bleibt unverändert (Review 1 §1.6).

### Fortschritt (SSE)

**`GET /api/projects/{id}/events`**
Server-Sent-Events-Stream. Event-Typen:

| Event | Payload |
|---|---|
| `state_changed` | `{"workflow_state": "...", "escalation_reason": "... \| null"}` |
| `agent_run_started` | `{"role": "...", "attempt": n}` |
| `agent_run_completed` | `{"role": "...", "attempt": n}` |
| `agent_run_failed` | `{"role": "...", "attempt": n, "error": "..."}` |
| `cost_updated` | `{"total_model_calls": n, "total_estimated_cost_usd": x}` |

Bildet die in Abschnitt 2/26 geforderte Statusanzeige (✓/●/○ je Schritt) ab, ohne dass das Frontend pollen muss.

### Export

**`GET /api/projects/{id}/export?format=markdown`**
Guard: `workflow_state = COMPLETED`. Liefert `final.plan` + `final.presentation` als Markdown-Datei (Phase 6). Weitere Formate (PDF/DOCX/JSON) sind Phase 8 und hier nicht spezifiziert.

### Kosten

**`GET /api/projects/{id}/cost`**
Liefert `total_model_calls`, `total_estimated_cost_usd`, aufgeschlüsselt je `agent_runs.role` — Grundlage für die optionale UI-Kostenanzeige (Abschnitt 32).

## Kosten-Notbremse (Review 4 §4.2)

Vor jedem Agentenaufruf prüft das Backend serverseitig einen konfigurierten harten Deckel (`MAX_MODEL_CALLS_PER_PROJECT`, `MAX_ESTIMATED_COST_PER_PROJECT_USD`), unabhängig von `revision_count`/`synthesis_revision_count`. Bei Überschreitung: `423 Locked` mit `{"error": {"code": "COST_LIMIT_EXCEEDED", ...}}`, Projekt bleibt im aktuellen `workflow_state`, keine automatische Fortsetzung möglich, bis der Nutzer den Deckel explizit erhöht (Endpunkt dafür ist Betriebs-/Admin-Funktion, nicht Teil dieses V1-Kontrakts).

## Nicht Teil dieses Kontrakts (V1)

Authentifizierung/Autorisierung, Mehrbenutzerbetrieb, WebSocket-Fallback, PDF/DOCX/JSON-Export — siehe Abschnitt 37 (Nicht-Ziele) bzw. Abschnitt 35 Phase 8.
