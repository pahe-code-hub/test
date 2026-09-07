# MASTER PLAN AI — Backend (Phase 1 + 2)

Implementiert Phase 1 (Workflow-Kern) und Phase 2 (Research) aus
`MASTER_PLAN_v0.2.md` Abschnitt 35. Keine Phase-3-Agenten oder spätere Rollen.
Siehe `docs/PHASE1_CHECKPOINT.md` und `docs/PHASE2_CHECKPOINT.md`.

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

# Dedizierte MASTER-PLAN-AI-Agenten anlegen. Beim Anlegen für beide Rollen
# das Modell konfigurieren, das MODEL_CLASS_MAP["MEDIUM"] entspricht
# (standardmäßig anthropic/claude-sonnet-5), anschließend IDs zuordnen:
openclaw agents add mpa-understanding
openclaw agents add mpa-research
export MPA_OPENCLAW_AGENT_ID_UNDERSTANDING=mpa-understanding
export MPA_OPENCLAW_AGENT_ID_RESEARCH=mpa-research

python -m alembic upgrade head        # legt masterplan.db an (SQLite, WAL-Modus)
```

Die rollenbezogenen Agent-IDs sind Pflicht. Das Backend fällt bewusst nicht
auf `main` oder einen anderen vorhandenen Agenten zurück. Insbesondere dürfen
persönliche bzw. anderweitig geroutete Agenten wie `main`, `masterplan` oder
`aktien` nicht wiederverwendet werden. Da das SDK das tatsächlich verwendete
Modell nicht im `ExecutionResult` bestätigt, müssen Provider und Modell jedes
dedizierten Gateway-Agenten mit `MODEL_PROVIDER` und der jeweiligen
`MODEL_CLASS_MAP`-Zuordnung übereinstimmen; nur dann sind Audit- und Kostendaten
korrekt.

**Bekannte openclaw-sdk-2.1.0-Bugs (Workarounds bereits enthalten, real gegen einen laufenden Gateway verifiziert):** Der HTTP-Zweig der OpenAI-kompatiblen Bridge ist im SDK an drei Stellen kaputt:

1. `Agent._build_send_params()` baut das WS-RPC-Payload (`sessionKey`, `message`, `idempotencyKey`, `timeoutMs`); `POST /v1/responses` erwartet stattdessen ausschließlich `model`/`input` und lehnt sowohl fehlende Felder als auch die WS-RPC-Felder selbst ("Unrecognized keys") mit HTTP 400 ab.
2. `Agent._execute_impl()` sucht im HTTP-Zweig den Antworttext nur unter `content`/`text`/`message` auf oberster Ebene; `/v1/responses` liefert ihn aber verschachtelt unter `output[].content[].text` - Ergebnis ohne Fix: leerer String.
3. Derselbe HTTP-Zweig wertet `usage` überhaupt nicht aus - `token_usage` bliebe `None`.

`app/model_provider.py` patcht `Agent._build_send_params` für Punkt 1 (siehe Kommentar dort) und umgeht `Agent.execute()` für Punkt 2/3 komplett, indem `call_model()` bei einer `OpenAICompatGateway`-Instanz direkt `gateway.call("chat.send", ...)` aufruft und die reale `/v1/responses`-Antwort selbst auswertet (`_call_via_openai_compat_bridge`). Der rohe WebSocket-/Local-Gateway-Pfad bleibt von alldem unberührt. Tests: `tests/test_model_provider.py::test_agent_build_send_params_rebuilds_payload_for_openai_compat_bridge`, `::test_agent_build_send_params_unchanged_for_raw_websocket_gateway`, `::test_call_model_over_openai_compat_bridge_end_to_end`. Bei einem openclaw-sdk-Update prüfen, ob die Fixes upstream vorhanden sind, und die Workarounds dann entfernen.

## Starten

```bash
uvicorn app.main:app --reload
```

Danach: `GET http://localhost:8000/health`, API unter `http://localhost:8000/api/projects` gemäß `docs/API_CONTRACT.md` (Phase-1-Teilmenge).

## Tests

```bash
python -m pytest tests/ -v
```

* `tests/test_phase1_workflow.py` mockt `app.routers.projects.call_model` — prüft die Workflow-/State-Logik, nicht die inhaltliche Qualität echter Modellantworten.
* `tests/test_model_provider.py` mockt `openclaw_sdk` direkt (Client/Agent/`execute`) — prüft die Adapter-Schicht selbst (Schema-Prompt, JSON-Parsing, Fehlerübersetzung, Agent-Caching) isoliert vom Router.

Kein Test führt einen echten Netzwerkaufruf aus (weder gegen OpenClaw noch gegen Anthropic); `ANTHROPIC_API_KEY` muss für `pytest` nicht gesetzt sein (Dummy-Wert in `tests/conftest.py`).

## Umfang (bewusst NICHT enthalten)

* Kein Frontend — alle Phase-1-Akzeptanzkriterien (`ACCEPTANCE_TESTS.md`) sind über REST/DB formuliert und hier per API-Test nachgewiesen, kein UI nötig, um sie zu erfüllen.
* Kein SSE-Endpunkt — Live-Status ist laut Abschnitt 35 Phase 7.
* Keine Rollen außer `understanding_v1` — Research/Architect/Challenger/Synthesizer/Critic/Evaluator/Revision/Final Builder sind Phase 2–6.
* Kein Docker/Packaging — Phase 7/8.
* Kein OpenClaw-Gateway-Betrieb selbst (Installation, Konfiguration, Messaging-Anbindung) — das ist Infrastruktur, die der Nutzer gemäß OpenClaws eigener Dokumentation betreibt, nicht Teil dieses Backends.

## Struktur

```
backend/
  app/
    main.py            FastAPI-Einstiegspunkt
    config.py           Modellklassen-Mapping, OpenClaw-Gateway-Konfiguration, Limits (Abschnitt 20/32, API_CONTRACT.md, ADR-011)
    database.py          SQLite/WAL-Setup (DATA_MODEL.md)
    models.py             ORM: projects, intake, understanding, agent_runs (Phase-1-Teilmenge von DATA_MODEL.md)
    schemas.py             Agenten-Output-Schema + REST-Schemas
    state_machine.py        Guards aus WORKFLOW_STATES.md (Phase-1-Teilmenge)
    model_provider.py        call_model (Abschnitt 20), Anbindung über OpenClaw (ADR-011), nicht direkt an Anthropic
    security.py               Secret-Redaction (SECURITY.md §2)
    routers/projects.py        REST-Endpunkte (API_CONTRACT.md, Phase-1-Teilmenge)
  prompts/understanding_v1.md   Prompt-Datei (ADR-009)
  alembic/                       Migrationen, eine Revision für Phase 1
  tests/                          AT-1.1 bis AT-1.7 + Kosten-Notbremse + Adapter-Tests
```
