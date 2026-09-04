# Review 2 — Architektur (Frontend/Backend/OpenClaw, Persistenz, Provider-Abstraktion, Parallelisierung, Skalierbarkeit)

**Bezug:** MASTER_PLAN_v0.1.md, Abschnitte 18, 19, 20, 26, 33, 34
**Prüfrolle:** System-/Infrastrukturarchitektur

## Befunde

### 2.1 SSE vs. WebSocket bleibt unentschieden (WICHTIG)

Abschnitt 18 und 26 nennen „SSE oder WebSocket" als gleichwertige Alternativen. Für ein produktives Spezifikationsdokument ist das keine Architekturentscheidung, sondern eine offene Frage, die an OpenClaw durchgereicht würde — genau das, was Abschnitt 29 (Decision Log) verhindern soll.

Die tatsächlichen Anforderungen (Fortschrittsstatus wie in Abschnitt 26 beschrieben: „✓ / ● / ○" je Schritt) sind rein serverseitig ausgelöste, unidirektionale Ereignisse. Es gibt keinen beschriebenen Bedarf für Client→Server-Nachrichten über denselben Kanal (Nutzeraktionen laufen ohnehin über REST-POST, siehe Abschnitt 19).

**Änderung:** Für V1 SSE festlegen (einfacher, kein Verbindungs-Handshake-Overhead, funktioniert mit Standard-HTTP-Reverse-Proxies ohne Sonderkonfiguration, ausreichend für unidirektionale Statusupdates). WebSocket erst dann evaluieren, wenn ein echter bidirektionaler Bedarf entsteht (aktuell nicht erkennbar). Diese Entscheidung gehört als ADR in Abschnitt 29.

### 2.2 SQLite + parallele Schreibzugriffe (KRITISCH)

Architect und Challenger laufen laut Abschnitt 34 parallel und schreiben vermutlich beide ihr Ergebnis in denselben Projekt-State (Abschnitt 22: `architect.output`, `challenger.output` im selben `project`-Datensatz). SQLite erlaubt nur einen gleichzeitigen Schreibzugriff (auch im WAL-Modus ist paralleles Schreiben serialisiert, nicht simultan). Ohne explizite Regelung entsteht ein reales Risiko von `database is locked`-Fehlern genau an der einzigen Stelle im Workflow, die bewusst parallelisiert wurde.

**Änderung:**
* SQLite im WAL-Modus (`PRAGMA journal_mode=WAL`) betreiben.
* Jeder Agentenlauf schreibt sein Ergebnis in eine eigene Zeile/Tabelle (`agent_runs`) statt in ein gemeinsam aktualisiertes JSON-Blob-Feld, damit Architect- und Challenger-Schreibvorgänng nicht dieselbe Zeile sperren.
* Schreibvorgänge kurz und transaktional halten (Ergebnis erst nach vollständigem Modellaufruf in einem einzigen Commit schreiben, nicht inkrementell) — reduziert zusätzlich das Risiko aus Review 4 (Atomarität bei Retries).

### 2.3 Research Tool Layer ist technisch nicht spezifiziert (KRITISCH — Blocker für Phase 2)

Abschnitt 19 nennt „Research Tool Layer" als Komponente, Abschnitt 21 definiert die Schnittstelle `research(query, requirements, source_policy)`, aber es fehlt jede Aussage dazu, **womit** tatsächlich recherchiert wird (Suchindex, Web-Fetch-Tool, welcher Anbieter). Das ist kein Stilproblem, sondern eine harte Voraussetzung dafür, dass Abschnitt 8 überhaupt funktionieren kann — insbesondere die Anforderung „Aussagen über bestehende Lösungen müssen belegbar sein" setzt voraus, dass `research()` echte, abrufbare Quellen liefert und nicht aus dem Modellgedächtnis geraten wird (siehe auch Review 3 §3.6 und Review 4 §4.1).

**Änderung:** Vor Beginn von Phase 2 eine explizite Entscheidung treffen und als ADR dokumentieren, z. B.: OpenClaw-natives Web-Such-/Fetch-Tool, sofern vorhanden, sonst eine dedizierte Such-API. Bis diese Entscheidung getroffen ist, ist Abschnitt 8 nicht implementierbar — dies ist der einzige Punkt in der gesamten Architektur-Review, der als echter Blocker (nicht nur Verbesserung) einzustufen ist.

### 2.4 Zu viele Schichten für ein lokales Single-User-V1 (WICHTIG)

Das Diagramm in Abschnitt 19 listet acht Boxen: Frontend → Backend API → Workflow Orchestrator → OpenClaw Agent Layer → Model Provider Layer → Research Tool Layer → State Store → Audit/Logging. Für eine Anwendung, die laut Abschnitt 37 explizit **kein** Multi-Tenant-SaaS und **keine** Microservices sein soll, ist das eine unternehmensartige Schichtung. Zwei der Boxen sind für V1 keine eigenständigen Komponenten, sondern Aspekte vorhandener Komponenten:

* „Workflow Orchestrator" und „Backend API" sind für ein lokales V1 dieselbe Prozessgrenze (ein FastAPI-Prozess, der sowohl REST-Endpunkte bedient als auch die State Machine ausführt). Sie separat aufzuführen suggeriert einen eigenen Dienst, der nicht gerechtfertigt ist.
* „Audit/Logging" als eigene Box neben „State Store": siehe Review 5 §5.3 — für V1 dieselbe SQLite-Datenbank.

**Änderung:** Diagramm für V1 auf drei tatsächliche Prozess-/Speichergrenzen reduzieren: *Frontend (React)* → *Backend (FastAPI, enthält Workflow-Logik und Orchestrierungsaufrufe an OpenClaw)* → *SQLite (State + Audit)*, mit OpenClaw/Model-Provider/Research-Tool als vom Backend aufgerufene Bibliotheken/Services, nicht als eigene Architekturschichten. Das ist eine Darstellungs-/Dokumentationsänderung, keine Funktionsänderung — sie verhindert aber, dass spätere Umsetzung unnötig viele Modulgrenzen und Interfaces für V1 baut.

### 2.5 Deployment-Topologie (Frontend/Backend getrennt oder gemeinsam?) ist offen (OPTIONAL)

Abschnitt 18 sagt „zunächst lokal, optional Docker", klärt aber nicht, ob React-Frontend und FastAPI-Backend ein gemeinsam deploybares Artefakt sind. Für ein lokales Werkzeug ohne Multi-User-Anspruch ist ein einzelner Prozess (FastAPI liefert den gebauten React-Build als statische Dateien aus und stellt zugleich die REST-/SSE-Endpunkte bereit) deutlich einfacher zu betreiben als zwei separate Prozesse mit CORS-Konfiguration.

**Änderung:** Für V1 als ein gemeinsam deploybares Artefakt festlegen (ein Prozess, ein Port). Passt zur späteren „Windows-Paket/Installer"-Anforderung aus Abschnitt 18 — ein Installer für zwei separate Dienste wäre unnötig kompliziert.

### 2.6 Schema-Migrationen nicht erwähnt (OPTIONAL)

Das Datenmodell in Abschnitt 22 wird sich über die acht MVP-Phasen (Abschnitt 35) hinweg mehrfach ändern (neue Felder je Phase). Ohne ein Migrationswerkzeug (z. B. Alembic) drohen manuelle, fehleranfällige Schemaanpassungen während der iterativen Umsetzung.

**Änderung:** Alembic (oder vergleichbar) von Phase 1 an einplanen, auch wenn V1 nur eine lokale SQLite-Datei ist — die MVP-Phasen selbst sind der Grund dafür, nicht ein hypothetischer Mehrbenutzerbetrieb.

### 2.7 Provider-Abstraktion (`call_model`) — grundsätzlich stimmig, ein Punkt fehlt (WICHTIG)

Die Schnittstelle aus Abschnitt 20 ist sinnvoll knapp gehalten. Es fehlt jedoch jede Aussage zu Timeout- und Backoff-Verhalten bei Provider-Fehlern (Rate-Limit, 5xx, Timeout) — das ist keine rein betriebliche Frage, sondern beeinflusst direkt Abschnitt 27 (Fehlerbehandlung/Retry). Ohne eine in der Abstraktion selbst verankerte Grenze könnte ein einzelner Agentenlauf unbegrenzt lange hängen und den State auf unbestimmte Zeit in einem laufenden Zustand halten (z. B. `GENERATING_SOLUTIONS` ohne Fortschritt).

**Änderung:** `call_model` um ein Timeout-Argument und eine begrenzte Anzahl interner Provider-Retries (getrennt von den in Abschnitt 27 beschriebenen Workflow-Retries) ergänzen; bei Überschreitung wird der Agentenlauf als technisch fehlgeschlagen markiert (siehe Review 1 §1.6).

## Zusammenfassung der Änderungen

| # | Befund | Priorität | Änderung |
|---|---|---|---|
| 2.1 | SSE/WebSocket unentschieden | WICHTIG | SSE für V1 festlegen, als ADR dokumentieren |
| 2.2 | SQLite-Schreibkonflikte bei paralleler Ausführung | KRITISCH | WAL-Modus, getrennte Zeilen pro Agentenlauf, kurze Transaktionen |
| 2.3 | Research Tool Layer technisch unspezifiziert | KRITISCH (Blocker Phase 2) | Konkrete Recherche-Anbindung vor Phase 2 als ADR entscheiden |
| 2.4 | Zu viele Architekturschichten für V1 | WICHTIG | Diagramm auf Frontend/Backend/SQLite reduzieren, Rest als Bibliotheken |
| 2.5 | Deployment-Topologie offen | OPTIONAL | Ein gemeinsames Artefakt/Prozess für V1 |
| 2.6 | Keine Migrationsstrategie | OPTIONAL | Alembic ab Phase 1 |
| 2.7 | Kein Timeout/Backoff in Provider-Abstraktion | WICHTIG | Timeout- und Retry-Parameter in `call_model` aufnehmen |
