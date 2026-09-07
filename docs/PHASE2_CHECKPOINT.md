# PHASE2_CHECKPOINT.md

Nachweis für **Phase 2 — Recherche** aus `MASTER_PLAN_v0.2.md` Abschnitt 35,
nach `PLAN → IMPLEMENT → TEST → REVIEW → CHECKPOINT`.

## PLAN

Umfang: `ResearchProvider.search()`/`extract()` über Tavily Search+Extract,
normalisierte Recherchepersistenz, `research_v1`, Research-Gate/API und eine
sanitisierte React-Darstellung. Nicht enthalten: Architect, Challenger,
Synthesizer oder andere Phase-3+-Agenten; SSE und Auslieferung des Frontend-
Builds bleiben gemäß Masterplan spätere Phasen.

## IMPLEMENT

* `app/research_provider.py`: providerunabhängiges Protocol und Tavily-Adapter;
  ausschließlich `/search` und `/extract`, keine Research-/Deep-Research-API.
* `app/external_data.py` und `prompts/research_v1.md`: verpflichtender
  `<external_research_data>`-Wrapper; eingebettete schließende Tags werden
  escaped.
* `models.py` + Migration `0002_phase2_research`: `research` und
  `research_sources`, inklusive FK auf den tatsächlichen Agentenlauf.
* `routers/projects.py`: deterministische Suchanfragen, Extract vor Modelllauf,
  harte URL-Allowlist gegen erfundene Quellen, atomare Persistierung,
  Gate/Rerun/Retry und Darstellung im Projekt-Detail.
* `retrieved_at` wird unmittelbar nach dem erfolgreichen Tavily-Extract-
  Response im Provider erzeugt und danach unverändert persistiert. Es ist kein
  Feld des Modelloutputs.
* `frontend/src/ResearchPanel.tsx`: Lösungen, Best Practices, Open-Source-
  Potenzial, Fazit und Quellen. Research-/Markdown-Text läuft durch
  `react-markdown` mit `skipHtml` und `rehype-sanitize`; externe Links werden
  auf HTTP(S) begrenzt.

## TEST

Hinzugefügt:

* `test_research_provider.py`: getrennte Search-/Extract-Endpunkte und echte,
  providerseitige Zeitstempelerzeugung statt Übernahme aus einer Response.
* `test_phase2_research.py`: Persistenz/Gate an und aus, Extract-Zeitstempel,
  Fremddatenwrapper und Negativtest für nicht extrahierte Quellen.
* `scripts/validate_adr003.py`: fünf reale Kategorien mit Laufzeit, Resultat-
  und Extraktionszahlen, Tavily-Scores, Credit-Schätzung und Feldern für die
  geforderte menschliche 1–5-Bewertung.
* `scripts/verify_gateway_e2e.py`: manueller, nicht in CI eingebundener
  `call_model()`-E2E-Nachweis für die Rollen `understanding` und `research`.

Ausführungsstand in dieser Sandbox:

* `python3 -m compileall -q app tests scripts alembic`: **bestanden**.
* `alembic upgrade head` gegen eine neue temporäre SQLite-Datei:
  **bestanden**; Tabellen `research` und `research_sources` inklusive Index und
  Fremdschlüsseln wurden zusammen mit dem Phase-1-Schema angelegt.
* `pytest`: **infrastrukturbedingt nicht ausführbar**. Das vorhandene `.venv`
  wurde mit Python 3.12 gebaut, die Sandbox enthält nur Python 3.11; der
  native `pydantic_core`-Build ist deshalb nicht importierbar. Paketinstallation
  war wegen fehlender DNS-Auflösung nicht möglich.
* Frontend-Build: **nicht ausführbar**, weil Node/npm in der Sandbox fehlen.
* ADR-003-Reallauf: inzwischen außerhalb der Sandbox real durchgeführt und
  bewertet; AT-2.3 ist laut `DECISIONS.md` (Commit `5a21da3`) **bestanden**.
* Gateway-E2E-Skript mit expliziten Agent-IDs ausgeführt: **BLOCKED**, weil
  bereits der Pydantic-Import des System-Python mit
  `ModuleNotFoundError: No module named 'pydantic'` fehlschlug. Der Gateway
  wurde dadurch nicht erreicht; es wurden keine Modell-, Token-, Kosten- oder
  Latenzwerte angenommen.
* Erneuter Testversuch: `python` ist nicht installiert; mit
  `.venv/bin/python -m pytest tests/ -v` meldet die vorhandene Python-3.11-
  Laufzeit `No module named pytest`. Das bestehende Toolchain-Problem bleibt.
* Erneuter Frontend-Versuch `npm install && npm run build`: **BLOCKED**, weil
  `npm` in dieser Umgebung nicht installiert ist.

## REVIEW

Code-Review gegen AT-2.1–AT-2.4 und SECURITY §3:

* AT-2.1/2.2: strukturell durch `ResearchOutput` (3–5 Lösungen,
  `source_urls`) und URL-Allowlist auf echte Extract-Ergebnisse abgesichert;
  Zeitstempel stammt aus dem Provider. Der reale Response-Vergleich bleibt
  mangels Tavily-Zugriff offen.
* AT-2.3: durch die reale Validation aus Commit `5a21da3` **bestanden**. Der
  vereinbarte Exa-Trigger trat nicht ein.
* AT-2.4: beide Gate-Pfade und Approve-Endpunkt sind implementiert und durch
  Tests beschrieben.
* Fremddaten werden einschließlich Rohinhalt genau einmal in einem escaped
  Wrapper eingebettet. Keine Phase-3-Prompts oder -Agenten wurden angelegt.
* Frühere Research-Quellen bleiben über `agent_run_id` auditierbar; die API
  zeigt nur Quellen des neuesten erfolgreichen Research-Laufs.
* Im abschließenden Review wurde ein fehlendes Mapping von
  `ResearchFinding.finding` auf die gleichnamige `NOT NULL`-Spalte entdeckt
  und vor dem Checkpoint korrigiert; ein Regression-Assert prüft den Wert.
* Im Folge-Review wurde der unsichere OpenClaw-Agent-Fallback auf `main`
  entfernt. `call_model` verlangt nun je aufgerufener Rolle eine explizite
  `MPA_OPENCLAW_AGENT_ID_<ROLLE>`-Konfiguration und schlägt andernfalls mit
  `ModelProviderError` fehl. Der Setup-Abschnitt dokumentiert dedizierte,
  modellkonforme Agenten für `understanding` und `research`; ein Regressionstest
  deckt die fehlende Rollenkonfiguration ab.

## CHECKPOINT

Phase 2 ist implementiert und ADR-003/AT-2.3 ist real validiert, aber aus Sicht
dieses Abschlusslaufs noch **nicht vollständig freigabereif**. Offen bleiben
der echte OpenClaw-/AT-1.2-Lauf sowie der Frontend-Build; beide konnten wegen
der beschriebenen Toolchain-Lücken nicht ausgeführt werden. Auch die aktuelle
Testsuite konnte hier nicht erneut gestartet werden. Die endgültige Freigabe
bleibt beim Nutzer/Claude-Code-Review.
