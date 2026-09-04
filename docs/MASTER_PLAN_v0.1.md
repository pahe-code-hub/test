# MASTER PLAN AI

## Technischer Umsetzungsplan für OpenClaw

**Version:** 0.1
**Status:** Entwurf zur externen Prüfung
**Ziel:** Übergabe an Claude für 5 Review-Pässe, anschließend Umsetzung in OpenClaw

---

## 1. Ziel des Systems

MASTER PLAN AI ist eine geführte Planungsanwendung, die aus einer zunächst groben Nutzeridee einen belastbaren, recherchierten, kritisch geprüften und freigegebenen Umsetzungsplan erzeugt.

Der Nutzer soll dabei nicht mit einer freien Prompt-Fläche allein gelassen werden, sondern durch einen strukturierten Intake geführt werden.

Die Anwendung soll:

* Nutzerideen strukturiert erfassen
* nur grundsätzliche Rückfragen stellen
* vor der Planung nach bestehenden Lösungen und Best Practices recherchieren
* zwei unabhängige Lösungsansätze erzeugen
* daraus ein konsistentes Zielkonzept synthetisieren
* das Zielkonzept kritisch prüfen
* eine unabhängige Abnahme durchführen
* notwendige Revisionen gezielt ausführen
* dem Nutzer relevante Zwischenergebnisse sichtbar machen
* an definierten Stellen eine Nutzerfreigabe verlangen
* am Ende einen vollständigen Plan und eine Präsentationsstruktur erzeugen

Grundprinzip:
Nicht möglichst viele KI-Aufrufe erzeugen, sondern unterschiedliche Denkrollen gezielt einsetzen.

## 2. UX-Grundkonzept

Die Anwendung erhält ein eigenes User Interface.

Der Nutzer sieht zu jeder Zeit:

* aktuelles Projekt
* aktuellen Workflow-Schritt
* bereits abgeschlossene Schritte
* laufende KI-Aktivitäten
* Zwischenergebnisse
* offene Rückfragen
* erforderliche Freigaben
* Revisionen
* finalen Output

Empfohlene Hauptnavigation:

1. Idee
2. Verständnis
3. Recherche
4. Lösungsentwürfe
5. Synthese
6. Prüfung
7. Abnahme
8. Ergebnis

Beispiel Statusanzeige:

* ✓ Idee
* ✓ Verständnis
* ● Recherche
* ○ Lösungsentwürfe
* ○ Synthese
* ○ Prüfung
* ○ Abnahme
* ○ Ergebnis

## 3. Nutzerinput

Der Nutzer erhält sechs getrennte Eingabebereiche.

### 3.1 ZIEL

Frage: Was möchtest du erreichen?
Nicht nur beschreiben, was gebaut werden soll, sondern welcher Nutzen erreicht werden soll.

### 3.2 PROBLEM

Frage: Welches konkrete Problem soll gelöst werden?
Was funktioniert heute schlecht, langsam, unsicher oder fehleranfällig?

### 3.3 NUTZER / STRUKTUR

Frage: Wer soll die Lösung nutzen?

Beispiele: Einzelperson, kleines Team, mehrere Abteilungen, Unternehmen, Kunden, externe Nutzer, Öffentlichkeit.

Optional können Rollen und unterschiedliche Berechtigungen beschrieben werden.

### 3.4 INTERFACE / AUSGABE

Frage: Wie soll die Lösung genutzt werden bzw. welches Ergebnis soll entstehen?

Beispiele: Desktop-Anwendung, Web-App, mobile App, CLI, Automatisierung, Hintergrunddienst, API, Prozess, Konzept, Präsentation, Entscheidungsvorlage.

### 3.5 EINSCHRÄNKUNGEN / CONSTRAINTS

Frage: Welche festen Vorgaben oder Grenzen gibt es?

Beispiele: Betriebssystem, lokal/Cloud/Hybrid, vorhandene Infrastruktur, erlaubte oder verbotene Technologien, Budget, Zeitrahmen, Datenschutz, Security, Normen/Richtlinien, vorhandene Systeme, Schnittstellen, Offline-Fähigkeit, Lizenzvorgaben.

### 3.6 KERNFUNKTIONEN

Frage: Was muss die Lösung unbedingt können?
Der Nutzer nennt die wichtigsten zwingenden Funktionen oder Fähigkeiten. Keine Detailimplementierung.

## 4. Workflow

### 4.1 Gesamtfluss

```
USER INPUT
→ Verständnisprüfung
→ Nutzerbestätigung
→ Recherche
→ Architect + Challenger parallel
→ Synthese
→ Critic
→ Evaluator
→ PASS oder gezielte Revision
→ Final Builder
→ Nutzer
```

Wichtig: Architect und Challenger arbeiten unabhängig voneinander. Sie erhalten dieselben Grundlagen, aber nicht gegenseitig ihre Ergebnisse.

## 5. Workflow-State-Machine

Empfohlene Zustände:

* DRAFT
* UNDERSTANDING
* WAITING_FOR_USER_CLARIFICATION
* WAITING_FOR_USER_CONFIRMATION
* RESEARCHING
* RESEARCH_READY
* GENERATING_SOLUTIONS
* SYNTHESIZING
* REVIEWING
* EVALUATING
* REVISION_REQUIRED
* REVISING
* ESCALATION_REQUIRED
* FINALIZING
* COMPLETED
* FAILED

Zulässige Übergänge werden explizit im Backend kontrolliert. Kein Agent darf eigenständig beliebige Workflow-Schritte überspringen.

## 6. Agenten

### 6.1 Verständnisprüfung

**Modellklasse:** MITTEL

Aufgabe: Prüfen, ob die Nutzeridee als belastbare Ausgangsbasis reicht.

Prüfbereiche: ZIEL, PROBLEM, NUTZER/STRUKTUR, INTERFACE/AUSGABE, EINSCHRÄNKUNGEN, KERNFUNKTIONEN.

Nur grundsätzliche Rückfragen. Eine Rückfrage ist nur dann zulässig, wenn die Antwort den grundsätzlichen Lösungsweg, die Architektur, den Projektumfang oder eine harte Einschränkung wesentlich verändern würde.

Keine Detailfragen zu: Technologien, Frameworks, Datenbanken, UI-Details, Implementierungsdetails, Komponenten, Feinkonfiguration, Design, Optimierung.

**Output-Status:** READY, CLARIFICATION_REQUIRED, CONTRADICTION

**Output-Regel**

Bei READY: 2–4 Sätze (was erreicht werden soll, welches Problem gelöst wird, für wen, in welche grundsätzliche Richtung es gehen soll). Abschluss: „Habe ich das so richtig verstanden?"

Bei CLARIFICATION_REQUIRED: maximal 1–3 kurze, grundlegende Rückfragen.

Bei CONTRADICTION: Widerspruch in einem Satz benennen und genau die notwendige Rückfrage stellen.

## 7. Nutzerfreigabe 1

Nach READY muss der Nutzer bestätigen. Optionen: RICHTIG VERSTANDEN, KORRIGIEREN. Ohne Bestätigung startet keine Recherche.

## 8. Research Agent

**Modellklasse:** MITTEL

Ziel: Nicht das Rad neu erfinden. Recherchiert, ob vergleichbare Produkte, Open-Source-Projekte, Frameworks, Referenzarchitekturen, etablierte technische Ansätze, Standards, Best Practices existieren.

Prüfen: vergleichbare Lösungen, grundsätzlicher Aufbau, bewährte Funktionen/Konzepte, übertragbare Best Practices, typische Schwächen, Open-Source-Basis-Eignung, wiederverwendbare Bestandteile, was bewusst selbst entwickelt werden sollte.

Quellenpriorität: offizielle Dokumentation, Standards, Herstellerdokumentation, offizielle Repositories, etablierte technische Quellen, Community-Quellen.

Regeln: keine Werbung, keine reine Link-Sammlung, keine langen Produktbeschreibungen, keine finale Architektur, keine erfundenen Produkte/Repositories/Funktionen/Quellen, Aussagen müssen belegbar sein, bei Open Source Lizenz/Aktualität/Wartbarkeit/Eignung prüfen.

**Research-Output:** maximal 3–5 relevante Lösungen, je Lösung: NAME, WAS IST DAVON INTERESSANT?, WAS KÖNNEN WIR ÜBERNEHMEN?, EIGNET SICH ALS BASIS? JA/TEILWEISE/NEIN, WICHTIGE EINSCHRÄNKUNG. Danach: ABGELEITETE BEST PRACTICES, OPEN-SOURCE-POTENZIAL, FAZIT. Die Zusammenfassung ist Bestandteil desselben Research-Aufrufs; kein zusätzlicher Summarizer erforderlich.

## 9. Architect

**Modellklasse:** HOCH

Input: bestätigter Nutzerinput, strukturierte Anforderungen, relevante Research-Ergebnisse. Nicht erhalten: Challenger-Ergebnis.

Aufgabe: Entwicklung der aus Sicht eines Principal Architects besten robusten und langfristig sinnvollen Lösung, unter Berücksichtigung von Nutzeranforderungen, Best Practices, vorhandenen Lösungen, Wartbarkeit, Erweiterbarkeit, Sicherheit, realistischer Umsetzbarkeit.

Output: grundsätzlicher Lösungsansatz, Aufbau/Struktur, wesentliche Bestandteile, Zusammenspiel, Technologien/vorhandene Lösungen, wesentliche Risiken, Umsetzungsvorgehen, offene Punkte. Overengineering vermeiden.

## 10. Challenger

**Modellklasse:** HOCH

Input: derselbe bestätigte Nutzerinput, dieselben Research-Ergebnisse. Nicht erhalten: Architect-Ergebnis.

Aufgabe: Unabhängigen Gegenentwurf entwickeln mit Schwerpunkt Einfachheit, wenige Komponenten, geringe Abhängigkeiten, geringe Betriebskosten, geringe Fehleranfälligkeit, gute Wartbarkeit, Nutzung vorhandener Lösungen, Eigenentwicklung nur wenn sinnvoll.

Explizit hinterfragen: unnötige Services, Datenbanken, Cloud-Abhängigkeiten, Framework-Komplexität, Abstraktionen, Automatisierung.

Output: eigener Lösungsansatz, Aufbau, Bestandteile, Zusammenspiel, vorhandene Lösungen/Open Source, Vor-/Nachteile, Risiken, Umsetzungsvorgehen.

## 11. KI-3 Synthesizer

**Modellklasse:** HOCH — Rolle: Chief Solution Architect

Input: bestätigter Userinput, Research-Ergebnisse, Architect-Entwurf, Challenger-Entwurf.

Aufgabe: nicht zusammenfassen, sondern die bestmögliche Gesamtlösung entwickeln.

Vorgehen: beide Entwürfe gegen das Ziel prüfen, gemeinsame starke Ansätze identifizieren, wesentliche Unterschiede/Widersprüche erkennen, unnötige Komplexität erkennen, fehlende Punkte erkennen, je Entscheidung den besseren Ansatz wählen, nur Bestandteile mit klarem Mehrwert übernehmen, bei beidseitiger Ungeeignetheit dritte Lösung entwickeln, Research-Erkenntnisse berücksichtigen, konsistentes Zielkonzept erzeugen.

Regeln: keine Kompromisslösung nur wegen zweier Entwürfe, nicht alles kombinieren, Einfachheit vor Raffinesse, Nutzerziel vor Agentenvorschlägen, keine neuen Anforderungen erfinden, offene Punkte kennzeichnen, noch keine Detailimplementierung.

Output: GRUNDSÄTZLICHER LÖSUNGSANSATZ, ÜBERNOMMENE KERNELEMENTE, VERWORFENE/GEÄNDERTE ANSÄTZE, AUFBAU/STRUKTUR, BESTEHENDE LÖSUNGEN/OPEN SOURCE, WESENTLICHE ENTSCHEIDUNGEN, RISIKEN/OFFENE PUNKTE, FAZIT.

## 12. Nutzerfreigabe 2

Nach der Synthese kann das Zielkonzept dem Nutzer gezeigt werden. Optionen: ZIELKONZEPT FREIGEBEN, ÄNDERUNGSWUNSCH. Sinnvoll vor Eintritt in die finale Qualitäts- und Umsetzungsphase.

## 13. Critic

**Modellklasse:** HOCH — Rolle: kritischer Senior Reviewer / Red Team

Prüfen: Zieltreffer, fehlende wesentliche Anforderungen, logische Widersprüche, unnötige Komplexität, bessere/einfachere Lösung, sinnvolle Research-Nutzung, technische/organisatorische Risiken, ungedeckte Annahmen, praktische Umsetzbarkeit.

Keine: kosmetische Vorschläge, Formulierungsänderungen, Detailoptimierungen ohne Nutzen, komplette Neuplanung.

Output: STATUS: OK oder STATUS: ANMERKUNGEN (max. 5 Punkte: PROBLEM, WARUM RELEVANT, EMPFOHLENE ÄNDERUNG, PRIORITÄT: KRITISCH/WICHTIG/OPTIONAL). OPTIONAL darf Freigabe nicht verhindern.

## 14. Evaluator

**Modellklasse:** HOCH — Rolle: unabhängiger finaler Prüfer

Input: bestätigter Nutzerinput, Research, Zielkonzept, Critic-Ergebnis, ggf. bereits durchgeführte Korrekturen.

Aufgabe: entscheiden, ob das Zielkonzept belastbar genug ist, um daraus den finalen Umsetzungsplan zu erzeugen.

Prüfen: Ziel getroffen, Problem gelöst, Kernfunktionen enthalten, Einschränkungen eingehalten, Konzept logisch/konsistent, realistisch umsetzbar, Risiken berücksichtigt, relevante Critic-Punkte korrekt behandelt. Keine neuen Ideen einführen, wenn nicht zwingend erforderlich.

Output: PASS (max. 3 Sätze Begründung) oder REVISION_REQUIRED (max. 3 zwingende Punkte, je Punkt PROBLEM/ERFORDERLICHE KORREKTUR).

## 15. Revision Agent

**Modellklasse:** HOCH oder MITTEL, abhängig vom Änderungsumfang

Aufgabe: nur die vom Evaluator geforderten Punkte korrigieren. Regeln: keine vollständige Neuplanung, validierte Bereiche beibehalten, keine neuen Anforderungen, keine unnötigen Zusatzänderungen.

Output: aktualisiertes Zielkonzept, GEÄNDERT/UNVERÄNDERT. Danach direkt zurück zum Evaluator — nicht erneut den vollständigen Critic durchlaufen lassen.

## 16. Revisionslogik

MAX_INTERNAL_REVISIONS = 2. Wenn danach noch REVISION_REQUIRED: Status ESCALATION_REQUIRED — der Nutzer erhält die offene Grundsatzentscheidung.

Wichtig: die fünf Claude-Prüfungen vor der OpenClaw-Umsetzung sind davon getrennt — eine externe Design-Review-Schleife dieses Masterplans, nicht die spätere interne Runtime-Schleife des Produkts.

## 17. Final Builder

**Modellklasse:** MITTEL oder HOCH

Input: nur freigegebenes Zielkonzept plus notwendige strukturierte Projektdaten.

Aufgabe: vollständigen, verständlichen, umsetzbaren Projektplan erstellen. Regeln: Zielkonzept ist verbindlich, keine neue Architektur, keine bereits geprüften Entscheidungen verändern, keine neuen Anforderungen, offene Entscheidungen sichtbar kennzeichnen, technische Details nur wenn umsetzungsrelevant.

Output: ZIEL UND AUSGANGSLAGE, EMPFOHLENE GESAMTLÖSUNG, AUFBAU UND KOMPONENTEN, FUNKTIONSUMFANG, VERWENDETE BESTEHENDE/OPEN-SOURCE-LÖSUNGEN, TECHNISCHE GRUNDENTSCHEIDUNGEN, UMSETZUNGSPLAN IN PHASEN, RISIKEN UND GEGENMASSNAHMEN, OFFENE ENTSCHEIDUNGEN, ABNAHMEKRITERIEN. Zusätzlich: kompakte Präsentationsstruktur.

## 18. Technische Architektur

Empfehlung für V1: Frontend React/TypeScript, Backend Python/FastAPI, Persistenz SQLite, Orchestrierung OpenClaw, Kommunikation REST + SSE oder WebSocket für Live-Status, Deployment zunächst lokal, optional Docker, später Windows-Paket/Installer. Keine Microservices für V1.

## 19. Systemkomponenten

```
MASTER PLAN AI
Frontend
→ Backend API
→ Workflow Orchestrator
→ OpenClaw Agent Layer
→ Model Provider Layer
→ Research Tool Layer
→ State Store
→ Audit / Logging
```

Der Browser kommuniziert niemals direkt mit dem Modellprovider. API-Schlüssel liegen nur serverseitig.

## 20. Provider-Abstraktion

Abstrakte Schnittstelle: `call_model(role, model_class, system_prompt, input_context, output_schema)`. Modellklassen: LOW, MEDIUM, HIGH. Konkrete Provider/Modelle werden per Konfiguration zugeordnet. Vorteil: Modelle austauschbar, Kosten steuerbar, A/B-Tests möglich, Rollen können unterschiedliche Modelle erhalten.

## 21. Research-Abstraktion

Abstrakte Schnittstelle: `research(query, requirements, source_policy)`. Rückgabe strukturiert: source, title, finding, relevance, confidence, license_info, retrieved_at. Nur belegte Research-Findings dürfen in spätere Agentenprompts eingehen.

## 22. Projekt-State

Nicht die komplette Chat-Historie an jeden Agenten senden. Empfohlenes Schema: project (id, title, created_at, updated_at, workflow_state, revision_count); intake (goal, problem, users_structure, interface_output, constraints, core_features); understanding (status, summary, questions, confirmed_at); research (solutions, best_practices, open_source_candidates, summary, sources); architect (output); challenger (output); synthesis (output, decisions); critic (status, findings); evaluation (status, required_changes); revisions (number, changes); final (plan, presentation).

## 23. Kontextmanagement

Jeder Agent erhält nur benötigte Informationen:

* Verständnis-Agent: Intake
* Research: bestätigter Intake, Verständniszusammenfassung
* Architect: bestätigter Intake, Research-Zusammenfassung
* Challenger: bestätigter Intake, Research-Zusammenfassung
* Synthesizer: bestätigter Intake, Research-Zusammenfassung, Architect, Challenger
* Critic: bestätigter Intake, relevante Research-Erkenntnisse, Synthese
* Evaluator: bestätigter Intake, Synthese, Critic, aktuelle Revision
* Final Builder: bestätigter Intake, freigegebenes Zielkonzept, relevante Entscheidungen

Ziel: Tokenverbrauch reduzieren und Agentenrollen sauber trennen.

## 24. Structured Outputs

Interne Agentenantworten möglichst nicht als reinen Fließtext speichern.

Beispiel Understanding: `{"status": "READY", "summary": "...", "questions": []}`

Evaluation: `{"status": "REVISION_REQUIRED", "issues": [{"problem": "...", "required_change": "..."}]}`

Die UI rendert daraus lesbare Darstellungen.

## 25. User Interface

* **Intake:** sechs große Eingabeboxen, Button „IDEE PRÜFEN"
* **Understanding:** Output anzeigen, Buttons RICHTIG VERSTANDEN / KORRIGIEREN
* **Research:** gefundene Lösungen, Best Practices, Open-Source-Potenzial, Quellen, Fazit; optional RECHERCHE FREIGEBEN / ANMERKUNG / NEU RECHERCHIEREN (konfigurierbar, da zu viele Pflicht-Klicks den Workflow bremsen können)
* **Architect/Challenger:** nebeneinander anzeigen, kein Pflicht-Human-Gate
* **Synthese:** Zielkonzept prominent anzeigen, Buttons ZIELKONZEPT FREIGEBEN / ÄNDERUNGSWUNSCH
* **Qualitätsprüfung:** Critic und Evaluator als kompakte Qualitätsübersicht
* **Final:** finalen Plan anzeigen, Exportoptionen später (Markdown, PDF, DOCX, JSON)

## 26. Live-Status

Längere Schritte dürfen die UI nicht blockieren. Backend führt längere Jobs asynchron aus, Frontend erhält Fortschritt über SSE oder WebSocket.

## 27. Fehlerbehandlung

Jeder Agentenlauf erhält: status, started_at, finished_at, provider, model, prompt_version, attempt, error, token_usage, estimated_cost.

Bei technischen Fehlern: automatischer Retry mit Limit, kein Workflow-State-Verlust, Nutzer kann fehlgeschlagenen Schritt erneut starten. Technischer Retry ist nicht dasselbe wie inhaltliche Revision.

## 28. Versionierung der Prompts

Jeder Prompt erhält: prompt_id, role, version, content, output_schema, active. Beispiel: architect_v1, challenger_v1, synthesizer_v1.

## 29. Decision Log

Beispiel:

```
ADR-001
Decision: SQLite statt PostgreSQL für V1
Reason: lokale Einzelinstanz, geringer Betriebsaufwand
Alternatives: PostgreSQL
Trade-off: geringere Skalierbarkeit bei späterer zentraler Mehrbenutzerarchitektur
Status: Accepted
```

Verhindert, dass spätere Agenten bereits geklärte Grundsatzentscheidungen immer wieder neu aufrollen.

## 30. Sicherheit

Mindestens: API-Keys nur serverseitig, Secrets über Environment/Secret Store, keine Secrets im Browser, keine Secrets in Prompts/Logs, Eingaben validieren, HTML-Ausgabe sanitizen, externe Inhalte als nicht vertrauenswürdig behandeln, Research-Inhalte dürfen keine Systemanweisungen überschreiben, Prompt-Injection aus Webseiten berücksichtigen, lokale Projektdaten nicht unnötig an externe Provider senden, Logging ohne sensible Inhalte ermöglichen.

## 31. Auditierbarkeit

Speichern: Nutzerinput, Bestätigung, Research-Quellen, Agentenoutputs, Modell/Provider, Prompt-Version, Synthese, Kritik, Evaluation, Revisionen, Nutzerfreigaben, finale Ausgabe.

## 32. Kostenkontrolle

UI optional anzeigen: Anzahl Modellaufrufe, Input-/Output-Tokens, geschätzte Kosten, Laufzeit.

Modelle nach Aufgabe: Understanding MEDIUM, Research MEDIUM, Architect HIGH, Challenger HIGH, Synthesizer HIGH, Critic HIGH, Evaluator HIGH, Revision MEDIUM/HIGH, Final Builder MEDIUM/HIGH. Keine HIGH-Modelle für reine Formatierung oder einfache Klassifikation.

## 33. OpenClaw-Verantwortung

OpenClaw übernimmt: Agenten-Orchestrierung, parallele Ausführung von Architect und Challenger, Tool-Aufrufe, Research-Anbindung, Modellaufrufe, strukturierte Agentenoutputs, Workflow-Ausführung nach Freigabe.

Nicht OpenClaw allein überlassen: persistenter Projekt-State, Berechtigungslogik, UI-State, User-Freigaben, Secret-Verwaltung, zentrale Workflow-Regeln. Der Backend-Orchestrator bleibt die kontrollierende Instanz.

## 34. Parallelisierung

Parallel ausführbar: Architect + Challenger. Optional später: mehrere Research-Queries.
Nicht parallel: Understanding und User-Bestätigung; Synthese vor Architect/Challenger; Evaluation vor Critic; Final Builder vor PASS.

## 35. MVP-Phasen

* **Phase 1 – Workflow-Kern:** Projekt anlegen, Intake speichern, State Machine, Understanding Agent, Nutzerbestätigung, einfacher Model Provider. Abnahme: Ein Projekt kann von DRAFT bis bestätigtem Verständnis laufen.
* **Phase 2 – Research:** Web-Research, Quellen, Research-Zusammenfassung, Lizenzfeld, UI-Darstellung.
* **Phase 3 – Multi-Agent Planning:** Architect, Challenger, parallele Ausführung, strukturierte Outputs.
* **Phase 4 – Synthese:** Synthesizer, Decision Log, Zielkonzept, Nutzerfreigabe.
* **Phase 5 – Qualität:** Critic, Evaluator, Revision, Revision Limit, Escalation.
* **Phase 6 – Final Output:** Final Builder, Präsentationsstruktur, Markdown Export.
* **Phase 7 – UX/Betrieb:** Live-Status, Kostenanzeige, Retry, Prompt-Versionierung, Projektübersicht, Logging.
* **Phase 8 – Export/Packaging:** PDF, DOCX, JSON, optional Windows-Paket.

## 36. Akzeptanzkriterien MVP

1. Nutzer kann alle sechs Intake-Felder erfassen.
2. Understanding Agent stellt nur grundsätzliche Rückfragen.
3. Nutzer kann Verständnis bestätigen oder korrigieren.
4. Research liefert belegte, relevante Lösungen.
5. Architect und Challenger laufen unabhängig.
6. Synthesizer erzeugt ein einheitliches Zielkonzept.
7. Critic findet relevante Schwächen ohne kosmetische Kritik.
8. Evaluator gibt PASS oder REVISION_REQUIRED.
9. Revision verändert nur beanstandete Bereiche.
10. Nach maximal zwei internen Revisionen erfolgt PASS oder ESCALATION_REQUIRED.
11. Final Builder verändert keine freigegebenen Architekturentscheidungen.
12. Workflow kann nach Neustart fortgesetzt werden.
13. API-Schlüssel befinden sich nicht im Frontend.
14. Jeder Agentenlauf ist nachvollziehbar gespeichert.
15. Fehlgeschlagene Modellaufrufe zerstören den Projekt-State nicht.

## 37. Nicht-Ziele für V1

Nicht in V1: Multi-Tenant-SaaS, komplexe Benutzerverwaltung, Microservices, Kubernetes, autonome Endlosschleifen, vollautomatische Codegenerierung des geplanten Projekts, komplexes Rechte-/Mandantensystem, Echtzeit-Kollaboration mehrerer Nutzer, eigener Vector-DB-Stack ohne nachgewiesenen Bedarf.

## 38. Externe Review-Schleife mit Claude

Dieser Masterplan soll vor der OpenClaw-Umsetzung fünf getrennte Review-Pässe erhalten. Die fünf Pässe sollen nicht fünfmal dieselbe allgemeine Frage stellen.

* **Review 1 – Logik:** Workflow, States, Übergänge, Human Gates, Schleifen, fehlende Zustände.
* **Review 2 – Architektur:** Frontend/Backend/OpenClaw, Persistenz, Provider-Abstraktion, Parallelisierung, Skalierbarkeit, unnötige Komplexität.
* **Review 3 – Agentenqualität:** Rollentrennung, Prompt-Ziele, Informationsfluss, Kontextgrenzen, Risiko gegenseitiger Beeinflussung, Halluzinationsrisiko.
* **Review 4 – Sicherheit/Betrieb:** API-Key-Schutz, Prompt Injection, Logging, Research-Inhalte, Fehlertoleranz, Recovery, Datenschutz.
* **Review 5 – Red Team/Vereinfachung:** Welche Teile dieses Plans sind unnötig kompliziert, redundant oder teuer und können entfernt werden, ohne die Ergebnisqualität wesentlich zu verschlechtern?

Nach jedem Review: nur relevante Änderungen übernehmen, Änderung begründen, keine Änderung nur wegen Stilpräferenz.

Am Ende: `FINAL_REVIEW_STATUS = APPROVED / CHANGES_REQUIRED`

## 39. Übergabepaket an OpenClaw

Nach Abschluss der fünf Reviews soll OpenClaw folgende Artefakte erhalten:

1. MASTER_PLAN.md
2. WORKFLOW_STATES.md
3. AGENT_PROMPTS.md
4. DATA_MODEL.md
5. API_CONTRACT.md
6. ACCEPTANCE_TESTS.md
7. DECISIONS.md

Optional: 8. UI_WIREFRAMES.md, 9. SECURITY.md, 10. docker-compose.yml / Setup-Spezifikation.

OpenClaw soll nicht aus einer losen Chat-Historie implementieren, sondern ausschließlich aus der freigegebenen Spezifikation.

## 40. Umsetzungsregel für OpenClaw

OpenClaw soll in kleinen, überprüfbaren Schritten implementieren. Für jede Phase: PLAN → IMPLEMENT → TEST → REVIEW → COMMIT/CHECKPOINT → nächste Phase. Keine komplette Anwendung in einem einzigen Generierungslauf. Jede Phase muss ihre Akzeptanzkriterien erfüllen, bevor die nächste beginnt.

## 41. Definition of Done

Das Projekt ist für V1 fertig, wenn: End-to-End-Workflow funktioniert, User-Gates funktionieren, Agentenrollen getrennt sind, Research belegbar ist, Projekt-State persistent ist, Revisionen begrenzt sind, Final Builder nur freigegebene Inhalte verarbeitet, Fehler sauber wiederaufgenommen werden können, Audit-Log vorhanden ist, API-Secrets geschützt sind, Markdown-Export funktioniert, definierte Akzeptanztests bestanden sind.

## 42. Leitprinzipien

1. Nutzerziel vor Technik.
2. Nur grundsätzliche Rückfragen.
3. Bestehende Lösungen vor Eigenentwicklung prüfen.
4. Architect und Challenger bleiben unabhängig.
5. Synthese statt Mittelwert.
6. Critic findet Fehler, Evaluator entscheidet.
7. Revision nur gezielt.
8. Keine Endlosschleifen.
9. State statt kompletter Chat-Historie.
10. Modelle nach Aufgabenwert einsetzen.
11. OpenClaw orchestriert Agenten; Backend kontrolliert Workflow und State.
12. Erst einfach bauen, später erweitern.
