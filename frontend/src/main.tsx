import React from "react";
import { createRoot } from "react-dom/client";
import { ResearchPanel } from "./ResearchPanel";
import "./style.css";

const projectId = new URLSearchParams(location.search).get("project");
createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    {projectId ? <ResearchPanel projectId={projectId} /> : <p>Projekt-ID als <code>?project=…</code> angeben.</p>}
  </React.StrictMode>,
);
