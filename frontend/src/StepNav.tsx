import type { ProjectDetail } from "./api";

/** Abschnitt 2 (UX-Grundkonzept): "Idee → Verständnis → Recherche →
 * Lösungsentwürfe → Synthese → Prüfung → Abnahme → Ergebnis". */
const STEPS = ["Idee", "Verständnis", "Recherche", "Lösungsentwürfe", "Synthese", "Prüfung", "Abnahme", "Ergebnis"];

const STATE_TO_STEP: Record<string, number> = {
  DRAFT: 0,
  UNDERSTANDING: 0,
  WAITING_FOR_USER_CONFIRMATION: 1,
  WAITING_FOR_USER_CLARIFICATION: 1,
  RESEARCHING: 2,
  WAITING_FOR_RESEARCH_APPROVAL: 2,
  GENERATING_SOLUTIONS: 3,
  SYNTHESIZING: 4,
  WAITING_FOR_SYNTHESIS_APPROVAL: 4,
  REVIEWING: 5,
  EVALUATING: 5,
  REVISION_REQUIRED: 5,
  REVISING: 5,
  FINALIZING: 6,
  COMPLETED: 7,
};

function currentStep(project: ProjectDetail): number {
  if (project.workflow_state === "ESCALATION_REQUIRED") {
    return project.escalation_reason === "REVISION_LIMIT" ? 6 : 1;
  }
  return STATE_TO_STEP[project.workflow_state] ?? 0;
}

export function StepNav({ project }: { project: ProjectDetail }) {
  const active = currentStep(project);
  return (
    <ol className="step-nav" aria-label="Workflow-Fortschritt">
      {STEPS.map((label, i) => (
        <li key={label} className={i < active ? "done" : i === active ? "active" : "pending"}>
          <span className="step-dot" aria-hidden="true">{i < active ? "✓" : i === active ? "●" : "○"}</span>
          {label}
        </li>
      ))}
    </ol>
  );
}
