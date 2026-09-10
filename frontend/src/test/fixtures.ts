import type { ProjectDetail } from "../api";

/** Minimale, aber vollständige ProjectDetail-Fixture (jedes Feld typkorrekt
 * besetzt) - Tests überschreiben gezielt einzelne Felder statt jedes Mal
 * das komplette Objekt neu aufzubauen. */
export function makeProject(overrides: Partial<ProjectDetail> = {}): ProjectDetail {
  return {
    id: "p1",
    title: "Testprojekt",
    workflow_state: "DRAFT",
    escalation_reason: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    clarification_round_count: 0,
    research_gate_enabled: false,
    total_model_calls: 0,
    total_estimated_cost_usd: 0,
    intake: {
      goal: "", problem: "", users_structure: "", interface_output: "",
      constraints: "", core_features: "", updated_at: "2026-01-01T00:00:00Z",
    },
    understanding: null,
    research: null,
    architect: null,
    challenger: null,
    synthesis: null,
    critic: null,
    evaluations: [],
    final: null,
    last_run_status: null,
    hint: null,
    ...overrides,
  };
}
