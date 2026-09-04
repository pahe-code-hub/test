# Review 1 — Logik (Workflow, States, Übergänge, Human Gates, Schleifen)

**Bezug:** MASTER_PLAN_v0.1.md, Abschnitte 4, 5, 7, 12, 13, 15, 16
**Prüfrolle:** Workflow-/State-Machine-Review

## Befunde

### 1.1 Fehlende States für die UI-Freigaben aus Abschnitt 25 (KRITISCH)

Abschnitt 25 sieht zwei optionale/verpflichtende Freigabe-Interaktionen vor, die in Abschnitt 5 **kein Gegenstück** haben:

* Research: `RECHERCHE FREIGEBEN / ANMERKUNG / NEU RECHERCHIEREN`
* Synthese (Nutzerfreigabe 2, Abschnitt 12): `ZIELKONZEPT FREIGEBEN / ÄNDERUNGSWUNSCH`

`RESEARCH_READY` und `SYNTHESIZING` sind reine "Ergebnis liegt vor"-Zustände, kein Wartezustand auf Nutzerinteraktion. Ohne eigene States (z. B. `WAITING_FOR_RESEARCH_APPROVAL`, `WAITING_FOR_SYNTHESIS_APPROVAL`) kann das Backend die in Abschnitt 5 geforderte Regel „kein Agent darf eigenständig Schritte überspringen" für diese beiden Gates nicht durchsetzen — es gibt schlicht keinen State, in dem „wartet auf Nutzer" von „Agent läuft" unterscheidbar ist.

**Änderung:** Zwei zusätzliche States aufnehmen: `WAITING_FOR_RESEARCH_APPROVAL` (nur relevant, wenn das konfigurierbare Gate aktiv ist) und `WAITING_FOR_SYNTHESIS_APPROVAL`.

### 1.2 `ÄNDERUNGSWUNSCH`-Schleife ist nicht begrenzt (KRITISCH)

Abschnitt 16 definiert `MAX_INTERNAL_REVISIONS = 2` ausdrücklich nur für die Evaluator→Revision-Schleife. Der Nutzer kann aber nach Abschnitt 12 beliebig oft `ÄNDERUNGSWUNSCH` zur Synthese wählen. Das ist ein zweiter, komplett unbegrenzter Revisionskreislauf, der im Plan an keiner Stelle gedeckelt wird — ein Verstoß gegen das eigene Leitprinzip Nr. 8 „Keine Endlosschleifen" (Abschnitt 42).

**Änderung:** Eigenen, harmlosen aber vorhandenen Zähler einführen, z. B. `synthesis_revision_count` mit einer großzügigen, aber expliziten Grenze (Empfehlung: keine harte Blockade, sondern ab z. B. der 3. Runde ein Hinweis „möchtest du das Konzept grundlegend neu aufsetzen?"). Wichtig ist nicht die genaue Zahl, sondern dass der Fall überhaupt im State-Modell vorkommt.

### 1.3 `CONTRADICTION` hat keinen eigenen State (WICHTIG)

Abschnitt 6 definiert drei Output-Stati des Verständnis-Agenten: `READY`, `CLARIFICATION_REQUIRED`, `CONTRADICTION`. Abschnitt 5 kennt aber nur `WAITING_FOR_USER_CLARIFICATION`. Ein Widerspruch ist fachlich etwas anderes als eine offene Rückfrage (der Nutzer muss eine bestehende Angabe korrigieren, nicht nur ergänzen) und sollte in Audit-Log und UI auch so unterscheidbar sein.

**Änderung:** Entweder `CONTRADICTION` als reinen Sub-Status von `WAITING_FOR_USER_CLARIFICATION` in den Metadaten führen (kein neuer State nötig, aber explizit im Datenmodell, Abschnitt 22, unter `understanding.status` als Wert erlaubt), oder als eigenen State `CONTRADICTION_DETECTED` — Empfehlung: Sub-Status, um die State-Machine nicht unnötig zu vergrößern (siehe auch Review 5).

### 1.4 Kein Wiederholungslimit für Klärungsrunden (WICHTIG)

Der Nutzer kann auf `CLARIFICATION_REQUIRED` antworten, woraufhin erneut geprüft wird. Es gibt keine Regel, wie oft `UNDERSTANDING ⇄ WAITING_FOR_USER_CLARIFICATION` durchlaufen werden darf, bevor es als Eskalation behandelt wird (z. B. wenn der Nutzer wiederholt ausweichend antwortet).

**Änderung:** `MAX_CLARIFICATION_ROUNDS` (Empfehlung: 3) ergänzen; danach `ESCALATION_REQUIRED` mit Hinweis, dass die Idee grundlegend überarbeitet werden sollte.

### 1.5 `ESCALATION_REQUIRED` hat keinen definierten Ausgang (KRITISCH)

Abschnitt 16 beschreibt nur den Eintritt in `ESCALATION_REQUIRED` („Der Nutzer erhält die offene Grundsatzentscheidung"), aber keinen Übergang danach. Was passiert, wenn der Nutzer entscheidet? Zurück zu `REVISING`? Direkt `FINALIZING` mit akzeptierten Restrisiken? Abbruch (`FAILED`, oder ein neuer Endzustand `ABANDONED`)? Ohne definierten Ausgang ist dies der einzige Zustand im Diagramm ohne Weiterleitung — ein Sackgassen-Risiko in der Implementierung.

**Änderung:** Mindestens zwei explizite Übergänge aus `ESCALATION_REQUIRED` definieren: `ESCALATION_REQUIRED → REVISING` (Nutzer gibt eine Richtungsentscheidung vor, ein weiterer Revisionsversuch wird erlaubt) und `ESCALATION_REQUIRED → FINALIZING` (Nutzer akzeptiert das Konzept trotz offener Punkte ausdrücklich, offene Punkte werden in den Final-Builder-Output unter „OFFENE ENTSCHEIDUNGEN" durchgereicht).

### 1.6 `FAILED` ist als globaler Terminalzustand modelliert, sollte es aber nicht sein (WICHTIG)

Abschnitt 27 fordert: „Nutzer kann fehlgeschlagenen Schritt erneut starten" und „kein Workflow-State-Verlust". Ein einziger globaler `FAILED`-State, der in Abschnitt 5 wie ein Endzustand neben `COMPLETED` steht, widerspricht dieser Anforderung: Aus `FAILED` müsste bekannt sein, *welcher* vorherige State erneut betreten werden soll.

**Änderung:** `FAILED` nicht als eigenständigen Zustand in der Hauptkette führen, sondern als Attribut/Flag am jeweiligen State (z. B. `state = RESEARCHING`, `last_run_status = FAILED`). Retry setzt denselben State erneut aus, ohne dass „FAILED" ein State im Sinne der Übergangstabelle ist. Das ist keine kosmetische Änderung — sonst lässt sich Akzeptanzkriterium 15 aus Abschnitt 36 nicht sauber implementieren.

### 1.7 Kein Fan-out/Fan-in für `GENERATING_SOLUTIONS` (WICHTIG — siehe auch Review 2 §2.4)

Architect und Challenger laufen parallel unter einem gemeinsamen State `GENERATING_SOLUTIONS`. Der Plan sagt nicht, was passiert, wenn nur einer der beiden fehlschlägt. Ohne granularere Teilstati (`architect_status`, `challenger_status`) müsste im Fehlerfall vermutlich der komplette parallele Schritt wiederholt werden — inklusive des bereits erfolgreich gelaufenen Agenten, was unnötige Kosten verursacht (Modellklasse HOCH für beide).

**Änderung:** `GENERATING_SOLUTIONS` bleibt der sichtbare High-Level-State, aber intern zwei unabhängige Run-Datensätze (`architect.run_status`, `challenger.run_status`) führen, damit ein Retry gezielt nur den fehlgeschlagenen Zweig erneut ausführt.

### 1.8 Reihenfolge Critic/Evaluator ist konsistent — kein Befund

Die in Abschnitt 4 und 13–15 beschriebene Kette `REVIEWING (Critic) → EVALUATING (Evaluator) → REVISION_REQUIRED → REVISING → zurück zu EVALUATING (nicht erneut Critic)` ist in sich stimmig und explizit genug spezifiziert. Kein Änderungsbedarf.

## Zusammenfassung der Änderungen

| # | Befund | Priorität | Änderung |
|---|---|---|---|
| 1.1 | Fehlende Gate-States für Research-/Synthese-Freigabe | KRITISCH | `WAITING_FOR_RESEARCH_APPROVAL`, `WAITING_FOR_SYNTHESIS_APPROVAL` ergänzen |
| 1.2 | Unbegrenzte ÄNDERUNGSWUNSCH-Schleife | KRITISCH | `synthesis_revision_count` mit Soft-Limit |
| 1.3 | `CONTRADICTION` ohne State-Abbildung | WICHTIG | Als Sub-Status von `WAITING_FOR_USER_CLARIFICATION` führen |
| 1.4 | Kein Limit für Klärungsrunden | WICHTIG | `MAX_CLARIFICATION_ROUNDS = 3` |
| 1.5 | `ESCALATION_REQUIRED` ohne Ausgang | KRITISCH | Übergänge zu `REVISING` und `FINALIZING` definieren |
| 1.6 | `FAILED` als globaler Terminalzustand | WICHTIG | Als Lauf-Attribut je State statt eigener State |
| 1.7 | Kein Fan-out/Fan-in bei Architect/Challenger | WICHTIG | Getrennte Run-Status pro Agent |
