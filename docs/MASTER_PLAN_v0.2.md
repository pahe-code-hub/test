# MASTER PLAN AI

## Technischer Umsetzungsplan für OpenClaw

**Version:** 0.2
**Status:** **APPROVED** (Nutzerfreigabe auf Commit `5ef2297`, nach Korrektur der Abschnitt-21-Inkonsistenz und der `ESCALATION_REQUIRED`-Rückwege) — siehe `reviews/FINAL_REVIEW_SUMMARY.md` für die vorangegangenen 5 Review-Pässe
**Ziel:** Erstellung des vollständigen Übergabepakets (Abschnitt 39), danach Umsetzung in OpenClaw

> Diese Version übernimmt alle KRITISCH und WICHTIG eingestuften Änderungen aus den fünf Reviews. Änderungen gegenüber v0.1 sind mit `[v0.2]` markiert. Unveränderte Abschnitte sind aus v0.1 übernommen. Vollständige Begründungen stehen in `reviews/*.md`.

---

## 1. Ziel des Systems

*(unverändert gegenüber v0.1)*

MASTER PLAN AI ist eine geführte Planungsanwendung, die aus einer zunächst groben Nutzeridee einen belastbaren, recherchierten, kritisch geprüften und freigegebenen Umsetzungsplan erzeugt. Der Nutzer wird durch einen strukturierten Intake geführt statt mit einer freien Prompt-Fläche allein gelassen.

Grundprinzip: Nicht möglichst viele KI-Aufrufe erzeugen, sondern unterschiedliche Denkrollen gezielt einsetzen.

## 2. UX-Grundkonzept

*(unverändert gegenüber v0.1 — Hauptnavigation Idee → Verständnis → Recherche → Lösungsentwürfe → Synthese → Prüfung → Abnahme → Ergebnis)*

## 3. Nutzerinput

*(unverändert gegenüber v0.1 — sechs Eingabebereiche: ZIEL, PROBLEM, NUTZER/STRUKTUR, INTERFACE/AUSGABE, EINSCHRÄNKUNGEN, KERNFUNKTIONEN; siehe Review 5 §5.7 — kein Vereinfachungsbedarf)*

## 4. Workflow

### 4.1 Gesamtfluss

*(unverändert)*

```
USER INPUT
→ Verständnisprüfung
→ Nutzerbestätigung
→ Recherche
→ [v0.2] optionale Nutzerfreigabe Recherche (konfigurierbar)
→ Architect + Challenger parallel
→ Synthese
→ [v0.2] Nutzerfreigabe Zielkonzept (ZIELKONZEPT FREIGEBEN / ÄNDERUNGSWUNSCH, begrenzt)
→ Critic
→ Evaluator
→ PASS oder gezielte Revision
→ Final Builder
→ Nutzer
```

Architect und Challenger arbeiten unabhängig voneinander und erhalten dieselben Grundlagen, aber nicht gegenseitig ihre Ergebnisse.

## 5. Workflow-State-Machine `[v0.2 — überarbeitet, Review 1]`

Vollständige Übergangstabelle mit Guards: siehe `WORKFLOW_STATES.md`. Änderungen gegenüber v0.1:

**Neue States:**

* `WAITING_FOR_RESEARCH_APPROVAL` — nur durchlaufen, wenn das konfigurierbare Research-Gate (Abschnitt 25) aktiv ist (Review 1 §1.1)
* `WAITING_FOR_SYNTHESIS_APPROVAL` — Wartezustand für Nutzerfreigabe 2 (Review 1 §1.1)

**Geänderte Semantik:**

* `FAILED` ist **kein eigenständiger State in der Übergangskette mehr**, sondern ein Lauf-Attribut (`last_run_status = FAILED`) am jeweils aktiven State. Retry setzt denselben State erneut aus, ohne einen State-Übergang über einen globalen `FAILED`-Knoten zu erzwingen (Review 1 §1.6).
* `understanding.status` erlaubt zusätzlich den Wert `CONTRADICTION` als Sub-Status von `WAITING_FOR_USER_CLARIFICATION` — kein eigener State (Review 1 §1.3).
* `GENERATING_SOLUTIONS` bleibt der sichtbare High-Level-State, führt aber intern getrennte Run-Datensätze `architect.run_status` und `challenger.run_status`, damit ein Retry gezielt nur den fehlgeschlagenen Zweig wiederholt (Review 1 §1.7).

**Neue Zähler/Limits:**

* `clarification_round_count`, Limit `MAX_CLARIFICATION_ROUNDS = 3` → danach `ESCALATION_REQUIRED` (Review 1 §1.4)
* `synthesis_revision_count` — kein hartes Limit, aber ab Runde 3 UI-Hinweis „Konzept grundlegend neu aufsetzen?" (Review 1 §1.2)

**`ESCALATION_REQUIRED` trägt `escalation_reason ∈ {CLARIFICATION_LIMIT, REVISION_LIMIT}`** — die beiden Auslöser führen zu unterschiedlichen, klar getrennten Ausgängen (nicht ein einziger generischer Ausgang, siehe `WORKFLOW_STATES.md` für die vollständige Tabelle):

* Bei `escalation_reason = REVISION_LIMIT` (Review 1 §1.5): `ESCALATION_REQUIRED → REVISING` — Nutzer gibt Richtungsentscheidung vor, ein weiterer Revisionsversuch am bestehenden Zielkonzept wird zugelassen; oder `ESCALATION_REQUIRED → FINALIZING` — Nutzer akzeptiert das bestehende Zielkonzept trotz offener Punkte ausdrücklich, offene Punkte werden im Final-Builder-Output unter „OFFENE ENTSCHEIDUNGEN" sichtbar geführt.
* Bei `escalation_reason = CLARIFICATION_LIMIT`: **weder** `REVISING` **noch** `FINALIZING` sind gültige Ziele — an diesem Punkt im Workflow existiert noch kein Zielkonzept, da das Verständnis-Gate (Abschnitt 6/7) nie passiert wurde. Einziger Ausgang: `ESCALATION_REQUIRED → DRAFT`, der Nutzer überarbeitet die Idee grundlegend; `clarification_round_count` wird zurückgesetzt.

Zulässige Übergänge werden weiterhin ausschließlich im Backend kontrolliert. Kein Agent darf eigenständig Workflow-Schritte überspringen.

## 6. Agenten

### 6.1 Verständnisprüfung

*(unverändert gegenüber v0.1, siehe Abschnitt 5 für die Sub-Status-Behandlung von `CONTRADICTION`)*

## 7. Nutzerfreigabe 1

*(unverändert)*

## 8. Research Agent `[v0.2 — Halluzinationsschutz präzisiert, Review 3 §3.4]`

*(Inhalt wie v0.1, zusätzlich:)*

**Neue verbindliche Pipeline-Regel:** die `ResearchProvider`-Abstraktion (Abschnitt 21: `search()` + `extract()`) darf ausschließlich Ergebnisse zurückgeben, die aus einem tatsächlichen Retrieval-Aufruf stammen (Suchtreffer oder abgerufene Seite). Der Research-Agent-Prompt darf ausschließlich mit den so gelieferten, bereits verifizierten Fundstellen arbeiten und **keine zusätzlichen, nicht abgerufenen Quellen ergänzen** — die Belegpflicht aus v0.1 wird damit technisch statt nur durch Prompt-Anweisung durchgesetzt.

> **Entschieden (ADR-003, ACCEPTED):** die `ResearchProvider`-Abstraktion wird für V1 über Tavily implementiert (`search` + `extract`, nicht Tavily Research/Deep-Research) — siehe `DECISIONS.md`, ADR-003 für Begründung, Alternativen und den Validierungsvorbehalt (5 reale Testfälle vor endgültiger Freigabe von Phase 2, siehe Abschnitt 35).

## 9. Architect `[v0.2 — Prompt-Ergänzung, Review 3 §3.2]`

*(Inhalt wie v0.1, Prompt-Anweisung ergänzt:)* „Overengineering vermeiden" wird von einem Nebensatz zu einer gleichrangigen Anforderung neben Robustheit erhoben: unnötige Komplexität ist genauso zu vermeiden wie unzureichende Robustheit.

## 10. Challenger `[v0.2 — Prompt-Ergänzung, Review 3 §3.2]`

*(Inhalt wie v0.1, Prompt-Anweisung ergänzt:)* Einfachheit darf grundlegende Robustheits- und Sicherheitsanforderungen nicht opfern — der Challenger muss explizit prüfen, ob eine vereinfachte Lösung noch die harten Einschränkungen (Abschnitt 3.5) und Kernfunktionen (Abschnitt 3.6) erfüllt.

## 11. KI-3 Synthesizer

*(unverändert gegenüber v0.1)*

## 12. Nutzerfreigabe 2 `[v0.2 — Limit ergänzt, Review 1 §1.2]`

Nach der Synthese wird das Zielkonzept dem Nutzer gezeigt. Optionen: ZIELKONZEPT FREIGEBEN, ÄNDERUNGSWUNSCH. State: `WAITING_FOR_SYNTHESIS_APPROVAL`. Der `synthesis_revision_count` wird mitgeführt; ab der dritten Runde erhält der Nutzer einen Hinweis, dass ein grundlegend neuer Ansatz sinnvoller sein könnte, statt weiterer punktueller Änderungswünsche.

## 13. Critic

*(unverändert gegenüber v0.1. Bewusster Trade-off dokumentiert: Critic erhält die Synthese, nicht die Architect-/Challenger-Rohentwürfe — siehe `DECISIONS.md`, ADR-005, Review 3 §3.7.)*

## 14. Evaluator `[v0.2 — Kontextumfang präzisiert, Review 3 §3.5]`

*(Inhalt wie v0.1, präzisiert:)* Bei mehreren Revisionsrunden erhält der Evaluator ausschließlich den aktuellen Zielkonzept-Stand, die ursprünglichen Critic-Findings und eine kurze Diff-Notiz („was wurde in dieser Revision geändert") — nicht die vollständige Revisionshistorie.

## 15. Revision Agent `[v0.2 — Modellklasse fixiert, Review 3 §3.6]`

**Modellklasse:** HOCH (für V1 fest, keine dynamische MITTEL/HOCH-Wahl mehr — konsistent mit Synthesizer/Critic/Evaluator). Eine kostenoptimierte MITTEL-Option kann in einer Folgeversion auf Basis echter Kostendaten eingeführt werden.

*(übrige Regeln unverändert gegenüber v0.1)*

## 16. Revisionslogik

*(unverändert: `MAX_INTERNAL_REVISIONS = 2`, danach `ESCALATION_REQUIRED` mit den in Abschnitt 5 neu definierten Ausgängen)*

## 17. Final Builder `[v0.2 — Kontext korrigiert, Review 3 §3.1]`

**Input:** freigegebenes Zielkonzept, notwendige strukturierte Projektdaten **sowie zusätzlich die im Zielkonzept referenzierten Open-Source-/Bestandslösungs-Einträge** (Teilmenge der Research-Ergebnisse, nicht der vollständige Research-State) — behebt den Widerspruch zwischen dem in v0.1 zu eng gefassten Kontext (Abschnitt 23) und dem geforderten Pflichtabschnitt „VERWENDETE BESTEHENDE / OPEN-SOURCE-LÖSUNGEN".

*(übriger Inhalt wie v0.1)*

## 18. Technische Architektur `[v0.2 — Entscheidungen fixiert, Review 2 §2.1, §2.4, §2.5]`

* Frontend: React, TypeScript
* Backend: Python, FastAPI
* Persistenz: SQLite (WAL-Modus, siehe Abschnitt 22)
* Orchestrierung: OpenClaw
* Kommunikation: REST + **Server-Sent Events (SSE)** — WebSocket wird für V1 nicht eingesetzt (ADR-001, Review 2 §2.1 / Review 5 §5.2: kein bidirektionaler Bedarf, SSE genügt für unidirektionale Statusupdates)
* Deployment: **ein gemeinsam deploybares Artefakt** (FastAPI liefert den gebauten React-Build aus und stellt REST-/SSE-Endpunkte im selben Prozess bereit), zunächst lokal, optional Docker, später Windows-Paket/Installer (ADR-004, Review 2 §2.5)

Keine Microservices für V1.

## 19. Systemkomponenten `[v0.2 — vereinfacht, Review 2 §2.4 / Review 5 §5.1]`

```
MASTER PLAN AI
Frontend (React)
→ Backend (FastAPI: REST + SSE + Workflow-/State-Machine-Logik)
→ ruft auf: OpenClaw Agent Layer (Modellaufrufe, Tool-Aufrufe, Research-Anbindung)
→ SQLite (Projekt-State + Audit-Log in derselben Datenbank, siehe Abschnitt 22)
```

„Workflow Orchestrator" und „Audit/Logging" sind für V1 keine eigenen Architekturschichten mehr, sondern Bestandteil von Backend bzw. State Store (Review 2 §2.4, Review 5 §5.1). Der Browser kommuniziert niemals direkt mit dem Modellprovider. API-Schlüssel liegen nur serverseitig.

## 20. Provider-Abstraktion `[v0.2 — Timeout/Retry ergänzt, Review 2 §2.7]`

Abstrakte Schnittstelle: `call_model(role, model_class, system_prompt, input_context, output_schema, timeout, max_provider_retries)`.

Modellklassen: LOW, MEDIUM, HIGH. **LOW ist für V1 nicht im Einsatz, aber als Kategorie reserviert** für zukünftige einfache Klassifikationsschritte (z. B. Eingangs-Plausibilitätsfilter) — siehe ADR-006, Review 5 §5.3.

Bei Überschreitung von Timeout/Provider-Retries wird der Agentenlauf als technisch fehlgeschlagen markiert (`last_run_status = FAILED`, siehe Abschnitt 5) — dieser technische Retry ist getrennt von den in Abschnitt 27 beschriebenen Workflow-Retries.

## 21. Research-Abstraktion `[v0.2 — Signatur an ADR-003 angepasst, Konsistenzfix beim Erstellen des Übergabepakets]`

Die in v0.1 als einzelner Aufruf skizzierte Schnittstelle `research(query, requirements, source_policy)` wird mit der ADR-003-Entscheidung (Tavily Search + Extract als zwei getrennte, unabhängig aufrufbare Operationen, siehe `DECISIONS.md`) auf zwei Methoden der `ResearchProvider`-Abstraktion präzisiert:

* `search(query, requirements, source_policy)` → Kandidaten-Treffer (URL, Titel, Snippet)
* `extract(urls)` → Volltext/Markdown je ausgewählter URL, inkl. `retrieved_at`

Diese Trennung war in v0.1 als einzelne Funktion zu grob spezifiziert, um die in `AGENT_PROMPTS.md` (Rolle `research_v1`) beschriebene Arbeitsweise abzubilden: erst Suchergebnisse sichten und Quellen auswählen, dann gezielt extrahieren — nicht beides in einem opaken Aufruf. Rückgabeform je Fundstelle unverändert strukturiert: `source`, `title`, `finding`, `relevance`, `confidence`, `license_info`, `retrieved_at` (siehe `DATA_MODEL.md`, Tabelle `research_sources`). Nur belegte, aus einem tatsächlichen `extract`-Aufruf stammende Findings dürfen in spätere Agentenprompts eingehen (Abschnitt 8, Review 3 §3.4). Konkrete Anbindung: Tavily hinter dieser Abstraktion gekapselt (ADR-003, ACCEPTED) — ein späterer Wechsel zu Exa oder einem anderen Provider erfordert keine Änderung an `research_v1` oder nachgelagerten Agenten, solange der neue Provider beide Methoden bedienen kann.

## 22. Projekt-State `[v0.2 — Schema ergänzt, Review 2 §2.2, §2.6, Review 5 §5.1]`

Empfohlenes Schema wie v0.1, ergänzt um:

* `project.synthesis_revision_count`, `project.clarification_round_count`
* Jeder Agentenlauf (Understanding, Research, Architect, Challenger, Synthesizer, Critic, Evaluator, Revision, Final Builder) wird als eigene Zeile in einer Tabelle `agent_runs` geführt (status, started_at, finished_at, provider, model, prompt_version, attempt, error, token_usage, estimated_cost) statt als Teil eines gemeinsam aktualisierten JSON-Blobs — verhindert Schreibkonflikte bei paralleler Ausführung von Architect und Challenger (Review 2 §2.2) und dient zugleich als Audit-Log (Review 5 §5.1, ersetzt eine separate Logging-Komponente).
* SQLite läuft im WAL-Modus (`PRAGMA journal_mode=WAL`); jeder Agentenlauf schreibt Ergebnis und Status in einer einzigen Transaktion (Review 2 §2.2, Review 4 §4.3).
* Schema-Migrationen über Alembic ab Phase 1 (Review 2 §2.6).

*(übriges Schema wie v0.1)*

## 23. Kontextmanagement `[v0.2 — Final Builder korrigiert, Review 3 §3.1, §3.5]`

* Verständnis-Agent: Intake
* Research: bestätigter Intake, Verständniszusammenfassung
* Architect: bestätigter Intake, Research-Zusammenfassung
* Challenger: bestätigter Intake, Research-Zusammenfassung
* Synthesizer: bestätigter Intake, Research-Zusammenfassung **inklusive der zugehörigen `research_sources`-Einträge (id, url, title, finding, license_info)** — ohne die IDs kann die Synthese `existing_solutions_open_source` nicht auf konkrete Quellen verweisen (Konsistenzfund aus der Nutzerprüfung des Übergabepakets, siehe `AGENT_PROMPTS.md`), Architect, Challenger
* Critic: bestätigter Intake, relevante Research-Erkenntnisse, Synthese (bewusst ohne Architect-/Challenger-Rohentwürfe, ADR-005)
* Evaluator: bestätigter Intake, aktueller Synthese-Stand, ursprüngliche Critic-Findings, Diff-Notiz der letzten Revision (nicht die volle Revisionshistorie)
* **Final Builder: bestätigter Intake, freigegebenes Zielkonzept, relevante Entscheidungen, sowie die im Zielkonzept referenzierten Open-Source-/Bestandslösungs-Einträge** `[v0.2, behebt Widerspruch aus Review 3 §3.1]`

## 24. Structured Outputs `[v0.2 — auf alle Agenten ausgeweitet, Review 3 §3.3]`

Jeder Agent mit mehrteiligem Output erhält ein JSON-Schema, dessen Felder den in den jeweiligen Abschnitten (8–17) bereits benannten Gliederungspunkten entsprechen (nicht nur Understanding und Evaluation wie in v0.1). Vollständige Schemas: siehe `AGENT_PROMPTS.md` im Übergabepaket. Die UI rendert daraus lesbare Darstellungen.

## 25. User Interface

*(unverändert gegenüber v0.1 — inkl. konfigurierbarem Research-Freigabe-Gate; jetzt mit explizitem State-Gegenstück, siehe Abschnitt 5)*

## 26. Live-Status `[v0.2 — SSE festgelegt]`

Backend führt längere Jobs asynchron aus, Frontend erhält Fortschritt ausschließlich über **SSE** (kein WebSocket, siehe Abschnitt 18).

## 27. Fehlerbehandlung `[v0.2 — Atomarität ergänzt, Review 4 §4.3]`

*(Inhalt wie v0.1, ergänzt:)* Jeder Agentenlauf schreibt Ergebnis und Statuswechsel in einer einzigen Datenbanktransaktion (Commit-or-Rollback) — verhindert inkonsistenten Projekt-State bei einem Absturz mitten im Schreibvorgang.

## 28. Versionierung der Prompts `[v0.2 — vereinfacht für V1, Review 5 §5.4]`

Für V1: Prompts als versionierte Dateien im Repository (`prompts/architect_v1.md`, `prompts/challenger_v1.md`, `prompts/synthesizer_v1.md`, …) statt eigener Datenbanktabelle mit Aktivierungslogik. Migration auf ein DB-gestütztes System (wie in v0.1 mit `prompt_id, role, version, content, output_schema, active` beschrieben) erst bei konkretem Bedarf (z. B. Prompt-A/B-Test im laufenden Betrieb).

## 29. Decision Log `[v0.2 — vereinfacht für V1, Review 5 §5.4]`

Für V1 als fortlaufende `DECISIONS.md` im Repository statt eigenem Datenmodell (Format wie v0.1-Beispiel ADR-001 beibehalten). Vollständiger Log: siehe `DECISIONS.md`.

## 30. Sicherheit `[v0.2 — Prompt-Injection-Mechanismus ergänzt, Review 4 §4.1, §4.4]`

*(Prinzipien wie v0.1, ergänzt um konkrete Mechanismen:)*

* **Prompt-Injection-Schutz ist technisch verbindlich, nicht nur Prinzip:** Jede Prompt-Vorlage, die recherchierte Webinhalte einbettet, muss diese in einem klar als Fremddaten markierten Block führen, mit expliziter Systemanweisung, dass der Inhalt Datenmaterial und keine Anweisung ist. Pflichtbestandteil jeder betroffenen Vorlage in `AGENT_PROMPTS.md`.
* **Auth-Modell explizit:** V1 ist Single-User/lokal ohne Authentifizierung. Vor jedem Netzwerk-Deployment (auch nur im LAN) ist ein Auth-Mechanismus verpflichtend nachzurüsten.
* Markdown-Rendering im Frontend ausschließlich über eine Bibliothek mit eingebautem HTML-Sanitizing, kein `dangerouslySetInnerHTML` mit ungefiltertem Agentenoutput.
* Secrets/PII in Freitext-Intake-Feldern: dokumentiertes Restrisiko, Nutzerhinweis in der UI, keine automatische Erkennung in V1.

*(übrige Punkte wie v0.1: API-Keys nur serverseitig, Secrets über Environment/Secret Store, keine Secrets im Browser/Prompts/Logs, Eingaben validieren, lokale Projektdaten nicht unnötig an externe Provider senden)*

## 31. Auditierbarkeit

*(unverändert gegenüber v0.1 in der Zielsetzung; technisch umgesetzt über die `agent_runs`-Tabelle aus Abschnitt 22, siehe Review 5 §5.1)*

## 32. Kostenkontrolle `[v0.2 — harter Deckel ergänzt, Review 4 §4.2]`

*(UI-Anzeige und Modellzuordnung wie v0.1, ergänzt:)* Zusätzlich zur Revisionslogik (Abschnitt 16) ein harter, serverseitig unabhängig geprüfter Deckel je Projekt (maximale Gesamtzahl an Modellaufrufen bzw. geschätzten Kosten pro Durchlauf) — greift unabhängig von jeder Workflow-Zählvariable als Verteidigung in der Tiefe.

## 33. OpenClaw-Verantwortung

*(unverändert gegenüber v0.1)*

## 34. Parallelisierung `[v0.2 — Fan-out/Fan-in ergänzt, Review 1 §1.7]`

Parallel ausführbar: Architect + Challenger, mit getrennten Run-Status pro Agent (`architect.run_status`, `challenger.run_status`), damit ein Fehlschlag eines Zweigs nicht den bereits erfolgreichen Zweig erneut ausführen muss. Optional später: mehrere Research-Queries.

Nicht parallel: Understanding und User-Bestätigung; Synthese vor Architect/Challenger; Evaluation vor Critic; Final Builder vor PASS.

## 35. MVP-Phasen `[v0.2 — Phase-2-Voraussetzung präzisiert, Review 2 §2.3, ADR-003]`

*(Phasen 1–8 wie v0.1)* — **Hinweis:** Phase 2 (Research) implementiert die `ResearchProvider`-Abstraktion (`search`/`extract`, Abschnitt 21) über Tavily (ADR-003, ACCEPTED). Die endgültige Freigabe von Phase 2 setzt zusätzlich die in ADR-003 festgelegte Validation voraus (mindestens 5 repräsentative Research-Aufgaben, bewertet nach Relevanz, Quellenqualität, Aktualität, Vollständigkeit, Extraktionsqualität, Kosten, Laufzeit) — bei unzureichendem Abschneiden, insbesondere bei GitHub-/Open-Source-Recherche, ist Exa der erste alternative Kandidat.

## 36. Akzeptanzkriterien MVP

*(unverändert gegenüber v0.1)*

## 37. Nicht-Ziele für V1

*(unverändert gegenüber v0.1)*

## 38. Externe Review-Schleife mit Claude

Abgeschlossen für v0.1 → v0.2. Ergebnis: siehe `reviews/FINAL_REVIEW_SUMMARY.md`. `FINAL_REVIEW_STATUS = CHANGES_REQUIRED` (v0.1) — die dort als kritisch/wichtig eingestuften Änderungen sind in v0.2 eingearbeitet. Nach Korrektur zweier bei der Nutzerprüfung gefundener Restpunkte (Abschnitt-21-Inkonsistenz, `ESCALATION_REQUIRED`-Rückwege) wurde v0.2 auf Commit `5ef2297` durch den Nutzer **APPROVED**.

## 39. Übergabepaket an OpenClaw

Nach Freigabe von v0.2:

1. MASTER_PLAN.md *(dieses Dokument)*
2. WORKFLOW_STATES.md *(erstellt)*
3. AGENT_PROMPTS.md *(erstellt)*
4. DATA_MODEL.md *(erstellt)*
5. API_CONTRACT.md *(erstellt)*
6. ACCEPTANCE_TESTS.md *(erstellt)*
7. DECISIONS.md *(erstellt)*

Optional: UI_WIREFRAMES.md *(zurückgestellt, kein Blocker für Phase 1)*, SECURITY.md *(erstellt)*, docker-compose.yml/Setup-Spezifikation *(zurückgestellt, erst ab Phase 7/8 relevant)*.

## 40. Umsetzungsregel für OpenClaw

*(unverändert gegenüber v0.1: PLAN → IMPLEMENT → TEST → REVIEW → COMMIT/CHECKPOINT → nächste Phase)*

## 41. Definition of Done

*(unverändert gegenüber v0.1)*

## 42. Leitprinzipien

*(unverändert gegenüber v0.1)*
