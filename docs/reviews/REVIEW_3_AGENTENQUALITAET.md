# Review 3 — Agentenqualität (Rollentrennung, Prompt-Ziele, Informationsfluss, Kontextgrenzen, Halluzinationsrisiko)

**Bezug:** MASTER_PLAN_v0.1.md, Abschnitte 6, 8–17, 23, 24
**Prüfrolle:** Prompt-/Agenten-Design-Review

## Befunde

### 3.1 Widerspruch zwischen Final-Builder-Kontext und -Output (KRITISCH)

Abschnitt 23 listet den Kontext des Final Builders als: *bestätigter Intake, freigegebenes Zielkonzept, relevante Entscheidungen* — **ohne** Research-Ergebnisse. Abschnitt 17 verlangt vom Final Builder jedoch als Pflichtabschnitt im Output: *„VERWENDETE BESTEHENDE / OPEN-SOURCE-LÖSUNGEN"*. Diese Information kann der Final Builder nur zuverlässig liefern, wenn er entweder (a) die konkreten Research-Findings erhält, oder (b) sich vollständig auf das verlassen kann, was der Synthesizer bereits in „BESTEHENDE LÖSUNGEN / OPEN SOURCE" (Abschnitt 11) übernommen hat. Der Plan lässt offen, welcher der beiden Wege gilt — das ist ein echter Spezifikationswiderspruch, kein Stilproblem.

**Änderung:** Abschnitt 23 präzisieren: Final Builder erhält **zusätzlich** die im Zielkonzept referenzierten Open-Source-/Bestandslösungs-Einträge (Teilmenge der Research-Ergebnisse, nicht der komplette Research-Output) — nicht den gesamten `research`-State. Das hält den Kontext klein (Prinzip aus Abschnitt 23 bleibt gewahrt) und behebt den Widerspruch.

### 3.2 Architect/Challenger liefern identische Rollen mit entgegengesetztem Bias statt echter Unabhängigkeit (WICHTIG)

Die Kontextisolation zwischen Architect und Challenger (Abschnitt 9/10: keiner sieht das Ergebnis des anderen) ist korrekt umgesetzt und methodisch richtig — das ist die Stärke dieses Designs. Das Risiko liegt woanders: Beide erhalten denselben Input, denselben Modellprovider, dieselbe Modellklasse (HOCH) — der einzige Unterschied ist eine gegensätzliche Rollenanweisung („robust/langfristig" vs. „einfach/wenig Komponenten"). Das kann zu einem vorhersehbaren, wenig informativen Kontrast führen: Architect liefert praktisch immer die komplexere Lösung, Challenger praktisch immer die einfachere — unabhängig vom tatsächlichen Projekt. Für ein sehr einfaches Projekt könnte der Architect unnötig überengineeren *müssen*, weil seine Rolle das verlangt, nicht weil das Projekt es rechtfertigt.

**Änderung:** In beiden Prompts ergänzen, dass die jeweilige Rolle kein Selbstzweck ist: Architect soll explizit auch unnötige Komplexität vermeiden (steht in Abschnitt 9 bereits als „Overengineering vermeiden" — sollte aber prominenter, nicht als Nebensatz stehen), Challenger soll explizit auch grundlegende Robustheits-/Sicherheitsanforderungen nicht der Einfachheit opfern (fehlt in Abschnitt 10 komplett). Das reduziert das Risiko einer rein formelhaften statt inhaltlich begründeten Divergenz. Kein struktureller Eingriff nötig, nur eine Prompt-Präzisierung.

### 3.3 Nur zwei von neun Agenten haben ein definiertes Output-Schema (WICHTIG)

Abschnitt 24 zeigt Structured-Output-Beispiele nur für Understanding und Evaluation. Architect, Challenger, Synthesizer, Research, Critic und Final Builder haben in den Abschnitten 8–17 zwar klar benannte Gliederungspunkte (z. B. „GRUNDSÄTZLICHER LÖSUNGSANSATZ", „ÜBERNOMMENE KERNELEMENTE" …), aber keine formale Schema-Definition. Das führt in der Praxis zu Formatdrift zwischen Modellaufrufen und erschwert das in Abschnitt 24 selbst geforderte Ziel „Die UI rendert daraus lesbare Darstellungen" — eine UI kann Fließtext mit wechselnder Überschriftenformatierung nicht zuverlässig rendern.

**Änderung:** Für jeden Agenten mit mehrteiligem Output ein JSON-Schema definieren, dessen Felder exakt den bereits im Plan benannten Gliederungspunkten entsprechen (z. B. Research: `{"solutions": [{"name": ..., "interesting": ..., "reusable": ..., "fit": "JA|TEILWEISE|NEIN", "constraint": ...}], "best_practices": [...], "open_source_potential": ..., "conclusion": ...}`). Dies ist keine inhaltliche Änderung des Plans, sondern eine notwendige Formalisierung des bereits vorhandenen Aufbaus — gehört in `AGENT_PROMPTS.md` im Übergabepaket (Abschnitt 39).

### 3.4 Kein technischer Beleg-Mechanismus gegen Research-Halluzination (KRITISCH — überschneidet sich mit Review 4 §4.1)

Abschnitt 8 fordert „keine erfundenen Produkte, Repositories, Funktionen oder Quellen" und „Aussagen über bestehende Lösungen müssen belegbar sein" — das sind reine Prompt-Anweisungen. Ein Sprachmodell kann plausibel klingende, aber nicht existierende Projekte oder Versionsstände nennen, ohne dass eine Prompt-Regel das zuverlässig verhindert. Der Plan selbst deutet mit `retrieved_at` in Abschnitt 21 bereits an, dass Findings aus echten Tool-Aufrufen stammen sollen — das ist aber nirgends als harte technische Anforderung an `research()` festgehalten, sondern liest sich wie ein Datenfeld unter vielen.

**Änderung:** Explizit festschreiben, dass `research()` ausschließlich Ergebnisse zurückgeben darf, die aus einem tatsächlichen Retrieval-Aufruf stammen (Suchtreffer/abgerufene Seite), niemals aus reinem Modellwissen ohne Beleg — der Research-Agent-Prompt darf nur mit den von `research()` gelieferten, bereits verifizierten Fundstellen arbeiten und keine zusätzlichen, nicht abgerufenen Quellen ergänzen. Dies ist eine Pipeline-Anforderung (wo greift die Beleg-Pflicht technisch, nicht nur als Prompt-Bitte), keine reine Prompt-Formulierung.

### 3.5 Evaluator-Kontextumfang bei mehreren Revisionsrunden unklar (OPTIONAL)

Abschnitt 23 nennt für den Evaluator „aktuelle Revision" (Singular) — bleibt aber offen, ob bei der zweiten Revisionsrunde die komplette Historie (Runde 1 + Runde 2) mitgegeben wird oder nur der aktuelle Stand plus das, was sich zuletzt geändert hat. Bei `MAX_INTERNAL_REVISIONS = 2` ist der Effekt gering, aber die Unschärfe sollte behoben werden, bevor die Prompts geschrieben werden.

**Änderung:** Präzisieren: Evaluator erhält immer nur den aktuellen Zielkonzept-Stand, die ursprünglichen Critic-Findings und eine kurze Diff-Notiz („was wurde in dieser Revision geändert") — nicht die vollständige Revisionshistorie. Hält den Kontext klein und verhindert, dass der Evaluator bereits akzeptierte frühere Zwischenstände erneut kommentiert.

### 3.6 Revision-Agent: Modellklassen-Wahl „HOCH oder MITTEL, abhängig vom Änderungsumfang" ohne Entscheidungsregel (OPTIONAL)

Abschnitt 15 nennt zwei mögliche Modellklassen, aber keine Regel, wer/was diese Wahl trifft. Ohne Kriterium ist das keine Konfigurationsoption, sondern eine Lücke.

**Änderung:** Für V1 vereinfachen: Revision-Agent läuft immer in Modellklasse HOCH (konsistent mit Synthesizer/Critic/Evaluator, die alle HOCH sind) — die MITTEL-Option kann als spätere Kostenoptimierung in einer Folgeversion angegangen werden, sobald echte Kostendaten vorliegen (passt zu Leitprinzip 12 „Erst einfach bauen, später erweitern").

### 3.7 Critic sieht Architect/Challenger-Rohentwürfe nicht — bewusster Trade-off, kein Fehler (kein Änderungsbedarf, aber Dokumentationslücke)

Abschnitt 23 gibt dem Critic nur die Synthese, nicht die Rohentwürfe von Architect und Challenger. Dadurch kann der Critic nicht erkennen, ob der Synthesizer einen wichtigen Punkt aus einem der beiden Entwürfe fälschlich verworfen hat. Das ist eine sinnvolle, bewusste Entscheidung zur Kontextreduktion (Abschnitt 23, Ziel: Tokenverbrauch reduzieren) und kein Fehler — sollte aber als akzeptierter Trade-off im Decision Log stehen, damit spätere Bearbeiter es nicht für ein Versehen halten.

**Änderung:** Keine funktionale Änderung; Aufnahme als ADR („Critic prüft die Synthese, nicht die Einzelentwürfe — bewusste Kontextreduktion").

## Zusammenfassung der Änderungen

| # | Befund | Priorität | Änderung |
|---|---|---|---|
| 3.1 | Final-Builder-Kontext widerspricht gefordertem Output | KRITISCH | Final Builder erhält zusätzlich referenzierte Open-Source-Findings |
| 3.2 | Architect/Challenger-Kontrast ggf. formelhaft statt inhaltlich | WICHTIG | Beide Prompts um Gegenkriterium ergänzen (Architect: keine unnötige Komplexität; Challenger: Robustheit nicht opfern) |
| 3.3 | Fehlende Output-Schemas für 6 von 9 Agenten | WICHTIG | JSON-Schema je Agent definieren, in AGENT_PROMPTS.md |
| 3.4 | Kein technischer Beleg-Mechanismus gegen Halluzination | KRITISCH | `research()` liefert nur retrieval-belegte Funde; Research-Agent darf nichts ergänzen |
| 3.5 | Evaluator-Kontext bei Mehrfachrevision unklar | OPTIONAL | Nur aktueller Stand + Diff-Notiz, keine volle Historie |
| 3.6 | Revision-Modellklassenwahl ohne Kriterium | OPTIONAL | Für V1 fest auf HOCH setzen |
| 3.7 | Critic ohne Rohentwürfe (Trade-off) | — | Als ADR dokumentieren, keine Änderung |
