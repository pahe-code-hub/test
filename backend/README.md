# MASTER PLAN AI — Backend (Phase 1)

Implementiert ausschließlich **Phase 1 — Workflow-Kern** aus `MASTER_PLAN_v0.2.md` Abschnitt 35, freigegeben auf Commit `360b24d`. Kein Research, kein Architect/Challenger, keine Synthese, keine spätere Phase — siehe `docs/PHASE1_CHECKPOINT.md` für den vollständigen Nachweis gegen `ACCEPTANCE_TESTS.md`.

## Setup

```bash
cd backend
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...   # nur für echten Betrieb nötig, nicht für Tests
python -m alembic upgrade head        # legt masterplan.db an (SQLite, WAL-Modus)
```

## Starten

```bash
uvicorn app.main:app --reload
```

Danach: `GET http://localhost:8000/health`, API unter `http://localhost:8000/api/projects` gemäß `docs/API_CONTRACT.md` (Phase-1-Teilmenge).

## Tests

```bash
python -m pytest tests/ -v
```

Die Tests mocken den Modellaufruf (`app.routers.projects.call_model`) — sie prüfen die Workflow-/State-Logik, nicht die inhaltliche Qualität echter Modellantworten. Kein Test führt einen echten Anthropic-API-Aufruf aus; `ANTHROPIC_API_KEY` muss für `pytest` nicht gesetzt sein (Dummy-Wert in `tests/conftest.py`).

## Umfang (bewusst NICHT enthalten)

* Kein Frontend — alle Phase-1-Akzeptanzkriterien (`ACCEPTANCE_TESTS.md`) sind über REST/DB formuliert und hier per API-Test nachgewiesen, kein UI nötig, um sie zu erfüllen.
* Kein SSE-Endpunkt — Live-Status ist laut Abschnitt 35 Phase 7.
* Keine Rollen außer `understanding_v1` — Research/Architect/Challenger/Synthesizer/Critic/Evaluator/Revision/Final Builder sind Phase 2–6.
* Kein Docker/Packaging — Phase 7/8.

## Struktur

```
backend/
  app/
    main.py            FastAPI-Einstiegspunkt
    config.py           Modellklassen-Mapping, Limits (aus Abschnitt 20/32, API_CONTRACT.md)
    database.py          SQLite/WAL-Setup (DATA_MODEL.md)
    models.py             ORM: projects, intake, understanding, agent_runs (Phase-1-Teilmenge von DATA_MODEL.md)
    schemas.py             Agenten-Output-Schema + REST-Schemas
    state_machine.py        Guards aus WORKFLOW_STATES.md (Phase-1-Teilmenge)
    model_provider.py        call_model (Abschnitt 20), Anthropic-Anbindung
    security.py               Secret-Redaction (SECURITY.md §2)
    routers/projects.py        REST-Endpunkte (API_CONTRACT.md, Phase-1-Teilmenge)
  prompts/understanding_v1.md   Prompt-Datei (ADR-009)
  alembic/                       Migrationen, eine Revision für Phase 1
  tests/                          AT-1.1 bis AT-1.7 + Kosten-Notbremse
```
