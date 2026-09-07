Du arbeitest im Repository unter dem aktuellen Arbeitsverzeichnis (Branch `claude/test-akso67` von `pahe-code-hub/test`). Lies zuerst, bevor du irgendetwas änderst:

1. `docs/MASTER_PLAN_v0.2.md` — der vollständig freigegebene Plan (Status: APPROVED)
2. `docs/WORKFLOW_STATES.md`, `docs/DATA_MODEL.md`, `docs/API_CONTRACT.md`, `docs/AGENT_PROMPTS.md`, `docs/ACCEPTANCE_TESTS.md`, `docs/SECURITY.md`, `docs/DECISIONS.md` — das vollständige Übergabepaket
3. `docs/PHASE1_CHECKPOINT.md` — Stand von Phase 1, inklusive zweier explizit offener Punkte
4. `backend/` — der bereits implementierte, getestete Phase-1-Code (Stil- und Konventions-Vorbild)

## Schritt 1 — Offene Phase-1-Punkte schließen

`docs/PHASE1_CHECKPOINT.md` nennt zwei offene Punkte, die nur mit echten Zugangsdaten und einem laufenden Gateway (also: hier, bei dir) geprüft werden konnten:

* **AT-1.2**: manuelle Stichprobe — 2-3 absichtlich unvollständige Testideen über `POST /api/projects` + `POST /api/projects/{id}/submit` einreichen, prüfen ob `understanding_v1` ausschließlich grundsätzliche Rückfragen stellt (Verbotsliste in `docs/AGENT_PROMPTS.md` § `understanding_v1`: keine Fragen zu Technologien, Frameworks, UI-Details, Implementierungsdetails).
* **Ende-zu-Ende-Test gegen den echten OpenClaw-Gateway**: bestätigen, dass `backend/app/model_provider.py` gegen deine tatsächliche OpenClaw-Installation funktioniert (Agent-Anlage, `execute()`, strukturierte JSON-Antwort). Falls deine OpenClaw-Version an einer Stelle abweicht (z. B. `execute_structured` statt der eigenen JSON-Parsing-Logik, andere Exception-Klassen, anderer Rückgabetyp), passe `model_provider.py` entsprechend an — die Tests in `backend/tests/test_model_provider.py` zeigen, welches Verhalten dabei erhalten bleiben muss.

Trage das Ergebnis in `docs/PHASE1_CHECKPOINT.md` nach (Abschnitt REVIEW/CHECKPOINT), inklusive etwaiger Korrekturen an `model_provider.py`.

## Schritt 2 — Phase 2 (Recherche)

Erst nach Schritt 1. Umfang exakt nach `docs/MASTER_PLAN_v0.2.md` Abschnitt 35, Phase 2: Web-Research, Quellen, Research-Zusammenfassung, Lizenzfeld, UI-Darstellung — **keine Vorwegnahme** von Architect/Challenger/Synthese/späteren Phasen.

Wichtig, bereits entschieden (nicht neu diskutieren):

* **ADR-003** (`docs/DECISIONS.md`): Tavily (Search + Extract) als Research-Provider, hinter einer `ResearchProvider`-Abstraktion (`search()`/`extract()`, siehe Masterplan Abschnitt 21) gekapselt. Tavily Research/Deep-Research ausdrücklich NICHT verwenden.
* **Validation vor Phase-2-Freigabe** (ADR-003): mindestens 5 reale Research-Aufgaben (allgemeine Softwarelösung, GitHub-Open-Source-Projekt, technische Framework-Recherche, offizielle Herstellerdokumentation, aktuelle Best-Practice-Recherche), bewertet nach Relevanz, Quellenqualität, Aktualität, Vollständigkeit, Extraktionsqualität, Kosten, Laufzeit. Ergebnis in `docs/DECISIONS.md` ADR-003 nachtragen. Falls Tavily bei GitHub/Open-Source schwach abschneidet: Exa als ersten Alternativ-Kandidaten evaluieren (im selben ADR dokumentieren, nicht stillschweigend wechseln).
* **Fremddaten-Markierung verpflichtend** (`docs/SECURITY.md` §3, `docs/AGENT_PROMPTS.md` globale Regel 2): jeder recherchierte Inhalt, der in einen Prompt eingebettet wird, muss als `<external_research_data>` markiert sein — betrifft mindestens `research_v1`, `architect_v1`, `challenger_v1`, `synthesizer_v1`, `critic_v1`, `final_builder_v1`.
* **`research_sources`-Tabelle** (`docs/DATA_MODEL.md`): jede Fundstelle einzeln mit `retrieved_at` aus dem tatsächlichen `extract()`-Aufruf speichern, nicht vom Modell erzeugen lassen (Halluzinationsschutz, Review 3 §3.4).

Arbeite nach der in Abschnitt 40 vorgegebenen Regel: **PLAN → IMPLEMENT → TEST → REVIEW → CHECKPOINT**. Schreibe am Ende einen `docs/PHASE2_CHECKPOINT.md` nach dem Vorbild von `docs/PHASE1_CHECKPOINT.md` — inklusive ehrlicher offener Punkte, falls etwas nicht vollständig automatisiert nachweisbar ist (nicht stillschweigend als erledigt markieren).

Committe in kleinen, nachvollziehbaren Schritten mit aussagekräftigen Commit-Messages, wie in der bisherigen Historie dieses Repositories zu sehen.
