# Übergabe an Claude Code direkt auf dem Server

Du läufst gerade als Claude Code CLI direkt auf `srv1900923` (`root@srv1900923:~/test`),
mit echtem Terminal-, Netzwerk- und `.venv`-Zugriff — im Unterschied zu einer zweiten
Claude-Instanz, die in einer separaten Sandbox ohne Zugriff auf diesen Server lief und
dieses Dokument geschrieben hat. Lies das komplett, bevor du irgendetwas tust.

## Was das Projekt ist

MASTER PLAN AI: ein mehrstufiges Multi-Agent-System, das aus einer rohen Nutzeridee über
Verständnisprüfung → Recherche → Multi-Agent-Planung (Architect/Challenger) → Synthese →
Qualitätssicherung (Critic/Evaluator/Revision) → Final Output einen vollständigen,
recherchierten und geprüften Umsetzungsplan erzeugt. Vollständige Spezifikation in
`docs/MASTER_PLAN_v0.2.md`, Architekturentscheidungen in `docs/DECISIONS.md` (ADR-001
bis ADR-011), Akzeptanzkriterien in `docs/ACCEPTANCE_TESTS.md`.

**8 Phasen insgesamt** (Abschnitt 35 des Plans):

| Phase | Inhalt | Status |
|---|---|---|
| 1 | Workflow-Kern | ✅ APPROVED |
| 2 | Research | ✅ APPROVED |
| 3 | Multi-Agent Planning (Architect + Challenger) | ✅ APPROVED |
| 4 | Synthese (Synthesizer, Decision Log, Nutzerfreigabe 2) | ⏳ nächster Schritt |
| 5 | Qualität (Critic, Evaluator, Revision, Revision-Limit) | offen |
| 6 | Final Output (Final Builder, Markdown-Export) | offen |
| 7 | UX/Betrieb (Live-Status/SSE, Kostenanzeige, Retry-UI, Logging) | offen |
| 8 | Export/Packaging (PDF, DOCX, JSON, optional Windows-Paket) | offen |

Lies für den aktuellen Stand jeder abgeschlossenen Phase die jeweiligen Dateien
`docs/PHASE1_CHECKPOINT.md`, `docs/PHASE2_CHECKPOINT.md`, `docs/PHASE3_CHECKPOINT.md` —
dort steht der komplette Nachweis (was implementiert, getestet, real gegen den Gateway
verifiziert wurde, inklusive aller gefundenen und behobenen Bugs).

## Bisherige Arbeitsteilung (jetzt änderst du das)

Bisher: eine Claude-Instanz in einer isolierten Sandbox ohne Server-Zugriff hat
Architektur/Reviews/Dokumentation gemacht und Git gepusht; ein OpenClaw-Agent
(`phase2-builder`, läuft über eine Codex-Engine in OpenClaws eigener Sandbox, ohne
Netzzugriff/funktionierendem `pytest`) hat auf Zuruf Code implementiert; der Nutzer
musste jeden Verifikationsschritt manuell im Terminal ausführen und die Ausgabe
zurückkopieren — mit viel Reibung durch Terminal-Paste-Korruption.

**Du (Claude Code direkt auf dem Server) kannst das jetzt selbst übernehmen**: Code
schreiben, Migrationen laufen lassen, `pytest` ausführen, curl-Workflows gegen den
echten laufenden OpenClaw-Gateway durchziehen — alles ohne den Umweg über den Nutzer.
Du musst nicht mehr alles vom Nutzer abtippen lassen, was du selbst im Terminal prüfen
kannst.

## Kritische technische Grundlagen (nicht neu erfinden)

* **ADR-011**: Modellaufrufe laufen ausschließlich über den OpenClaw-Gateway
  (`openclaw-sdk`), nie direkt gegen einen Modellanbieter. Siehe `backend/app/model_provider.py`.
* **Vier reale, verifizierte Bugs in openclaw-sdk 2.1.0**, alle bereits umgangen — lies
  den Kommentar-Block am Anfang von `backend/app/model_provider.py` und den entsprechenden
  Abschnitt in `backend/README.md`, bevor du an dieser Datei etwas änderst. Kurzfassung:
  1. `Agent._build_send_params()` baut ein WS-RPC-Payload, das die OpenAI-kompatible
     HTTP-Bridge (der einzige nutzbare Weg ohne Geräte-Pairing) ablehnt.
  2. `Agent._execute_impl()` liest die HTTP-Antwort an der falschen Stelle aus.
  3. Derselbe Pfad wertet `usage`/Tokens nicht aus.
  4. `OpenClawClient._build_gateway()` gibt den konfigurierten Timeout nicht weiter
     (bleibt bei 30s-Default) — echte `research`/`architect`/`challenger`-Aufrufe mit viel
     Kontext brauchen oft länger.
* **Setup-Umgebungsvariablen**, die für jeden echten Lauf gesetzt sein müssen (siehe
  `backend/README.md` § Setup für die vollständige, aktuelle Liste):
  `MPA_OPENCLAW_OPENAI_BASE_URL`, `MPA_OPENCLAW_API_KEY` (aus
  `~/.openclaw/openclaw.json` → `gateway.auth.token` auslesen, nie hart eintippen),
  `MPA_OPENCLAW_AGENT_ID_UNDERSTANDING`/`_RESEARCH`/`_ARCHITECT`/`_CHALLENGER`
  (bereits im Gateway angelegt: `mpa-understanding`, `mpa-research` auf
  `anthropic/claude-sonnet-5`; `mpa-architect`, `mpa-challenger` auf
  `anthropic/claude-opus-5`), `TAVILY_API_KEY` (liegt in `~/.tavily_key`, lies sie mit
  `$(cat ~/.tavily_key)` aus, nie neu eintippen), `MPA_MODEL_TIMEOUT_SECONDS=180`
  empfohlen (Default 60 kann bei realen Research-Aufrufen knapp sein).
* **Niemals** persönliche/anderweitig geroutete Agenten (`main`, `masterplan`, `aktien`)
  für Backend-Aufrufe verwenden — das Backend schlägt bewusst hart fehl statt still
  darauf zurückzufallen.
* Der OpenClaw-Gateway läuft als systemd-Service (`openclaw gateway status` zum
  Prüfen), Port 18789, `bind=loopback`.
* Migrationen: `python -m alembic upgrade head` in `backend/` — nach jedem Pull prüfen,
  ob eine neue Migration existiert, sonst `sqlite3.OperationalError: no such table`.
* Tests: `python -m pytest tests/ -v` in `backend/` — aktuell 36/36 grün, keine Regression
  einführen.
* Branch: `claude/test-akso67`. Git-Push funktioniert vom Server aus (DNS/Netzwerk
  vorhanden — im Gegensatz zu OpenClaws Sandbox).

## Sicherheitshinweis (aus konkretem Anlass)

Der Nutzer hat versehentlich zweimal echte Secrets (Tavily-Key, teilweise auch versucht
den OpenClaw-Token) im Klartext in einen Chat gepastet, weil er sie direkt in
`export`-Befehle eingetippt hat. Beide liegen jetzt in Dateien (`~/.tavily_key`) bzw.
werden per Skript ausgelesen — **immer so beibehalten, nie ein Secret direkt in einem
Befehl vorschlagen, den der Nutzer eintippen soll.** Falls du selbst mit dem Nutzer
kommunizierst (nicht nur Code schreibst): sei bei Sicherheits-relevanten Vorschlägen
genauso vorsichtig.

## Sofortiger nächster Schritt

Phase 4 (Synthese) ist noch nicht begonnen. Lies `docs/MASTER_PLAN_v0.2.md` Abschnitt 11
(Synthesizer), `docs/AGENT_PROMPTS.md` § `synthesizer_v1` (Prompt/Output-Schema bereits
vollständig spezifiziert), `docs/DATA_MODEL.md` § `synthesis`-Tabelle, und den
`WAITING_FOR_SYNTHESIS_APPROVAL`-Abschnitt in `docs/WORKFLOW_STATES.md`, bevor du mit der
Implementierung anfängst. Halte dich an `PLAN → IMPLEMENT → TEST → REVIEW → CHECKPOINT`
(Abschnitt 40) und an den Phasen-Scope — keine Vorgriffe auf Phase 5/6.

Der Nutzer hat gerade ein reales Test-Projekt im Zustand `SYNTHESIZING` in der DB
(`a3fa7ff7-7970-4a6a-b08c-1bd74ae40d32`, Terminplanungs-App) mit echten
Architect-/Challenger-Ergebnissen — nützlich für einen ersten echten
Synthesizer-Testlauf, sobald der Code steht.
