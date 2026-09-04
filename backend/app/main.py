"""
FastAPI-Einstiegspunkt, Phase 1.

Kein SSE-Endpunkt in Phase 1 (Live-Status ist laut MASTER_PLAN_v0.2.md
Abschnitt 35 Phase 7 - UX/Betrieb; die Phase-1-Akzeptanzkriterien in
ACCEPTANCE_TESTS.md sind ausschließlich über REST + DB-State prüfbar,
ein Polling von GET /api/projects/{id} genügt dafür). Kein
Auth-Layer (SECURITY.md §1: V1 Single-User/lokal).
"""
from fastapi import FastAPI

from app.routers import projects

app = FastAPI(title="MASTER PLAN AI - Backend (Phase 1)")
app.include_router(projects.router)


@app.get("/health")
def health():
    return {"status": "ok"}
