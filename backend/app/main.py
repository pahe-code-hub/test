"""
FastAPI-Einstiegspunkt, Phase 1-7 + Frontend.

Kein Auth-Layer (SECURITY.md §1: V1 Single-User/lokal). Ein gemeinsam
deploybares Artefakt (ADR-004): dieser Prozess liefert REST + SSE
*und* den gebauten React-Build (`frontend/dist/`) im selben Prozess auf
demselben Port aus - kein separater Vite-Dev-Server im Normalbetrieb.
`StaticFiles` wird NACH dem API-Router gemountet, damit `/api/*` und
`/health` in jedem Fall Vorrang vor dem Frontend-Fallback haben; die
SPA selbst braucht keinen Wildcard-Routen-Fallback, da sie clientseitig
nicht mit history-Pfaden, sondern ausschließlich mit einem
Query-Parameter (`?project=<id>`) navigiert (siehe `frontend/src/App.tsx`) -
`StaticFiles(html=True)` liefert `index.html` für `/` unabhängig vom
Query-String. Fehlt der Build (`frontend/dist/` nicht vorhanden, z. B.
vor dem ersten `npm run build`), bleibt nur die REST-/SSE-API erreichbar,
kein Fehler beim Start.
"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.routers import projects

app = FastAPI(title="MASTER PLAN AI - Backend (Phase 1-7)")
app.include_router(projects.router)


@app.get("/health")
def health():
    return {"status": "ok"}


_FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if _FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=_FRONTEND_DIST, html=True), name="frontend")
