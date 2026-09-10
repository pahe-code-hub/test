import type { ProjectDetail } from "./api";
import { Markdown } from "./Markdown";

const PRIORITY_LABEL: Record<string, string> = { KRITISCH: "Kritisch", WICHTIG: "Wichtig", OPTIONAL: "Optional" };

/** Prüfung (Critic → Evaluator → ggf. Revision) läuft laut
 * WORKFLOW_STATES.md vollständig automatisch - kein Nutzer-Gate, reine
 * Anzeige des Fortschritts. */
export function QualityPanel({ project }: { project: ProjectDetail }) {
  const running = ["REVIEWING", "EVALUATING", "REVISION_REQUIRED", "REVISING"].includes(project.workflow_state);
  return (
    <section>
      <h2>Prüfung</h2>
      {running && <p className="muted">Läuft automatisch — keine Nutzeraktion nötig.</p>}

      {project.critic && (
        <>
          <h3>Critic <small>{project.critic.status}</small></h3>
          {project.critic.findings.length === 0 && <p className="muted">Keine Anmerkungen.</p>}
          <ul className="findings">
            {project.critic.findings.map((f, i) => (
              <li key={i} className={`priority-${f.priority.toLowerCase()}`}>
                <strong>{PRIORITY_LABEL[f.priority] ?? f.priority}: {f.problem}</strong>
                <p><em>Relevanz:</em> <Markdown>{f.why_relevant}</Markdown></p>
                <p><em>Empfehlung:</em> <Markdown>{f.recommended_change}</Markdown></p>
              </li>
            ))}
          </ul>
        </>
      )}

      {project.evaluations.length > 0 && (
        <>
          <h3>Evaluator-Durchläufe</h3>
          <ol className="findings">
            {project.evaluations.map((e) => (
              <li key={e.attempt}>
                <strong>Durchlauf {e.attempt + 1}: {e.status === "PASS" ? "PASS" : "Revision erforderlich"}</strong>
                {e.reasoning && <p><Markdown>{e.reasoning}</Markdown></p>}
                {e.required_changes.length > 0 && (
                  <ul>{e.required_changes.map((c, i) => (
                    <li key={i}><strong>{c.problem}</strong> — <Markdown>{c.required_correction}</Markdown></li>
                  ))}</ul>
                )}
              </li>
            ))}
          </ol>
        </>
      )}
    </section>
  );
}
