import { describe, expect, it, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useProjectEvents } from "../useProjectEvents";

// Der globale StubEventSource aus test/setup.ts erlaubt, konkrete
// SSE-Frames manuell in den Hook zu spielen und zu prüfen, dass
// state_changed/agent_run_* die dokumentierten Effekte auslösen
// (API_CONTRACT.md § Fortschritt, Event-Tabelle).
type StubInstance = { listeners: Record<string, ((e: MessageEvent) => void)[]>; onopen: (() => void) | null };

function lastInstance(): StubInstance {
  const cls = globalThis.EventSource as unknown as { instances: StubInstance[] };
  return cls.instances[cls.instances.length - 1];
}

function emit(instance: StubInstance, type: string, data: unknown) {
  for (const cb of instance.listeners[type] ?? []) cb({ data: JSON.stringify(data) } as MessageEvent);
}

describe("useProjectEvents", () => {
  it("ruft onRefetch bei state_changed auf", () => {
    const onRefetch = vi.fn();
    renderHook(() => useProjectEvents("p1", onRefetch));
    act(() => emit(lastInstance(), "state_changed", { workflow_state: "UNDERSTANDING", escalation_reason: null }));
    expect(onRefetch).toHaveBeenCalledTimes(1);
  });

  it("ruft onRefetch bei cost_updated auf", () => {
    const onRefetch = vi.fn();
    renderHook(() => useProjectEvents("p1", onRefetch));
    act(() => emit(lastInstance(), "cost_updated", { total_model_calls: 2, total_estimated_cost_usd: 0.1 }));
    expect(onRefetch).toHaveBeenCalledTimes(1);
  });

  it("haelt agent_run_started als transiente activity ohne sofortigen Refetch", () => {
    const onRefetch = vi.fn();
    const { result } = renderHook(() => useProjectEvents("p1", onRefetch));
    act(() => emit(lastInstance(), "agent_run_started", { role: "research", attempt: 1 }));
    expect(result.current.activity).toEqual({ role: "research", attempt: 1, status: "RUNNING" });
    expect(onRefetch).not.toHaveBeenCalled();
  });

  it("agent_run_completed aktualisiert activity UND löst Refetch aus", () => {
    const onRefetch = vi.fn();
    const { result } = renderHook(() => useProjectEvents("p1", onRefetch));
    act(() => emit(lastInstance(), "agent_run_completed", { role: "research", attempt: 1 }));
    expect(result.current.activity?.status).toBe("DONE");
    expect(onRefetch).toHaveBeenCalledTimes(1);
  });

  it("meldet 'connected' erst nach onopen", () => {
    const { result } = renderHook(() => useProjectEvents("p1", () => {}));
    expect(result.current.connected).toBe(false);
    act(() => lastInstance().onopen?.());
    expect(result.current.connected).toBe(true);
  });

  it("verbindet sich nicht ohne projectId", () => {
    const before = (globalThis.EventSource as unknown as { instances: unknown[] }).instances.length;
    renderHook(() => useProjectEvents(null, () => {}));
    const after = (globalThis.EventSource as unknown as { instances: unknown[] }).instances.length;
    expect(after).toBe(before);
  });
});
