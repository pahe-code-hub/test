# DATA_MODEL.md

Konkretes Datenmodell für MASTER PLAN AI V1, basierend auf `MASTER_PLAN_v0.2.md` Abschnitt 22 (Projekt-State) und den dort in v0.2 ergänzten Punkten (Review 2 §2.2, §2.6; Review 5 §5.1). Zielsystem: SQLite, WAL-Modus, Migrationen über Alembic ab Phase 1 (ADR, siehe unten).

## Grundsätze

* **Eine Datenbank für State + Audit** (ADR-010, `DECISIONS.md`): keine separate Logging-Komponente. `agent_runs` ist zugleich Fortschrittsanzeige-Quelle (Abschnitt 26) und Audit-Log (Abschnitt 31).
* **Ein Commit pro Agentenlauf**: Ergebnis-Tabelle(n) und `agent_runs`-Statuszeile werden in derselben Transaktion geschrieben (Review 4 §4.3). Kein Zwischenzustand ist von außen sichtbar.
* **Getrennte Zeilen statt gemeinsamer JSON-Blobs für parallele Schreiber**: `architect` und `challenger` sind eigene Tabellen (nicht Felder eines gemeinsam aktualisierten `project`-Datensatzes), damit die parallele Ausführung (Abschnitt 34) nicht auf derselben Zeile kollidiert (Review 2 §2.2).
* JSON-wertige Spalten werden als `TEXT` mit JSON-Inhalt geführt (SQLite hat keinen nativen JSON-Typ); Zugriff über die SQLite-JSON1-Funktionen, wo nötig.
* `PRAGMA journal_mode=WAL;` beim Verbindungsaufbau.
* Migrationen: Alembic, ein Migrationsskript pro MVP-Phase (Abschnitt 35), nie manuelle Schemaänderungen an der laufenden Datei.

## Tabellen

### `projects`

| Spalte | Typ | Beschreibung |
|---|---|---|
| `id` | TEXT (UUID), PK | Projekt-ID |
| `title` | TEXT | Anzeigename (aus Intake abgeleitet oder frei vergeben) |
| `created_at` / `updated_at` | TEXT (ISO 8601) | — |
| `workflow_state` | TEXT | einer der States aus `WORKFLOW_STATES.md` |
| `escalation_reason` | TEXT, nullable | `CLARIFICATION_LIMIT` \| `REVISION_LIMIT`, nur gesetzt während `workflow_state = ESCALATION_REQUIRED` |
| `research_gate_enabled` | INTEGER (bool) | konfigurierbares Recherche-Freigabe-Gate (Abschnitt 25) |
| `clarification_round_count` | INTEGER, default 0 | Limit `MAX_CLARIFICATION_ROUNDS = 3` |
| `synthesis_revision_count` | INTEGER, default 0 | kein hartes Limit, UI-Hinweis ab Runde 3 |
| `revision_count` | INTEGER, default 0 | Limit `MAX_INTERNAL_REVISIONS = 2` |
| `total_model_calls` | INTEGER, default 0 | für harten Kostendeckel (Review 4 §4.2) |
| `total_estimated_cost_usd` | REAL, default 0 | kumulierte Kostenschätzung, siehe Abschnitt 32 |

### `intake`

1:1 zu `projects`, `project_id` als PK/FK.

| Spalte | Typ |
|---|---|
| `project_id` | TEXT, PK, FK → `projects.id` |
| `goal` | TEXT |
| `problem` | TEXT |
| `users_structure` | TEXT |
| `interface_output` | TEXT |
| `constraints` | TEXT |
| `core_features` | TEXT |
| `updated_at` | TEXT |

Editierbar nur während `workflow_state = DRAFT`.

### `understanding`

| Spalte | Typ |
|---|---|
| `project_id` | TEXT, PK, FK |
| `status` | TEXT — `READY` \| `CLARIFICATION_REQUIRED` \| `CONTRADICTION` (Sub-Status, Review 1 §1.3) |
| `summary` | TEXT, nullable (nur bei `READY`) |
| `questions` | TEXT (JSON-Array von Strings), nullable |
| `contradiction_note` | TEXT, nullable (nur bei `CONTRADICTION`) |
| `confirmed_at` | TEXT, nullable |

### `research`

| Spalte | Typ |
|---|---|
| `project_id` | TEXT, PK, FK |
| `solutions` | TEXT (JSON-Array, Struktur siehe `AGENT_PROMPTS.md` § Research) |
| `best_practices` | TEXT (JSON-Array von Strings) |
| `open_source_potential` | TEXT |
| `conclusion` | TEXT |
| `approved_at` | TEXT, nullable (nur wenn `research_gate_enabled`) |

### `research_sources`

Normalisierte Quellenliste, getrennt von `research.solutions`, damit jede einzelne Fundstelle unabhängig auditierbar ist (Abschnitt 21/31) und dem Final Builder gezielt referenziert werden kann (v0.2-Fix Abschnitt 23, Review 3 §3.1).

| Spalte | Typ |
|---|---|
| `id` | TEXT (UUID), PK |
| `project_id` | TEXT, FK |
| `agent_run_id` | TEXT, FK → `agent_runs.id` (welcher Research-Lauf hat diese Quelle geliefert) |
| `url` | TEXT |
| `title` | TEXT |
| `finding` | TEXT |
| `relevance` | REAL, nullable |
| `confidence` | REAL, nullable |
| `license_info` | TEXT, nullable |
| `retrieved_at` | TEXT (ISO 8601) — stammt vom Retrieval-Aufruf selbst, nicht vom Modell (Review 3 §3.4) |
| `provider` | TEXT — z. B. `tavily` (ADR-003) |
| `referenced_by_synthesis` | INTEGER (bool), default 0 — wird gesetzt, wenn `synthesis.output.existing_solutions_open_source` (siehe `AGENT_PROMPTS.md`) per `source_id` auf diesen Eintrag verweist. Steuert, welche Quellen der Final Builder als Kontext erhält (v0.2-Fix Abschnitt 23, Review 3 §3.1) — nicht erst nachträglich beim Final Builder gesetzt |

### `architect` / `challenger`

Identisches Schema, getrennte Tabellen (siehe Grundsätze oben).

| Spalte | Typ |
|---|---|
| `project_id` | TEXT, PK, FK |
| `output` | TEXT (JSON, Struktur siehe `AGENT_PROMPTS.md`) |
| `run_status` | TEXT — `PENDING` \| `RUNNING` \| `DONE` \| `FAILED` (Review 1 §1.7, Fan-out/Fan-in) |

### `synthesis`

| Spalte | Typ |
|---|---|
| `project_id` | TEXT, FK |
| `version` | INTEGER — erhöht sich bei jedem `ÄNDERUNGSWUNSCH` (`synthesis_revision_count`) |
| `output` | TEXT (JSON, vollständige Struktur inkl. `key_decisions`, siehe `AGENT_PROMPTS.md` § `synthesizer_v1`) |
| `approved_at` | TEXT, nullable |
| PK | (`project_id`, `version`) |

*(v0.1 Abschnitt 22 hatte `output` und `decisions` als getrennte Felder vorgesehen — mit dem in `AGENT_PROMPTS.md` festgelegten Output-Schema liegt `key_decisions` bereits strukturiert innerhalb von `output`; eine zusätzliche, redundante `decisions`-Spalte entfällt.)*

Nur die Zeile mit `version = MAX(version)` ist die aktuell gültige.

### `critic`

| Spalte | Typ |
|---|---|
| `project_id` | TEXT, FK |
| `synthesis_version` | INTEGER — gegen welche Synthese-Version geprüft wurde |
| `status` | TEXT — `OK` \| `ANMERKUNGEN` |
| `findings` | TEXT (JSON-Array, max. 5 Einträge) |
| PK | (`project_id`, `synthesis_version`) |

### `evaluations`

| Spalte | Typ |
|---|---|
| `id` | TEXT (UUID), PK |
| `project_id` | TEXT, FK |
| `attempt` | INTEGER — entspricht `revision_count` zum Zeitpunkt der Prüfung |
| `status` | TEXT — `PASS` \| `REVISION_REQUIRED` |
| `reasoning` | TEXT, nullable (nur bei `PASS`, max. 3 Sätze) |
| `required_changes` | TEXT (JSON-Array, max. 3 Einträge), nullable |
| `created_at` | TEXT |

### `revisions`

| Spalte | Typ |
|---|---|
| `id` | TEXT (UUID), PK |
| `project_id` | TEXT, FK |
| `number` | INTEGER (1 oder 2, siehe `MAX_INTERNAL_REVISIONS`) |
| `evaluation_id` | TEXT, FK → `evaluations.id` |
| `updated_synthesis` | TEXT (JSON) |
| `changed` | TEXT — `GEÄNDERT` \| `UNVERÄNDERT` |
| `created_at` | TEXT |

### `final`

| Spalte | Typ |
|---|---|
| `project_id` | TEXT, PK, FK |
| `plan` | TEXT (JSON, vollständige Struktur nach `AGENT_PROMPTS.md` § `final_builder_v1`, enthält `open_decisions` bereits als Feld) |
| `presentation` | TEXT (JSON oder Markdown) |
| `open_decisions` | TEXT (JSON-Array) — denormalisierte Kopie von `plan.open_decisions`, insbesondere für den schnellen Zugriff auf aus `ESCALATION_REQUIRED → FINALIZING` übernommene offene Punkte ohne den kompletten `plan`-Blob zu parsen |
| `created_at` | TEXT |

### `agent_runs`

Zentrale Audit-/Fortschritts-Tabelle (ersetzt eine separate Logging-Komponente, ADR-010).

| Spalte | Typ |
|---|---|
| `id` | TEXT (UUID), PK |
| `project_id` | TEXT, FK |
| `role` | TEXT — `understanding` \| `research` \| `architect` \| `challenger` \| `synthesizer` \| `critic` \| `evaluator` \| `revision` \| `final_builder` |
| `attempt` | INTEGER — erhöht sich bei jedem technischen Retry desselben Schritts |
| `status` | TEXT — `RUNNING` \| `DONE` \| `FAILED` (entspricht `last_run_status`, Review 1 §1.6) |
| `started_at` / `finished_at` | TEXT, nullable |
| `provider` | TEXT |
| `model` | TEXT |
| `model_class` | TEXT — `LOW` \| `MEDIUM` \| `HIGH` |
| `prompt_id` | TEXT — z. B. `architect_v1` (ADR-009) |
| `error` | TEXT, nullable |
| `token_usage_input` / `token_usage_output` | INTEGER, nullable |
| `estimated_cost_usd` | REAL, nullable |

Index: (`project_id`, `role`, `attempt`) für schnellen Zugriff auf den letzten Lauf je Rolle.

## Zusammenspiel mit `WORKFLOW_STATES.md`

* Jeder State mit laufendem Agentenaufruf (siehe dortiger Abschnitt „Technischer Fehlschlag") entspricht genau einer offenen `agent_runs`-Zeile mit `status = RUNNING`.
* Ein Retry nach `FAILED` erzeugt eine **neue** `agent_runs`-Zeile mit erhöhtem `attempt`, nicht ein Update der fehlgeschlagenen Zeile — die fehlgeschlagene Zeile bleibt für die Audit-Historie erhalten.
* `escalation_reason` auf `projects` wird exakt beim Übergang nach `ESCALATION_REQUIRED` gesetzt (aus `WAITING_FOR_USER_CLARIFICATION` → `CLARIFICATION_LIMIT`, aus `EVALUATING` → `REVISION_LIMIT`) und beim Verlassen von `ESCALATION_REQUIRED` wieder auf `NULL` gesetzt.

## Migrationen

Alembic-Revisionen folgen den MVP-Phasen aus Abschnitt 35:

* Phase 1: `projects`, `intake`, `understanding`, `agent_runs` (nur Rolle `understanding`)
* Phase 2: `research`, `research_sources`
* Phase 3: `architect`, `challenger`
* Phase 4: `synthesis`
* Phase 5: `critic`, `evaluations`, `revisions`
* Phase 6: `final`
* Phase 7/8: keine Schemaänderung erwartet (UX/Export-Phasen)

Jede Migration ist additiv (neue Tabellen/Spalten), keine Migration der bisherigen Phasen löscht oder verändert bestehende Spalten rückwirkend.
