# DECISIONS.md — Decision Log MASTER PLAN AI

Format je Eintrag: Decision, Reason, Alternatives, Trade-off, Status. Fortlaufende Datei für V1 statt eigenem Datenmodell (Review 5 §5.4).

---

## ADR-001

**Decision:** SQLite statt PostgreSQL für V1
**Reason:** lokale Einzelinstanz, geringer Betriebsaufwand
**Alternatives:** PostgreSQL
**Trade-off:** geringere Skalierbarkeit bei späterer zentraler Mehrbenutzerarchitektur
**Status:** Accepted

## ADR-002

**Decision:** Server-Sent Events (SSE) statt WebSocket für Live-Status
**Reason:** Anforderung ist rein unidirektional (Server → Client, Fortschrittsanzeige je Workflow-Schritt); Nutzeraktionen laufen ohnehin über REST-POST. SSE funktioniert über Standard-HTTP ohne Protokoll-Upgrade und ist einfacher zu betreiben.
**Alternatives:** WebSocket
**Trade-off:** keiner erkennbar für den beschriebenen Anwendungsfall; falls künftig echte bidirektionale Kommunikation über denselben Kanal nötig wird, muss neu evaluiert werden.
**Status:** Accepted (Review 2 §2.1, Review 5 §5.2)

## ADR-003 — Research-/Retrieval-Provider für V1

**Status:** ACCEPTED (gemeinsam entschieden, unter Testvorbehalt — siehe Validation)

### Decision

Tavily wird für V1 als primärer Research-/Retrieval-Provider verwendet.

Die Integration erfolgt ausschließlich über eine interne `ResearchProvider`-Abstraktion (deckt sich mit der in Abschnitt 21 des Masterplans vorgesehenen Schnittstelle `search()`/`extract()` — bei dieser Gelegenheit von einem einzelnen `research()`-Aufruf auf zwei Methoden präzisiert, siehe dortige v0.2-Anmerkung). Der Research-Agent darf keine Tavily-spezifischen Abhängigkeiten enthalten.

Für V1 werden verwendet:

* Tavily Search
* Tavily Extract

Optional später: Tavily Crawl (z. B. für umfangreiche technische Dokumentationen).

**Tavily Research / Deep-Research-Funktionen werden für V1 ausdrücklich NICHT verwendet.** Der Research-Agent bleibt eigene Prompt-Logik, Quellenauswahl und Halluzinationsschutz (Abschnitt 8/21 des Masterplans) — kein fertiges Drittanbieter-Rechercheergebnis wird ungeprüft übernommen:

```
Unser Research Agent
        │
        ▼
ResearchProvider
        │
        ▼
Tavily
 ├─ Search
 └─ Extract
```

nicht `Unser Agent → Tavily Research → fertiges Ergebnis`.

### Reason

Tavily bietet Search und Content-Extraction über einen einzelnen Provider und reduziert damit den Integrationsaufwand für das MVP. Die Funktionen passen unmittelbar zum benötigten Workflow:

```
SEARCH → Quellen auswählen → Originalinhalt EXTRACT → Findings ableiten → Quellen speichern
```

Kosten aktuell (siehe `ADR-003_CANDIDATES.md` für den vollständigen Vergleich): 1.000 Credits/Monat kostenlos, Basic Search 1 Credit, Advanced Search 2 Credits, Basic Extract 1 Credit je 5 erfolgreiche URL-Extraktionen, Pay-as-you-go 0,008 $/Credit ([Tavily Docs](https://docs.tavily.com/documentation/api-reference/endpoint/crawl)). Tavily Research ist bewusst ausgeschlossen, da es je nach Modus deutlich mehr Credits pro Request verbraucht als Search+Extract ([Tavily Docs](https://docs.tavily.com/documentation/api-credits)) und dem Research-Agenten die in Abschnitt 8/21 geforderte Kontrolle über Quellenauswahl und Belegpflicht entziehen würde.

Die bestehende Provider-Abstraktion bleibt erhalten, sodass Tavily später ohne Änderung der Agentenlogik ersetzt oder ergänzt werden kann.

### Alternatives

**Exa** — sehr guter Kandidat insbesondere für technische Dokumentation, GitHub-/Code-Recherche und spätere spezialisierte Recherche (Search $7/1.000 Requests, Contents $1/1.000 Seiten). Für V1 zurückgestellt — kein ausreichend großer Vorteil gegenüber Tavily, um den zusätzlichen Wechsel zu rechtfertigen. Erster Kandidat für einen `ExaResearchProvider`, falls die Validation (siehe unten) zeigt, dass Open-Source-/Repository-Recherche mit Tavily zu schwach ist.

**Brave Search + Jina Reader** — technisch der sauberste Fit zur geforderten Provider-Unabhängigkeit (unabhängiger Suchindex, geringster Lock-in pro Baustein), aber zwei APIs, zwei Fehlerbilder, zwei Rate-Limits, zwei Kostenmodelle, zwei Secrets — für V1 unnötige Komplexität. Für eine spätere Kosten-/Lock-in-Optimierung vorgemerkt.

**Modellprovider-native Websuche (z. B. Anthropic `web_search`)** — nicht gewählt, da dadurch Research- und Modellprovider gekoppelt würden und genau die in Abschnitt 20/21 geforderte Unabhängigkeit unterlaufen würde.

### Consequences

Positiv: geringer Implementierungsaufwand; ein Research-Provider für Search + Extraction; Quellen bleiben nachvollziehbar; Provider bleibt austauschbar; einfacher Kosten- und Fehlerpfad.

Negativ: zusätzliche externe Abhängigkeit; Qualität bei GitHub-/Code-Recherche muss praktisch getestet werden; mögliche spätere Migration zu Exa oder Multi-Provider-Ansatz.

### Validation

Vor endgültiger Freigabe von MVP-Phase 2 werden mindestens 5 repräsentative Research-Aufgaben ausgeführt, darunter mindestens:

1. allgemeine bestehende Softwarelösung
2. Open-Source-Projekt auf GitHub
3. technische Framework-/Library-Recherche
4. offizielle Herstellerdokumentation
5. aktuelle Best-Practice-Recherche

Bewertet werden: Relevanz, Quellenqualität, Aktualität, Vollständigkeit, Extraktionsqualität, Kosten, Laufzeit.

Falls Tavily hierbei unzureichend abschneidet — insbesondere bei GitHub-/Open-Source-Recherche — ist Exa der erste alternative Provider-Kandidat.

## ADR-004

**Decision:** Frontend und Backend als ein gemeinsam deploybares Artefakt (ein Prozess, ein Port) statt zweier getrennter Dienste
**Reason:** V1 ist explizit Single-User/lokal (Abschnitt 37 Nicht-Ziele); zwei separate Prozesse mit CORS-Konfiguration wären unnötige Betriebskomplexität und erschweren die spätere Windows-Paket/Installer-Anforderung.
**Alternatives:** getrennte Frontend-/Backend-Deployments
**Trade-off:** etwas weniger Deployment-Flexibilität, für V1 ohne praktische Relevanz.
**Status:** Accepted (Review 2 §2.5)

## ADR-005

**Decision:** Critic erhält nur die Synthese, nicht die Architect-/Challenger-Rohentwürfe
**Reason:** Kontextreduktion zur Tokenersparnis (ursprüngliches Ziel aus Abschnitt 23 des Masterplans)
**Alternatives:** Critic erhält zusätzlich beide Rohentwürfe
**Trade-off:** Critic kann nicht erkennen, ob der Synthesizer einen wichtigen Punkt aus einem der beiden Entwürfe fälschlich verworfen hat — als akzeptiertes Risiko dokumentiert, nicht behoben.
**Status:** Accepted, bewusster Trade-off (Review 3 §3.7)

## ADR-006

**Decision:** Modellklasse LOW bleibt in der Provider-Abstraktion definiert, wird in V1 aber von keiner Rolle verwendet
**Reason:** Abstraktion verursacht keine Mehrkosten; Kategorie wird für zukünftige einfache Klassifikationsschritte (z. B. Eingangs-Plausibilitätsfilter) vorgehalten, statt sie ersatzlos zu streichen und später erneut einführen zu müssen.
**Alternatives:** LOW ersatzlos aus V1 streichen
**Trade-off:** minimal — eine ungenutzte, aber dokumentierte Kategorie in der Konfiguration.
**Status:** Accepted (Review 5 §5.3)

## ADR-007

**Decision:** Zwei unabhängige HOCH-Klasse-Entwürfe (Architect + Challenger) werden für jedes Projekt beibehalten, nicht zusammengelegt oder gestrichen
**Reason:** Trägt den Kern des Produkts (Leitprinzip 5 „Synthese statt Mittelwert"); eine einzelne Meinung statt zweier unabhängiger Ansätze würde die Produktidee selbst verändern, nicht nur die Kosten senken.
**Alternatives:** nur ein Architect-Lauf; dynamische Auswahl je nach Projektgröße
**Trade-off:** höchste Kostenposition im gesamten Workflow (mind. 3 HOCH-Aufrufe vor Beginn der Qualitätsprüfung) — bewusst in Kauf genommen, damit dieser Punkt in einer späteren Kostenoptimierungsrunde nicht versehentlich als „unnötige Komplexität" gestrichen wird.
**Status:** Accepted, bewusster Trade-off (Review 5 §5.5)

## ADR-008

**Decision:** Critic und Evaluator bleiben zwei getrennte Agentenaufrufe, werden für V1 nicht zusammengelegt
**Reason:** Trennung von offener, nicht blockierender Kritik (Critic) und bindender PASS/REVISION_REQUIRED-Entscheidung (Evaluator) trägt Leitprinzip 6.
**Alternatives:** ein kombinierter „Quality Gate"-Agent, der Findings und Pass/Fail in einem Aufruf liefert
**Trade-off:** ein zusätzlicher HOCH-Aufruf pro Prüfzyklus gegenüber einer Zusammenlegung.
**Status:** Accepted für V1; Zusammenlegung als mögliche Kostenoptimierung für eine Folgeversion vorgemerkt, nicht Teil von V1 (Review 5 §5.6)

## ADR-009

**Decision:** Prompt-Versionierung und Decision Log werden für V1 als versionierte Dateien im Repository geführt (`prompts/*_v1.md`, diese Datei), nicht als eigenes Datenbankschema mit Aktivierungslogik
**Reason:** Der Mehrwert einer DB-gestützten Prompt-Verwaltung mit „active"-Flag entsteht erst bei parallel eingesetzten Prompt-Versionen (z. B. A/B-Tests) — für V1 nicht vorgesehen.
**Alternatives:** Datenbankschema wie ursprünglich in Abschnitt 28/29 des Masterplans beschrieben
**Trade-off:** Migration auf ein DB-System nötig, sobald ein konkreter Bedarf (z. B. Prompt-A/B-Test im laufenden Betrieb) entsteht.
**Status:** Accepted (Review 5 §5.4)

## ADR-010

**Decision:** Auditierbarkeit (Abschnitt 27/31) wird über eine `agent_runs`-Tabelle in derselben SQLite-Datenbank wie der Projekt-State abgebildet, keine separate Logging-Komponente
**Reason:** Für ein lokales Single-User-V1 ist eine dedizierte Logging-Infrastruktur unnötige Komplexität; ein Join zwischen Projekt-State und Run-Log wird durch dieselbe Datenbank sogar einfacher.
**Alternatives:** separates Logging-System (z. B. strukturierte Log-Dateien, externer Log-Dienst)
**Trade-off:** keiner erkennbar für V1.
**Status:** Accepted (Review 2 §2.4, Review 5 §5.1)
