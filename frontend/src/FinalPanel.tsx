import { api, type FinalPlan, type ProjectDetail } from "./api";
import { Markdown } from "./Markdown";

const SECTIONS: { key: keyof FinalPlan; label: string }[] = [
  { key: "goal_and_starting_point", label: "Ziel und Ausgangslage" },
  { key: "recommended_overall_solution", label: "Empfohlene Gesamtlösung" },
  { key: "structure_and_components", label: "Aufbau und Komponenten" },
  { key: "feature_scope", label: "Funktionsumfang" },
  { key: "core_technical_decisions", label: "Technische Grundentscheidungen" },
  { key: "implementation_plan_phases", label: "Umsetzungsplan in Phasen" },
  { key: "risks_and_mitigations", label: "Risiken und Gegenmaßnahmen" },
];

/** Abschnitt 25: "Final: finalen Plan anzeigen, Exportoptionen später
 * (Markdown, PDF, DOCX, JSON)" - PDF/DOCX/JSON sind laut ADR-012 bewusst
 * nicht umgesetzt (Phase 8, außerhalb V1-Scope), Markdown-Export (Phase
 * 6) ist der einzige Button hier. */
export function FinalPanel({ project }: { project: ProjectDetail }) {
  const final = project.final;
  if (!final) return <section><h2>Ergebnis</h2><p className="muted">Wird finalisiert…</p></section>;
  const plan = final.plan;

  return (
    <section>
      <h2>Ergebnis — Finaler Projektplan</h2>
      <a className="button" href={api.exportMarkdownUrl(project.id)}>Als Markdown exportieren</a>

      {SECTIONS.map(({ key, label }) => (
        <div key={key}>
          <h3>{label}</h3>
          <Markdown>{plan[key] as string}</Markdown>
        </div>
      ))}

      {plan.existing_open_source_solutions_used.length > 0 && (
        <>
          <h3>Verwendete bestehende/Open-Source-Lösungen</h3>
          <ul>{plan.existing_open_source_solutions_used.map((s) => (
            <li key={s.source_id}><Markdown>{s.how_used}</Markdown></li>
          ))}</ul>
        </>
      )}

      <h3>Offene Entscheidungen</h3>
      {final.open_decisions.length === 0
        ? <p className="muted">Keine.</p>
        : <ul>{final.open_decisions.map((d, i) => <li key={i}><Markdown>{d}</Markdown></li>)}</ul>}

      <h3>Abnahmekriterien</h3>
      <ul>{plan.acceptance_criteria.map((c, i) => <li key={i}><Markdown>{c}</Markdown></li>)}</ul>

      <h3>Präsentationsstruktur</h3>
      <Markdown>{plan.presentation_structure}</Markdown>
    </section>
  );
}
