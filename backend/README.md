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
# ADR-004). Siehe https://docs.openclaw.ai für Installation/Betrieb. Ohne
# MPA_OPENCLAW_GATEWAY_WS_URL/MPA_OPENCLAW_OPENAI_BASE_URL versucht
# openclaw-sdk automatisch einen lokalen Gateway unter ws://127.0.0.1:18789
# zu finden (siehe OpenClawClient.connect-Verhalten in app/model_provider.py).
# export MPA_OPENCLAW_GATEWAY_WS_URL=ws://127.0.0.1:18789
# export MPA_OPENCLAW_API_KEY=...        # falls der Gateway Auth verlangt

python -m alembic upgrade head        # legt masterplan.db an (SQLite, WAL-Modus)
```

**Wichtiger Vorbehalt (siehe `docs/PHASE1_CHECKPOINT.md`):** In der Implementierungs-Sandbox dieser Session stand kein laufender OpenClaw-Gateway zur Verfügung. Die Adapter-Schicht (`app/model_provider.py`) ist gegen die reale `openclaw-sdk`-Schnittstelle gebaut und mit Mocks getestet (`tests/test_model_provider.py`), aber **nicht** Ende-zu-Ende gegen einen echten, laufenden Gateway verifiziert. Das muss vor Produktivbetrieb nachgeholt werden.

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
