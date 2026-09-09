# MASTER PLAN AI — Backend (Phase 1–3)

Implementiert Phase 1 (Workflow-Kern), Phase 2 (Research) und Phase 3
(Architect + Challenger) aus `MASTER_PLAN_v0.2.md` Abschnitt 35. Keine
Synthese- oder späteren Rollen. Siehe die Checkpoints unter `docs/`.

Modellaufrufe laufen ausschließlich über den **OpenClaw-Gateway** (`openclaw-sdk`), nie direkt gegen einen Modellanbieter-Client (ADR-011) — siehe `docs/DECISIONS.md` ADR-011 zur Begründung dieser Korrektur gegenüber der ersten Phase-1-Implementierung.

## Setup

```bash
cd backend
pip install -r requirements.txt

# Der Modellanbieter, den OpenClaw für jeden Agenten aufruft (Abschnitt 20/33):
export ANTHROPIC_API_KEY=sk-ant-...
export TAVILY_API_KEY=...              # nur serverseitig; Search + Extract

# Der OpenClaw-Gateway-Prozess muss separat laufen (eigener Prozess, ADR-011/
# ADR-004). Siehe https://docs.openclaw.ai für Installation/Betrieb.
#
# WICHTIG: den rohen WebSocket-Pfad (MPA_OPENCLAW_GATEWAY_WS_URL bzw. die
# Auto-Erkennung ohne jede Konfiguration) NICHT verwenden - der verlangt ein
# per Ed25519 signiertes Geräte-Zertifikat unter ~/.openclaw/identity/, für
# das es in aktuellen OpenClaw-CLI-Versionen keinen Befehl zur lokalen
# Erzeugung gibt (nur Node-/Fremdgeräte-Pairing über `openclaw connect`).
# Stattdessen die OpenAI-kompatible HTTP-Bridge des Gateways verwenden:
#
# 1. Auf dem Gateway die benötigten Endpunkte aktivieren (standardmäßig aus)
#    und den Gateway neu starten:
#      openclaw config set gateway.http.endpoints.chatCompletions.enabled true
#      openclaw config set gateway.http.endpoints.responses.enabled true
#      openclaw gateway restart
#
# 2. Base-URL und den bereits vorhandenen Gateway-Token verwenden (Token
#    steht in ~/.openclaw/openclaw.json unter gateway.auth.token, NICHT hier
#    reinkopieren, sondern per Skript/Secret-Manager auslesen):
export MPA_OPENCLAW_OPENAI_BASE_URL=http://127.0.0.1:18789
export MPA_OPENCLAW_API_KEY=...        # aus gateway.auth.token

# Dedizierte MASTER-PLAN-AI-Agenten anlegen und beim Anlegen das unten
# dokumentierte MEDIUM- bzw. HIGH-Modell konfigurieren, anschließend IDs
# zuordnen:
openclaw agents add mpa-understanding
openclaw agents add mpa-research
openclaw agents add mpa-architect
openclaw agents add mpa-challenger
export MPA_OPENCLAW_AGENT_ID_UNDERSTANDING=mpa-understanding
export MPA_OPENCLAW_AGENT_ID_RESEARCH=mpa-research
export MPA_OPENCLAW_AGENT_ID_ARCHITECT=mpa-architect
export MPA_OPENCLAW_AGENT_ID_CHALLENGER=mpa-challenger

python -m alembic upgrade head        # legt masterplan.db an (SQLite, WAL-Modus)
```

Die Rollen `understanding`/`research` müssen dem MEDIUM-Modell aus
`MODEL_CLASS_MAP`, `architect`/`challenger` dem HIGH-Modell entsprechen. Die
rollenbezogenen Agent-IDs sind Pflicht. Das Backend fällt bewusst nicht
auf `main` oder einen anderen vorhandenen Agenten zurück. Insbesondere dürfen
persönliche bzw. anderweitig geroutete Agenten wie `main`, `masterplan` oder
`aktien` nicht wiederverwendet werden. Da das SDK das tatsächlich verwendete
Modell nicht im `ExecutionResult` bestätigt, müssen Provider und Modell jedes
dedizierten Gateway-Agenten mit `MODEL_PROVIDER` und der jeweiligen
`MODEL_CLASS_MAP`-Zuordnung übereinstimmen; nur dann sind Audit- und Kostendaten
korrekt.

**Bekannte openclaw-sdk-2.1.0-Bugs (Workarounds bereits enthalten, real gegen einen laufenden Gateway verifiziert):** Der HTTP-Zweig der OpenAI-kompatiblen Bridge ist im SDK an vier Stellen kaputt:

1. `Agent._build_send_params()` baut das WS-RPC-Payload (`sessionKey`, `message`, `idempotencyKey`, `timeoutMs`); `POST /v1/responses` erwartet stattdessen ausschließlich `model`/`input` und lehnt sowohl fehlende Felder als auch die WS-RPC-Felder selbst ("Unrecognized keys") mit HTTP 400 ab.
2. `Agent._execute_impl()` sucht im HTTP-Zweig den Antworttext nur unter `content`/`text`/`message` auf oberster Ebene; `/v1/responses` liefert ihn aber verschachtelt unter `output[].content[].text` - Ergebnis ohne Fix: leerer String.
3. Derselbe HTTP-Zweig wertet `usage` überhaupt nicht aus - `token_usage` bliebe `None`.
4. `OpenClawClient._build_gateway()` gibt `config.timeout` beim `openai_base_url`-Pfad nicht an `OpenAICompatGateway` weiter - die bleibt bei ihrem Konstruktor-Default von 30 Sekunden, unabhängig von `MODEL_CALL_TIMEOUT_SECONDS`. Ein echter `research`-Lauf mit extrahiertem Seiteninhalt im Kontext überschreitet 30s real und schlägt mit einem nichtssagenden `httpx.ReadTimeout` fehl, dessen `str()`-Repräsentation leer ist - äußert sich als `"... OpenClaw-Gateway-Fehler: HTTP request failed for chat.send: "` ohne jeden erkennbaren Grund dahinter.

`app/model_provider.py` patcht `Agent._build_send_params` für Punkt 1 und `OpenClawClient._build_gateway` für Punkt 4 (siehe Kommentare dort) und umgeht `Agent.execute()` für Punkt 2/3 komplett, indem `call_model()` bei einer `OpenAICompatGateway`-Instanz direkt `gateway.call("chat.send", ...)` aufruft und die reale `/v1/responses`-Antwort selbst auswertet (`_call_via_openai_compat_bridge`). Der rohe WebSocket-/Local-Gateway-Pfad bleibt von alldem unberührt. Tests: `tests/test_model_provider.py::test_agent_build_send_params_rebuilds_payload_for_openai_compat_bridge`, `::test_agent_build_send_params_unchanged_for_raw_websocket_gateway`, `::test_call_model_over_openai_compat_bridge_end_to_end`, `::test_build_gateway_forwards_configured_timeout_to_openai_compat_bridge`. Bei einem openclaw-sdk-Update prüfen, ob die Fixes upstream vorhanden sind, und die Workarounds dann entfernen.

## Starten

```bash
uvicorn app.main:app --reload
```

Danach: `GET http://localhost:8000/health`, API unter
`http://localhost:8000/api/projects` gemäß `docs/API_CONTRACT.md` bis zur
Phase-3-Grenze `SYNTHESIZING`.

## Tests

```bash
python -m pytest tests/ -v
```

* `tests/test_phase1_workflow.py` mockt `app.routers.projects.call_model` — prüft die Workflow-/State-Logik, nicht die inhaltliche Qualität echter Modellantworten.
* `tests/test_model_provider.py` mockt `openclaw_sdk` direkt (Client/Agent/`execute`) — prüft die Adapter-Schicht selbst (Schema-Prompt, JSON-Parsing, Fehlerübersetzung, Agent-Caching) isoliert vom Router.
* `tests/test_phase3_planning.py` erzwingt parallele Architect-/Challenger-
  Läufe, getrennte Schreibtransaktionen und den gezielten Zweig-Retry.

Kein Test führt einen echten Netzwerkaufruf aus (weder gegen OpenClaw noch gegen Anthropic); `ANTHROPIC_API_KEY` muss für `pytest` nicht gesetzt sein (Dummy-Wert in `tests/conftest.py`).

## Umfang (bewusst NICHT enthalten)

* Kein SSE-Endpunkt — Live-Status ist laut Abschnitt 35 Phase 7.
* Kein Synthesizer, Critic, Evaluator, Revision Agent oder Final Builder —
  diese Rollen gehören zu Phase 4–6.
* Kein Docker/Packaging — Phase 7/8.
* Kein OpenClaw-Gateway-Betrieb selbst (Installation, Konfiguration, Messaging-Anbindung) — das ist Infrastruktur, die der Nutzer gemäß OpenClaws eigener Dokumentation betreibt, nicht Teil dieses Backends.

## Struktur

```
backend/
  app/
    main.py            FastAPI-Einstiegspunkt
    config.py           Modellklassen-Mapping, OpenClaw-Gateway-Konfiguration, Limits (Abschnitt 20/32, API_CONTRACT.md, ADR-011)
    database.py          SQLite/WAL-Setup (DATA_MODEL.md)
    models.py             ORM-Tabellen bis einschließlich Phase 3
    schemas.py             Agenten-Output-Schema + REST-Schemas
    state_machine.py        Guards/States bis zur Phase-3-Grenze
    model_provider.py        call_model (Abschnitt 20), Anbindung über OpenClaw (ADR-011), nicht direkt an Anthropic
    security.py               Secret-Redaction (SECURITY.md §2)
    routers/projects.py        REST-Endpunkte und Phase-3-Fan-out/Fan-in
  prompts/                     Prompt-Dateien bis architect/challenger_v1
  alembic/                     additive Migrationen je Phase
  tests/                       Akzeptanz- und Adapter-Tests bis Phase 3
```
