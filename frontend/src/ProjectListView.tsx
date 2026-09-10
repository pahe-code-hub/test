import { useEffect, useState } from "react";
import { api, ApiError, type ProjectSummary } from "./api";

const STATE_LABEL: Record<string, string> = {
  DRAFT: "Entwurf",
  UNDERSTANDING: "Verständnis läuft",
  WAITING_FOR_USER_CONFIRMATION: "Verständnis bestätigen",
  WAITING_FOR_USER_CLARIFICATION: "Rückfrage offen",
  ESCALATION_REQUIRED: "Entscheidung nötig",
  RESEARCHING: "Recherche läuft",
  WAITING_FOR_RESEARCH_APPROVAL: "Recherche freigeben",
  GENERATING_SOLUTIONS: "Lösungsentwürfe laufen",
  SYNTHESIZING: "Synthese läuft",
  WAITING_FOR_SYNTHESIS_APPROVAL: "Zielkonzept freigeben",
  REVIEWING: "Prüfung läuft",
  EVALUATING: "Prüfung läuft",
  REVISION_REQUIRED: "Revision läuft",
  REVISING: "Revision läuft",
  FINALIZING: "Abnahme läuft",
  COMPLETED: "Abgeschlossen",
};

/** Abschnitt 27 "Projektübersicht" (Phase 7) über GET /api/projects. */
export function ProjectListView({ onSelect }: { onSelect: (id: string) => void }) {
  const [projects, setProjects] = useState<ProjectSummary[] | null>(null);
  const [error, setError] = useState("");
  const [creating, setCreating] = useState(false);

  const load = () => api.listProjects().then(setProjects).catch((e) => setError(e instanceof ApiError ? e.message : String(e)));
  useEffect(() => { load(); }, []);

  const createProject = async () => {
    setCreating(true);
    setError("");
    try {
      const project = await api.createProject("Unbenanntes Projekt", {
        goal: "", problem: "", users_structure: "", interface_output: "", constraints: "", core_features: "",
      }, false);
      onSelect(project.id);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setCreating(false);
    }
  };

  return (
    <main>
      <h1>MASTER PLAN AI</h1>
      <button type="button" disabled={creating} onClick={createProject}>Neues Projekt</button>
      {error && <p role="alert" className="error">{error}</p>}
      {!projects && !error && <p className="muted">Lädt…</p>}
      {projects && projects.length === 0 && <p className="muted">Noch keine Projekte. Leg dein erstes an.</p>}
      {projects && projects.length > 0 && (
        <table className="project-list">
          <thead><tr><th>Titel</th><th>Status</th><th>Zuletzt geändert</th></tr></thead>
          <tbody>
            {projects.map((p) => (
              <tr
                key={p.id}
                role="button"
                tabIndex={0}
                onClick={() => onSelect(p.id)}
                onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSelect(p.id); } }}
              >
                <td>{p.title}</td>
                <td>{STATE_LABEL[p.workflow_state] ?? p.workflow_state}</td>
                <td>{new Date(p.updated_at).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </main>
  );
}
