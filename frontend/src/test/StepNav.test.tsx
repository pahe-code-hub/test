import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { StepNav } from "../StepNav";
import { makeProject } from "./fixtures";

function activeLabel(container: HTMLElement) {
  return container.querySelector("li.active")?.textContent?.replace("●", "").trim();
}

describe("StepNav (Abschnitt 2: Idee → Verständnis → … → Ergebnis)", () => {
  it("markiert 'Idee' bei DRAFT als aktiv", () => {
    const { container } = render(<StepNav project={makeProject({ workflow_state: "DRAFT" })} />);
    expect(activeLabel(container)).toBe("Idee");
  });

  it("markiert 'Synthese' bei WAITING_FOR_SYNTHESIS_APPROVAL als aktiv, vorherige Schritte als erledigt", () => {
    const { container } = render(<StepNav project={makeProject({ workflow_state: "WAITING_FOR_SYNTHESIS_APPROVAL" })} />);
    expect(activeLabel(container)).toBe("Synthese");
    expect(container.querySelectorAll("li.done")).toHaveLength(4); // Idee, Verständnis, Recherche, Lösungsentwürfe
  });

  it("markiert 'Ergebnis' bei COMPLETED als aktiv und alle vorigen als erledigt", () => {
    const { container } = render(<StepNav project={makeProject({ workflow_state: "COMPLETED" })} />);
    expect(activeLabel(container)).toBe("Ergebnis");
    expect(container.querySelectorAll("li.done")).toHaveLength(7);
  });

  it("ESCALATION_REQUIRED verzweigt nach escalation_reason: CLARIFICATION_LIMIT -> Verständnis", () => {
    const { container } = render(<StepNav project={makeProject({ workflow_state: "ESCALATION_REQUIRED", escalation_reason: "CLARIFICATION_LIMIT" })} />);
    expect(activeLabel(container)).toBe("Verständnis");
  });

  it("ESCALATION_REQUIRED verzweigt nach escalation_reason: REVISION_LIMIT -> Abnahme", () => {
    const { container } = render(<StepNav project={makeProject({ workflow_state: "ESCALATION_REQUIRED", escalation_reason: "REVISION_LIMIT" })} />);
    expect(activeLabel(container)).toBe("Abnahme");
  });

  it("rendert alle 8 Schritte aus Abschnitt 2 in der richtigen Reihenfolge", () => {
    render(<StepNav project={makeProject()} />);
    const labels = screen.getAllByRole("listitem").map((li) => li.textContent?.replace(/^[●○✓]/, ""));
    expect(labels).toEqual(["Idee", "Verständnis", "Recherche", "Lösungsentwürfe", "Synthese", "Prüfung", "Abnahme", "Ergebnis"]);
  });
});
