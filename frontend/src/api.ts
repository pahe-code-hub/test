/**
 * Typisierter Fetch-Client für API_CONTRACT.md. Spiegelt exakt die
 * Pydantic-Schemas aus backend/app/schemas.py (ProjectDetail und
 * Unterobjekte) sowie die dort dokumentierten Fehlerantworten
 * ({"error": {"code","message"}}).
 */

export type IntakeOut = {
  goal: string;
  problem: string;
  users_structure: string;
  interface_output: string;
  constraints: string;
  core_features: string;
  updated_at: string;
};

export type UnderstandingOut = {
  status: "READY" | "CLARIFICATION_REQUIRED" | "CONTRADICTION" | null;
  summary: string | null;
  questions: string[] | null;
  contradiction_note: string | null;
  confirmed_at: string | null;
};

export type ResearchSolution = {
  name: string;
  interesting: string;
  reusable: string;
  fit: string;
  constraint: string;
  source_urls: string[];
};

export type ResearchSourceOut = {
  id: string;
  url: string;
  title: string;
  finding: string;
  relevance: number | null;
  confidence: number | null;
  license_info: string | null;
  retrieved_at: string;
  provider: string;
};

export type ResearchOut = {
  solutions: ResearchSolution[];
  best_practices: string[];
  open_source_potential: string;
  conclusion: string;
  approved_at: string | null;
  sources: ResearchSourceOut[];
};

export type SolutionOutput = {
  approach: string;
  structure: string;
  components: string[];
  interactions: string;
  technologies: string[];
  risks: string[];
  implementation_approach: string;
  open_points: string[];
};

export type SolutionAgentOut = {
  output: SolutionOutput | null;
  run_status: "PENDING" | "RUNNING" | "DONE" | "FAILED";
};

export type SynthesisExistingSolution = { source_id: string; note: string };

export type SynthesisOutput = {
  approach: string;
  adopted_core_elements: string[];
  discarded_or_changed_approaches: string[];
  structure: string;
  existing_solutions_open_source: SynthesisExistingSolution[];
  key_decisions: string[];
  risks_open_points: string[];
  conclusion: string;
};

export type SynthesisOut = {
  version: number;
  output: SynthesisOutput;
  approved_at: string | null;
};

export type CriticFinding = {
  problem: string;
  why_relevant: string;
  recommended_change: string;
  priority: "KRITISCH" | "WICHTIG" | "OPTIONAL";
};

export type CriticOut = { status: "OK" | "ANMERKUNGEN"; findings: CriticFinding[] };

export type EvaluatorRequiredChange = { problem: string; required_correction: string };

export type EvaluationOut = {
  attempt: number;
  status: "PASS" | "REVISION_REQUIRED";
  reasoning: string | null;
  required_changes: EvaluatorRequiredChange[];
  created_at: string;
};

export type FinalExistingSolution = { source_id: string; how_used: string };

export type FinalPlan = {
  goal_and_starting_point: string;
  recommended_overall_solution: string;
  structure_and_components: string;
  feature_scope: string;
  existing_open_source_solutions_used: FinalExistingSolution[];
  core_technical_decisions: string;
  implementation_plan_phases: string;
  risks_and_mitigations: string;
  open_decisions: string[];
  acceptance_criteria: string[];
  presentation_structure: string;
};

export type FinalOut = {
  plan: FinalPlan;
  presentation: string;
  open_decisions: string[];
  created_at: string;
};

export type WorkflowState =
  | "DRAFT" | "UNDERSTANDING" | "WAITING_FOR_USER_CONFIRMATION"
  | "WAITING_FOR_USER_CLARIFICATION" | "ESCALATION_REQUIRED" | "RESEARCHING"
  | "WAITING_FOR_RESEARCH_APPROVAL" | "GENERATING_SOLUTIONS" | "SYNTHESIZING"
  | "WAITING_FOR_SYNTHESIS_APPROVAL" | "REVIEWING" | "EVALUATING"
  | "REVISION_REQUIRED" | "REVISING" | "FINALIZING" | "COMPLETED";

export type ProjectDetail = {
  id: string;
  title: string;
  workflow_state: WorkflowState;
  escalation_reason: "CLARIFICATION_LIMIT" | "REVISION_LIMIT" | null;
  created_at: string;
  updated_at: string;
  clarification_round_count: number;
  research_gate_enabled: boolean;
  total_model_calls: number;
  total_estimated_cost_usd: number;
  intake: IntakeOut;
  understanding: UnderstandingOut | null;
  research: ResearchOut | null;
  architect: SolutionAgentOut | null;
  challenger: SolutionAgentOut | null;
  synthesis: SynthesisOut | null;
  critic: CriticOut | null;
  evaluations: EvaluationOut[];
  final: FinalOut | null;
  last_run_status: "RUNNING" | "DONE" | "FAILED" | null;
  hint: string | null;
};

export type ProjectSummary = {
  id: string;
  title: string;
  workflow_state: WorkflowState;
  updated_at: string;
};

export type CostOut = {
  total_model_calls: number;
  total_estimated_cost_usd: number;
  by_role: Record<string, { calls: number; estimated_cost_usd: number }>;
};

export type IntakeFields = {
  goal: string;
  problem: string;
  users_structure: string;
  interface_output: string;
  constraints: string;
  core_features: string;
};

export class ApiError extends Error {
  code: string;
  status: number;
  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
  });
  if (!res.ok) {
    let code = "UNKNOWN";
    let message = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      if (body?.error) {
        code = body.error.code ?? code;
        message = body.error.message ?? message;
      } else if (body?.detail) {
        // FastAPI-Validierungsfehler (422 ohne unseren error-Envelope)
        message = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
      }
    } catch {
      /* keine JSON-Fehlerantwort - message bleibt beim HTTP-Status */
    }
    throw new ApiError(res.status, code, message);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

const j = (body: unknown): RequestInit => ({ method: "POST", body: JSON.stringify(body) });

export const api = {
  listProjects: () => request<ProjectSummary[]>("/api/projects"),
  createProject: (title: string, intake: IntakeFields, researchGateEnabled: boolean) =>
    request<ProjectDetail>("/api/projects", j({ title, intake, research_gate_enabled: researchGateEnabled })),
  getProject: (id: string) => request<ProjectDetail>(`/api/projects/${encodeURIComponent(id)}`),
  patchIntake: (id: string, fields: Partial<IntakeFields>) =>
    request<ProjectDetail>(`/api/projects/${encodeURIComponent(id)}/intake`, { method: "PATCH", body: JSON.stringify(fields) }),
  submit: (id: string) => request<ProjectDetail>(`/api/projects/${encodeURIComponent(id)}/submit`, j({})),
  confirmUnderstanding: (id: string) => request<ProjectDetail>(`/api/projects/${encodeURIComponent(id)}/understanding/confirm`, j({})),
  correctUnderstanding: (id: string) => request<ProjectDetail>(`/api/projects/${encodeURIComponent(id)}/understanding/correct`, j({})),
  answerClarification: (id: string, answers: string) =>
    request<ProjectDetail>(`/api/projects/${encodeURIComponent(id)}/clarification`, j({ answers })),
  resolveEscalation: (id: string, action: string) =>
    request<ProjectDetail>(`/api/projects/${encodeURIComponent(id)}/escalation/resolve`, j({ action })),
  approveResearch: (id: string) => request<ProjectDetail>(`/api/projects/${encodeURIComponent(id)}/research/approve`, j({})),
  rerunResearch: (id: string, comment: string | null) =>
    request<ProjectDetail>(`/api/projects/${encodeURIComponent(id)}/research/rerun`, j({ comment })),
  approveSynthesis: (id: string) => request<ProjectDetail>(`/api/projects/${encodeURIComponent(id)}/synthesis/approve`, j({})),
  changeRequestSynthesis: (id: string, comment: string) =>
    request<ProjectDetail>(`/api/projects/${encodeURIComponent(id)}/synthesis/change-request`, j({ comment })),
  retry: (id: string) => request<ProjectDetail>(`/api/projects/${encodeURIComponent(id)}/retry`, j({})),
  getCost: (id: string) => request<CostOut>(`/api/projects/${encodeURIComponent(id)}/cost`),
  exportMarkdownUrl: (id: string) => `/api/projects/${encodeURIComponent(id)}/export?format=markdown`,
  eventsUrl: (id: string) => `/api/projects/${encodeURIComponent(id)}/events`,
};

/** Rollenname → deutsches Label (für Live-Status/Kostenanzeige). */
export const ROLE_LABELS: Record<string, string> = {
  understanding: "Verständnis",
  research: "Recherche",
  architect: "Architect",
  challenger: "Challenger",
  synthesizer: "Synthese",
  critic: "Prüfung (Critic)",
  evaluator: "Prüfung (Evaluator)",
  revision: "Revision",
  final_builder: "Abnahme (Final Builder)",
};
