# PHASE2_CHECKPOINT.md

**Status: PHASE 2 = APPROVED** (Nutzerfreigabe 2026-09-08 auf Commit
`8dd8e60` — alle Akzeptanzkriterien real verifiziert: 28/28 Tests, echter
OpenClaw-Gateway-E2E-Nachweis, ADR-003/AT-2.3, Frontend-Build, AT-1.2
inhaltlich).

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

## Abschluss 2026-09-07 (real, außerhalb jeder Sandbox — auf dem Server des Nutzers)

Alle in den vorigen Abschnitten als sandbox-bedingt offen markierten Punkte
wurden direkt auf dem Server des Nutzers nachgeholt, mit dessen echtem
`.venv`, echtem laufendem OpenClaw-Gateway und echten dedizierten Agenten:

* `python3 -m pytest tests/ -v`: **28 von 28 bestanden**, keine Regression.
* Echter Gateway-E2E-Nachweis (`scripts/verify_gateway_e2e.py`): **bestanden**
  — siehe `PHASE1_CHECKPOINT.md` Abschnitt „Abschluss 2026-09-07" für die
  vollständigen Ergebniswerte und die drei dabei gefundenen und umgangenen
  `openclaw-sdk`-2.1.0-Bugs (Request-Payload-Form, Antwort-Textauswertung,
  fehlende Token-Auswertung — alle drei in `app/model_provider.py`
  dokumentiert und durch dedizierte Tests abgesichert).
* ADR-003/AT-2.3: bereits zuvor real validiert (Commit `5a21da3`), unverändert
  bestanden.
* Frontend-Build (`npm install && npm run build`) auf dem Server des Nutzers:
  **bestanden**, nach Behebung eines realen Versionsfehlers in
  `package.json` (Commit `ca8e26d`, `rehype-sanitize`/`typescript` zeigten auf
  nicht existente npm-Versionen). `npm install` (151 Pakete, 0 Sicherheitslücken)
  und `npm run build` (`tsc -b && vite build`, 195 Module, `✓ built in 1.58s`,
  `dist/` inkl. `index.html`/CSS/JS) liefen beide sauber durch.

* AT-1.2s inhaltliche Prüfung: **bestanden** (2026-09-08, siehe
  `PHASE1_CHECKPOINT.md` Abschnitt „AT-1.2, inhaltlicher Teil"). Alle drei
  vorbereiteten Testfälle real über `/api/projects` → `/submit` ausgeführt:
  2× `READY` ohne Rückfragen, 1× `CLARIFICATION_REQUIRED` mit genau 2 Fragen,
  beide exakt zur absichtlich offen gelassenen Rollen-/Freigabe-Dimension,
  keine zu Technik/Framework/DB/UI.

Damit sind alle in dieser und der vorigen Sitzung offenen Punkte real
geschlossen — keine verbleibenden Vorbehalte mehr.

## CHECKPOINT

Phase 2 ist implementiert, getestet (28/28), der reale OpenClaw-Gateway-
E2E-Nachweis ist erbracht, ADR-003/AT-2.3 ist real validiert, der
Frontend-Build läuft sauber durch, und AT-1.2s inhaltliche Prüfung ist real
bestanden. Keine offenen Architektur-, Infrastruktur-, Toolchain- oder
Akzeptanzkriterien-Fragen mehr. Aus technischer Sicht ist Phase 2 vollständig
freigabereif; die formale Freigabe trifft weiterhin der Nutzer.
