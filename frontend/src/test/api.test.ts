import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { api, ApiError } from "../api";

function mockFetch(status: number, body: unknown) {
  return vi.fn(async () => ({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  })) as unknown as typeof fetch;
}

describe("api error handling (API_CONTRACT.md § Fehlerformat)", () => {
  beforeEach(() => { vi.restoreAllMocks(); });
  afterEach(() => { vi.unstubAllGlobals(); });

  it("extrahiert code/message aus dem {error:{code,message}}-Envelope", async () => {
    vi.stubGlobal("fetch", mockFetch(409, { error: { code: "INVALID_STATE", message: "Aktion nicht zulässig" } }));
    await expect(api.getProject("p1")).rejects.toMatchObject(
      new ApiError(409, "INVALID_STATE", "Aktion nicht zulässig"),
    );
  });

  it("faellt bei FastAPI-Validierungsfehlern (422 ohne error-Envelope) auf detail zurueck", async () => {
    vi.stubGlobal("fetch", mockFetch(422, { detail: "ungültige Eingabe" }));
    await expect(api.getProject("p1")).rejects.toThrow("ungültige Eingabe");
  });

  it("liefert einen brauchbaren Fallback ohne jede JSON-Antwort", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: false, status: 500, json: async () => { throw new Error("no body"); } })) as unknown as typeof fetch);
    await expect(api.getProject("p1")).rejects.toThrow("HTTP 500");
  });

  it("löst bei Erfolg mit dem geparsten JSON auf", async () => {
    vi.stubGlobal("fetch", mockFetch(200, { id: "p1", title: "x" }));
    await expect(api.getProject("p1")).resolves.toMatchObject({ id: "p1" });
  });
});

describe("api request construction", () => {
  it("submit sendet POST ohne Body-Feld an den richtigen Pfad", async () => {
    const fetchMock = mockFetch(200, { id: "p1" });
    vi.stubGlobal("fetch", fetchMock);
    await api.submit("p1");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/projects/p1/submit",
      expect.objectContaining({ method: "POST", body: "{}" }),
    );
    vi.unstubAllGlobals();
  });

  it("exportMarkdownUrl zeigt auf den Markdown-Export-Endpunkt (AT-6.4)", () => {
    expect(api.exportMarkdownUrl("p1")).toBe("/api/projects/p1/export?format=markdown");
  });
});
