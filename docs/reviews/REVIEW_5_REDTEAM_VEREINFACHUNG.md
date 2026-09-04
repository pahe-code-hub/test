# Review 5 — Red Team / Vereinfachung

**Bezug:** gesamter MASTER_PLAN_v0.1.md
**Prüffrage (wörtlich aus Abschnitt 38):** „Welche Teile dieses Plans sind unnötig kompliziert, redundant oder teuer und können entfernt werden, ohne die Ergebnisqualität wesentlich zu verschlechtern?"

## Vorbemerkung

Der Plan ist bereits überdurchschnittlich diszipliniert: Er hat ein explizites Nicht-Ziele-Kapitel (Abschnitt 37), eine phasenweise MVP-Planung (Abschnitt 35) und verzichtet bewusst auf Microservices/Kubernetes. Die folgenden Punkte sind Verfeinerungen an den Rändern, keine grundsätzliche Kritik am Ansatz.

## Befunde

### 5.1 „Audit / Logging" als eigene Komponente neben „State Store" (WICHTIG — Dopplung mit Review 2 §2.4)

Für ein lokales Single-User-V1 ist eine dedizierte Logging-Infrastruktur neben der ohnehin vorhandenen SQLite-Datenbank unnötige Komplexität. Der in Abschnitt 27 geforderte Datensatz je Agentenlauf (status, started_at, finished_at, provider, model, prompt_version, attempt, error, token_usage, estimated_cost) ist strukturell nichts anderes als eine `agent_runs`-Tabelle in derselben Datenbank wie der Projekt-State.

**Änderung:** „Audit/Logging" nicht als separate Systemkomponente führen, sondern als Tabelle(n) in derselben SQLite-Datei. Spart eine ganze Architekturschicht, ohne Auditierbarkeit (Abschnitt 31) zu verlieren — im Gegenteil, ein Join zwischen Projekt-State und Run-Log wird dadurch sogar einfacher.

### 5.2 SSE-vs-WebSocket-Offenlassung ist selbst unnötige Komplexität (WICHTIG — Dopplung mit Review 2 §2.1)

Zwei technisch unterschiedliche Lösungen als „oder" nebeneinander in der Spezifikation zu belassen zwingt die Umsetzung dazu, die Entscheidung später zu treffen oder (schlimmer) beides zu unterstützen. Für die beschriebenen Anforderungen (einseitige Fortschrittsanzeige) ist SSE strikt ausreichend und einfacher zu betreiben (kein eigenes Protokoll-Upgrade, funktioniert über normales HTTP).

**Änderung:** WebSocket komplett aus der V1-Spezifikation streichen, SSE als einzige Lösung führen.

### 5.3 LOW-Modellklasse ist definiert, aber nirgends verwendet (OPTIONAL)

Abschnitt 20 führt drei Modellklassen (LOW, MEDIUM, HIGH) ein. Die konkrete Zuordnung in Abschnitt 32 nutzt aber nur MEDIUM und HIGH — LOW kommt in keiner Rollenzuordnung vor. Eine im Datenmodell/der Konfiguration vorgesehene, aber nie genutzte Kategorie ist genau die Art unnötiger Abstraktion, nach der Review 5 explizit fragt.

**Änderung:** Zwei gleichwertige Optionen, beide reduzieren Unklarheit:
(a) LOW ersatzlos aus V1 streichen und bei Bedarf später wieder einführen, oder
(b) LOW ausdrücklich als „für V1 nicht genutzt, reserviert für zukünftige einfache Klassifikationsschritte (z. B. Eingangs-Plausibilitätsfilter)" kennzeichnen.
Empfehlung: (b), da die Abstraktion selbst (Abschnitt 20) keine Mehrkosten verursacht und spätere Kostenoptimierung erleichtert — nur die fehlende Erklärung ist das eigentliche Problem, nicht die Existenz der Kategorie.

### 5.4 Prompt-Versionierung und Decision Log als volle Infrastruktur schon vor MVP-Nachweis (OPTIONAL)

Abschnitt 28 beschreibt ein System mit `prompt_id, role, version, content, output_schema, active` — liest sich wie ein datenbankgestütztes Prompt-Management-System mit Aktivierungslogik. Abschnitt 29 (Decision Log) beschreibt ein strukturiertes ADR-Format. Beides ist inhaltlich richtig, aber für die ersten MVP-Phasen (Abschnitt 35, Phase 1–4) reicht dafür je eine versionierte Markdown-/YAML-Datei im Repository — der Wert einer datenbankgestützten „active"-Flag-Verwaltung entsteht erst, wenn tatsächlich mehrere Prompt-Versionen parallel im Einsatz sind (z. B. für A/B-Tests, siehe Abschnitt 20), was für V1 nicht vorgesehen ist.

**Änderung:** Für V1: Prompts als versionierte Dateien im Repository (`prompts/architect_v1.md` etc.) statt eigener DB-Tabelle mit Aktivierungslogik; Decision Log als fortlaufende `DECISIONS.md` statt eigenem Datenmodell. Migration auf ein DB-gestütztes System erst dann, wenn ein konkreter Bedarf (z. B. Prompt-A/B-Test im laufenden Betrieb) entsteht. Reduziert Bau-Aufwand vor MVP-Validierung, ohne die im Plan gewollte Nachvollziehbarkeit zu verlieren.

### 5.5 Zwei volle HOCH-Klasse-Entwürfe (Architect + Challenger) für jedes Projekt — bewusster Kern-Trade-off, kein Streichkandidat

Dies ist der teuerste Teil des Workflows (mindestens drei HOCH-Modellaufrufe — Architect, Challenger, Synthesizer — bevor überhaupt Qualitätsprüfung beginnt) und daher der naheliegendste Kandidat für eine Vereinfachung. Er ist jedoch explizit durch Leitprinzip 5 „Synthese statt Mittelwert" (Abschnitt 42) und die zentrale Produktidee (zwei unabhängige Ansätze statt einer einzelnen Meinung) getragen. Ihn zu streichen oder durch einen einzelnen Architect-Lauf zu ersetzen, würde den Kern des Produkts verändern, nicht nur seine Kosten.

**Änderung:** Keine strukturelle Änderung. Empfehlung: den Kosten-Trade-off explizit im Decision Log festhalten („zwei unabhängige HOCH-Entwürfe sind eine bewusste Qualitätsentscheidung, keine übersehene Kostenstelle"), damit dies in einer späteren Kostenoptimierungsrunde nicht versehentlich als „unnötige Komplexität" missverstanden und gestrichen wird.

### 5.6 Critic und Evaluator als zwei getrennte HOCH-Aufrufe — Kandidat für spätere Zusammenlegung, nicht für V1

Beide prüfen dieselbe Synthese aus leicht unterschiedlichem Blickwinkel (Critic: offene, nicht blockierende Kritik; Evaluator: bindende PASS/REVISION_REQUIRED-Entscheidung). Diese Trennung hat einen echten methodischen Wert (Abschnitt 42, Leitprinzip 6: „Critic findet Fehler, Evaluator entscheidet") und ist keine versehentliche Dopplung. Eine Zusammenlegung zu einem einzigen Aufruf würde einen HOCH-Aufruf pro Prüfzyklus sparen, aber die saubere Trennung von „offener Befund" und „bindender Entscheidung" aufweichen.

**Änderung:** Für V1 beibehalten wie spezifiziert (Trennung erhält Prinzip 6). Als mögliche Kostenoptimierung für eine spätere Version vormerken, aber nicht in den V1-Plan aufnehmen — passt zu Leitprinzip 12 „Erst einfach bauen, später erweitern" in seiner ursprünglichen Absicht (zuerst der methodisch sauberere Weg, Optimierung danach, mit echten Nutzungsdaten statt Vermutungen).

### 5.7 Sechs getrennte Intake-Felder — kein Vereinfachungsbedarf

Die strukturierte Sechs-Felder-Eingabe (Abschnitt 3) ist bereits die einfache, disziplinierte Lösung gegenüber einer freien Prompt-Fläche (die der Plan in Abschnitt 1 ausdrücklich vermeiden will). Kein Änderungsbedarf.

## Zusammenfassung der Änderungen

| # | Befund | Priorität | Änderung |
|---|---|---|---|
| 5.1 | Audit/Logging als eigene Komponente | WICHTIG | In SQLite-Tabellen des State Store integrieren |
| 5.2 | SSE/WebSocket-Wahlmöglichkeit offen gelassen | WICHTIG | WebSocket streichen, nur SSE |
| 5.3 | LOW-Modellklasse ungenutzt | OPTIONAL | Als „reserviert, in V1 ungenutzt" kennzeichnen |
| 5.4 | Prompt-Versionierung/Decision Log als volle Infrastruktur vor MVP-Nachweis | OPTIONAL | Für V1 als Dateien im Repository statt DB-System |
| 5.5 | Zwei HOCH-Entwürfe (Architect+Challenger) | — | Bewusster Trade-off, im Decision Log festhalten, nicht streichen |
| 5.6 | Critic+Evaluator getrennt | — | Für V1 beibehalten, als spätere Optimierung vormerken |
