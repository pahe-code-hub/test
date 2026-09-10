import { useEffect, useRef, useState } from "react";
import { api, ROLE_LABELS } from "./api";

export type LiveActivity = { role: string; attempt: number; status: "RUNNING" | "DONE" | "FAILED" } | null;

/**
 * API_CONTRACT.md § Fortschritt (SSE). Statt Teilzustände client-seitig
 * nachzubilden, wird bei JEDEM Event (state_changed, agent_run_*,
 * cost_updated) einfach `onRefetch()` aufgerufen - das Backend bleibt die
 * einzige Quelle der Wahrheit, das Frontend muss nur wissen, WANN es neu
 * laden soll, nicht WAS sich geändert hat (Abschnitt 26: kein Polling
 * nötig, aber auch kein fragiler Client-State-Merge). `agent_run_*`
 * werden zusätzlich als transiente "läuft gerade"-Anzeige gehalten.
 */
export function useProjectEvents(projectId: string | null, onRefetch: () => void) {
  const [connected, setConnected] = useState(false);
  const [activity, setActivity] = useState<LiveActivity>(null);
  const onRefetchRef = useRef(onRefetch);
  onRefetchRef.current = onRefetch;

  useEffect(() => {
    if (!projectId) return;
    setConnected(false);
    setActivity(null);
    const source = new EventSource(api.eventsUrl(projectId));

    source.onopen = () => setConnected(true);
    source.onerror = () => setConnected(false);

    const refetch = () => onRefetchRef.current();
    source.addEventListener("state_changed", refetch);
    source.addEventListener("cost_updated", refetch);
    source.addEventListener("agent_run_started", (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      setActivity({ role: data.role, attempt: data.attempt, status: "RUNNING" });
    });
    source.addEventListener("agent_run_completed", (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      setActivity({ role: data.role, attempt: data.attempt, status: "DONE" });
      refetch();
    });
    source.addEventListener("agent_run_failed", (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      setActivity({ role: data.role, attempt: data.attempt, status: "FAILED" });
      refetch();
    });

    return () => source.close();
  }, [projectId]);

  const activityLabel = activity ? ROLE_LABELS[activity.role] ?? activity.role : null;
  return { connected, activity, activityLabel };
}
