import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { IntakeForm } from "../IntakeForm";
import { api } from "../api";
import { makeProject } from "./fixtures";

describe("IntakeForm (Abschnitt 3: sechs Pflichtfelder, API_CONTRACT.md § submit)", () => {
  beforeEach(() => { vi.restoreAllMocks(); });

  it("deaktiviert 'IDEE PRÜFEN', solange nicht alle sechs Felder ausgefüllt sind", () => {
    render(<IntakeForm project={makeProject()} onChanged={() => {}} />);
    expect(screen.getByRole("button", { name: "IDEE PRÜFEN" })).toBeDisabled();
  });

  it("aktiviert 'IDEE PRÜFEN' erst, wenn alle sechs Felder befüllt sind", () => {
    const filled = makeProject({
      intake: {
        goal: "a", problem: "b", users_structure: "c", interface_output: "d",
        constraints: "e", core_features: "f", updated_at: "2026-01-01T00:00:00Z",
      },
    });
    render(<IntakeForm project={filled} onChanged={() => {}} />);
    expect(screen.getByRole("button", { name: "IDEE PRÜFEN" })).toBeEnabled();
  });

  it("speichert ein geändertes Feld per PATCH beim Verlassen (onBlur), nicht bei jedem Tastendruck", async () => {
    const patchSpy = vi.spyOn(api, "patchIntake").mockResolvedValue(makeProject());
    render(<IntakeForm project={makeProject()} onChanged={() => {}} />);
    const goalField = screen.getByLabelText("Ziel");
    fireEvent.change(goalField, { target: { value: "Neues Ziel" } });
    expect(patchSpy).not.toHaveBeenCalled(); // reine Eingabe löst noch kein PATCH aus
    fireEvent.blur(goalField);
    await waitFor(() => expect(patchSpy).toHaveBeenCalledWith("p1", { goal: "Neues Ziel" }));
  });

  it("löst 'IDEE PRÜFEN' aus und reicht das Ergebnis an onChanged weiter", async () => {
    const filled = makeProject({
      intake: {
        goal: "a", problem: "b", users_structure: "c", interface_output: "d",
        constraints: "e", core_features: "f", updated_at: "2026-01-01T00:00:00Z",
      },
    });
    const submitted = makeProject({ workflow_state: "UNDERSTANDING" });
    vi.spyOn(api, "submit").mockResolvedValue(submitted);
    const onChanged = vi.fn();
    render(<IntakeForm project={filled} onChanged={onChanged} />);
    fireEvent.click(screen.getByRole("button", { name: "IDEE PRÜFEN" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith(submitted));
  });

  it("zeigt eine Fehlermeldung bei INCOMPLETE_INTAKE statt sie zu verschlucken", async () => {
    const filled = makeProject({
      intake: {
        goal: "a", problem: "b", users_structure: "c", interface_output: "d",
        constraints: "e", core_features: "f", updated_at: "2026-01-01T00:00:00Z",
      },
    });
    const { ApiError } = await import("../api");
    vi.spyOn(api, "submit").mockRejectedValue(new ApiError(422, "INCOMPLETE_INTAKE", "Pflichtfelder fehlen"));
    render(<IntakeForm project={filled} onChanged={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "IDEE PRÜFEN" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Pflichtfelder fehlen");
  });
});
