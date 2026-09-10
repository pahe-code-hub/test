import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { ProjectListView } from "../ProjectListView";
import { api } from "../api";
import { makeProject } from "./fixtures";

describe("ProjectListView (API_CONTRACT.md § Projektübersicht, Abschnitt 27)", () => {
  beforeEach(() => { vi.restoreAllMocks(); });

  it("zeigt eine leere Liste mit Hinweistext statt einer leeren Tabelle", async () => {
    vi.spyOn(api, "listProjects").mockResolvedValue([]);
    render(<ProjectListView onSelect={() => {}} />);
    expect(await screen.findByText(/Noch keine Projekte/)).toBeInTheDocument();
  });

  it("listet bestehende Projekte mit Titel und Status", async () => {
    vi.spyOn(api, "listProjects").mockResolvedValue([
      { id: "p1", title: "Notiz-App", workflow_state: "COMPLETED", updated_at: "2026-01-01T00:00:00Z" },
    ]);
    render(<ProjectListView onSelect={() => {}} />);
    expect(await screen.findByText("Notiz-App")).toBeInTheDocument();
    expect(screen.getByText("Abgeschlossen")).toBeInTheDocument();
  });

  it("ein Klick auf eine Zeile wählt das Projekt aus", async () => {
    vi.spyOn(api, "listProjects").mockResolvedValue([
      { id: "p1", title: "Notiz-App", workflow_state: "DRAFT", updated_at: "2026-01-01T00:00:00Z" },
    ]);
    const onSelect = vi.fn();
    render(<ProjectListView onSelect={onSelect} />);
    fireEvent.click(await screen.findByText("Notiz-App"));
    expect(onSelect).toHaveBeenCalledWith("p1");
  });

  it("'Neues Projekt' legt ein leeres Draft-Projekt an und wählt es aus", async () => {
    vi.spyOn(api, "listProjects").mockResolvedValue([]);
    const created = makeProject({ id: "new-id" });
    vi.spyOn(api, "createProject").mockResolvedValue(created);
    const onSelect = vi.fn();
    render(<ProjectListView onSelect={onSelect} />);
    fireEvent.click(await screen.findByRole("button", { name: "Neues Projekt" }));
    await waitFor(() => expect(onSelect).toHaveBeenCalledWith("new-id"));
  });
});
