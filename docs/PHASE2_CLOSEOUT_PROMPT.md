# Phase-2-Abschluss — Auftrag für phase2-builder

Du bist `phase2-builder`, Workspace `~/test`. Dieser Auftrag schließt die
letzten offenen Punkte aus `docs/PHASE2_CHECKPOINT.md` ab. Halte dich exakt an
`PLAN → IMPLEMENT → TEST → REVIEW → CHECKPOINT` (Abschnitt 40) und bleib
ausschließlich im hier beschriebenen Umfang — keine Phase-3-Agenten
(Architect/Challenger/Synthesizer/...), keine Änderung an bereits getroffenen
Entscheidungen (ADR-003, ADR-011, Tavily-Anbindung).

## Ausgangslage (bereits erledigt, nicht wiederholen)

* `docs/DECISIONS.md` ADR-003 wurde bereits mit dem realen Validation-Ergebnis
  aktualisiert (Commit `5a21da3` auf `claude/test-akso67`) — **zieh diesen
  Stand zuerst** (`git pull origin claude/test-akso67`), bevor du irgendetwas
  änderst, sonst entsteht ein unnötiger Merge-Konflikt.
* Zwei dedizierte Gateway-Agenten existieren jetzt im Gateway:
  `mpa-understanding` und `mpa-research`, beide `Model:
  anthropic/claude-sonnet-5`.
* Die Umgebungsvariablen `MPA_OPENCLAW_AGENT_ID_UNDERSTANDING=mpa-understanding`
  und `MPA_OPENCLAW_AGENT_ID_RESEARCH=mpa-research` sind auf diesem Server in
  `~/.bashrc` hinterlegt. **Verlass dich nicht darauf, dass deine
  Ausführungsumgebung `~/.bashrc` automatisch sourced** — setze sie in jedem
  Skript/Testlauf, den du ausführst, explizit selbst (`export
  MPA_OPENCLAW_AGENT_ID_UNDERSTANDING=mpa-understanding` usw.), bevor du
  `call_model` oder ein Skript aufrufst, das darauf zugreift.

## PLAN

Umfang dieses Auftrags — nur diese drei Punkte, nichts darüber hinaus:

1. Echter Ende-zu-Ende-Test von `call_model()` gegen den tatsächlich
   laufenden OpenClaw-Gateway (schließt AT-1.2 aus Phase 1 und den
   entsprechenden Phase-2-Vorbehalt).
2. `docs/PHASE1_CHECKPOINT.md` und `docs/PHASE2_CHECKPOINT.md` mit den
   *tatsächlichen* Ergebnissen aktualisieren — nur was wirklich lief und
   wirklich beobachtet wurde, keine angenommenen Werte (gleiche Ehrlichkeits-
   Regel wie bisher: BLOCKED bleibt BLOCKED, wenn es blockiert ist).
3. Frontend-Build versuchen (`npm install && npm run build` in `frontend/`).
   Falls Node/npm in deiner Sandbox weiterhin fehlen: ehrlich als weiterhin
   offen dokumentieren, nicht simulieren.

## IMPLEMENT

Lege `backend/scripts/verify_gateway_e2e.py` an, im selben Stil wie
`scripts/validate_adr003.py` (kein Pytest-Test — das würde CI von einem
laufenden Gateway abhängig machen; ein eigenständiges, manuell auszuführendes
Skript, das niemals Secrets ausgibt):

* Ruft `app.model_provider.call_model()` **echt** auf (nicht gemockt) für
  beide aktuell konfigurierten Rollen (`understanding`, `research`), jeweils
  Modellklasse `MEDIUM`, mit einem trivialen Test-System-Prompt und einem
  minimalen Pydantic-Schema (z. B. `{"antwort": str}`), das Wortlaut wie
  "Antworte mit dem JSON-Feld antwort und dem Wert 'gateway-ok'" erzwingt.
* Gibt bei Erfolg pro Rolle aus: `role`, `model` (aus dem `ModelCallResult`),
  `input_tokens`, `output_tokens`, `estimated_cost_usd`, `latency_ms` (falls
  aus dem Ergebnis ableitbar), sowie das geparste Schema-Ergebnis.
* Gibt bei Fehlschlag den vollen `ModelProviderError`-Text aus (keine
  Secrets darin, das übernimmt bereits `app/security.py`/die bestehende
  Fehlerbehandlung) und beendet mit einem von 0 verschiedenen Exit-Code —
  nicht abfangen und beschönigen.
* Kein `--local`-Flag, kein neuer Gateway-Prozess — nutzt den bereits
  laufenden Gateway über die bestehende `OpenClawClient.connect()`-
  Auto-Erkennung (`ws://127.0.0.1:18789`), exakt wie es
  `app/model_provider.py` bereits tut.

## TEST

* `PYTHONPATH=. python3 scripts/verify_gateway_e2e.py` tatsächlich ausführen
  (mit den oben genannten Env-Vars gesetzt) und die reale Ausgabe erfassen.
* Bestehende Testsuite weiterhin versuchen (`python -m pytest tests/ -v`) —
  falls dein Toolchain-Problem (Python 3.12 vs. 3.11 im `.venv`) weiterhin
  besteht, das unverändert so vermerken wie im letzten Checkpoint, nicht neu
  erfinden.
* `cd ../frontend && npm install && npm run build` versuchen, Ausgabe/Fehler
  erfassen.

## REVIEW

* Prüfe, ob `ModelCallResult.model` tatsächlich `claude-sonnet-5` zeigt (so
  wie `MODEL_CLASS_MAP["MEDIUM"]` es vorsieht) — falls nicht, das explizit im
  Checkpoint vermerken, das wäre ein eigener Befund wert (Audit-Diskrepanz,
  siehe frühere Review-Rückmeldung zum `"main"`-Fallback).
* Keine neuen Abhängigkeiten, keine neuen Rollen, keine Änderung an
  `app/model_provider.py`s öffentlicher Signatur.

## CHECKPOINT

Aktualisiere `docs/PHASE1_CHECKPOINT.md` (AT-1.2-Abschnitt) und
`docs/PHASE2_CHECKPOINT.md` (CHECKPOINT-Abschnitt) mit dem tatsächlichen
Ergebnis von Schritt 1–3. Wenn alle drei Punkte grün sind, vermerke explizit,
dass aus deiner Sicht keine Blocker für eine Phase-2-Freigabe mehr offen
sind — die endgültige Freigabe bleibt trotzdem beim Nutzer/Claude-Code-Review,
nicht bei dir. Committen und pushen auf `claude/test-akso67` (kein Force-Push,
kein Rebase), Commit-Message auf Deutsch im bisherigen Stil dieses Repos.
