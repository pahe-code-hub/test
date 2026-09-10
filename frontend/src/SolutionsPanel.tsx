import type { ProjectDetail, SolutionAgentOut, SolutionOutput } from "./api";
import { Markdown } from "./Markdown";

/** Abschnitt 25: "Architect/Challenger: nebeneinander anzeigen, kein
 * Pflicht-Human-Gate" - reiner Anzeige-Baustein, keine Aktionen. */
function SolutionCard({ title, agent }: { title: string; agent: SolutionAgentOut | null }) {
  if (!agent || agent.run_status === "PENDING") {
    return <article><h3>{title}</h3><p className="muted">Wartet…</p></article>;
  }
  if (agent.run_status === "RUNNING") {
    return <article><h3>{title}</h3><p className="muted">Läuft…</p></article>;
  }
  if (agent.run_status === "FAILED" || !agent.output) {
    return <article><h3>{title}</h3><p className="error">Fehlgeschlagen.</p></article>;
  }
  const o: SolutionOutput = agent.output;
  return (
    <article>
      <h3>{title}</h3>
      <strong>Ansatz</strong><Markdown>{o.approach}</Markdown>
      <strong>Struktur</strong><Markdown>{o.structure}</Markdown>
      <strong>Komponenten</strong>
      <ul>{o.components.map((c) => <li key={c}>{c}</li>)}</ul>
      <strong>Zusammenspiel</strong><Markdown>{o.interactions}</Markdown>
      <strong>Technologien</strong>
      <ul>{o.technologies.map((t) => <li key={t}>{t}</li>)}</ul>
      <strong>Risiken</strong>
      <ul>{o.risks.map((r) => <li key={r}><Markdown>{r}</Markdown></li>)}</ul>
      <strong>Umsetzungsansatz</strong><Markdown>{o.implementation_approach}</Markdown>
      <strong>Offene Punkte</strong>
      <ul>{o.open_points.map((p) => <li key={p}><Markdown>{p}</Markdown></li>)}</ul>
    </article>
  );
}

export function SolutionsPanel({ project }: { project: ProjectDetail }) {
  return (
    <section>
      <h2>Lösungsentwürfe</h2>
      <section className="cards two-col">
        <SolutionCard title="Architect" agent={project.architect} />
        <SolutionCard title="Challenger" agent={project.challenger} />
      </section>
    </section>
  );
}
