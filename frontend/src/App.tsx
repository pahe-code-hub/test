import { useCallback, useEffect, useState } from "react";
import { ProjectListView } from "./ProjectListView";
import { ProjectDetailView } from "./ProjectDetailView";

/** Ganze App ist eine Seite (ADR-004: ein Prozess, ein Port, kein
 * separater Router nötig) - "Navigation" ist ein einziger Query-Parameter
 * `?project=<id>`, per history.pushState gepflegt, damit Browser-Zurück
 * funktioniert, ohne react-router als Abhängigkeit zu brauchen. */
function readProjectId(): string | null {
  return new URLSearchParams(location.search).get("project");
}

export function App() {
  const [projectId, setProjectId] = useState<string | null>(readProjectId());

  useEffect(() => {
    const onPop = () => setProjectId(readProjectId());
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  const select = useCallback((id: string) => {
    history.pushState({}, "", `?project=${encodeURIComponent(id)}`);
    setProjectId(id);
  }, []);

  const back = useCallback(() => {
    history.pushState({}, "", location.pathname);
    setProjectId(null);
  }, []);

  return projectId
    ? <ProjectDetailView projectId={projectId} onBack={back} />
    : <ProjectListView onSelect={select} />;
}
