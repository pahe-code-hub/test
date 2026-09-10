import { useCallback, useEffect, useState } from "react";
import { api, ApiError, ROLE_LABELS, type ProjectDetail } from "./api";
import { useProjectEvents } from "./useProjectEvents";
import { StepNav } from "./StepNav";
import { CostBadge } from "./CostBadge";
import { IntakeForm } from "./IntakeForm";
import { UnderstandingGate } from "./UnderstandingGate";
import { ResearchPanel } from "./ResearchPanel";
import { SolutionsPanel } from "./SolutionsPanel";
import { SynthesisPanel } from "./SynthesisPanel";
import { QualityPanel } from "./QualityPanel";
import { EscalationPanel } from "./EscalationPanel";
import { FinalPanel } from "./FinalPanel";

function Loading({ label }: { label: string }) {
  return <section><p className="muted spinner">{label}</p></section>;
}

/** Jeder Agentenlauf-State (siehe WORKFLOW_STATES.md "Technischer
 * Fehlschlag") kann last_run_status = FAILED annehmen, unabhängig vom
 * Panel - daher ein zentrales, state-unabhängiges Retry-Banner statt
 * das in jedem Panel einzeln nachzubilden. */
function RetryBanner({ project, onChanged }: { project: ProjectDetail; onChanged: (p: ProjectDetail) => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  if (project.last_run_status !== "FAILED") return null;
  const retry = async () => {
    setBusy(true);
    setError("");
    try {
      onChanged(await api.retry(project.id));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="banner error">
      <span>Der letzte Schritt ist fehlgeschlagen.</span>
      <button type="button" disabled={busy} onClick={retry}>{busy ? "Versuche erneut…" : "Erneut versuchen"}</button>
      {error && <span role="alert"> {error}</span>}
    </div>
  );
}

function Panel({ project, onChanged }: { project: ProjectDetail; onChanged: (p: ProjectDetail) => void }) {
  switch (project.workflow_state) {
    case "DRAFT":
      return <IntakeForm project={project} onChanged={onChanged} />;
    case "UNDERSTANDING":
      return <Loading label="Verständnis wird geprüft…" />;
    case "WAITING_FOR_USER_CONFIRMATION":
    case "WAITING_FOR_USER_CLARIFICATION":
      return <UnderstandingGate project={project} onChanged={onChanged} />;
    case "ESCALATION_REQUIRED":
      return project.escalation_reason === "REVISION_LIMIT"
        ? <><QualityPanel project={project} /><EscalationPanel project={project} onChanged={onChanged} /></>
        : <UnderstandingGate project={project} onChanged={onChanged} />;
    case "RESEARCHING":
      return <Loading label="Recherche läuft…" />;
    case "WAITING_FOR_RESEARCH_APPROVAL":
      return <ResearchPanel project={project} onChanged={onChanged} />;
    case "GENERATING_SOLUTIONS":
      return <SolutionsPanel project={project} />;
    case "SYNTHESIZING":
      return <><SolutionsPanel project={project} /><Loading label="Synthese läuft…" /></>;
    case "WAITING_FOR_SYNTHESIS_APPROVAL":
      return <SynthesisPanel project={project} onChanged={onChanged} />;
    case "REVIEWING":
    case "EVALUATING":
    case "REVISION_REQUIRED":
    case "REVISING":
      return <QualityPanel project={project} />;
    case "FINALIZING":
      return <><QualityPanel project={project} /><Loading label="Abnahme wird erstellt…" /></>;
    case "COMPLETED":
      return <FinalPanel project={project} />;
    default:
      return <p className="muted">Unbekannter Zustand: {project.workflow_state}</p>;
  }
}

export function ProjectDetailView({ projectId, onBack }: { projectId: string; onBack: () => void }) {
  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    api.getProject(projectId).then(setProject).catch((e) => setError(e instanceof ApiError ? e.message : String(e)));
  }, [projectId]);

  useEffect(() => { setProject(null); load(); }, [load]);

  const { connected, activity, activityLabel } = useProjectEvents(projectId, load);

  if (error) return <main><button type="button" className="link-button" onClick={onBack}>← Übersicht</button><p role="alert" className="error">{error}</p></main>;
  if (!project) return <main><p className="muted">Lädt…</p></main>;

  return (
    <main>
      <div className="toolbar">
        <button type="button" className="link-button" onClick={onBack}>← Übersicht</button>
        <span className={`live-dot ${connected ? "on" : "off"}`} title={connected ? "Live verbunden" : "Getrennt"} aria-hidden="true" />
        <CostBadge projectId={project.id} totalCalls={project.total_model_calls} totalCost={project.total_estimated_cost_usd} />
      </div>
      <h1>{project.title}</h1>
      <StepNav project={project} />
      {activity?.status === "RUNNING" && (
        <p className="muted spinner">{ROLE_LABELS[activity.role] ?? activityLabel} läuft…</p>
      )}
      <RetryBanner project={project} onChanged={setProject} />
      <Panel project={project} onChanged={setProject} />
    </main>
  );
}
