import { useState } from "react";
import { api, ApiError, type ProjectDetail } from "./api";

/** ESCALATION_REQUIRED(REVISION_LIMIT): nach MAX_INTERNAL_REVISIONS
 * erfolglosen Revisionen (AT-5.4) entscheidet der Nutzer zwischen
 * einem weiteren Revisionsversuch und der Abnahme trotz offener Punkte
 * (API_CONTRACT.md § Eskalation). Das CLARIFICATION_LIMIT-Gegenstück
 * liegt in UnderstandingGate, da es inhaltlich zum Verständnis-Schritt
 * gehört. */
export function EscalationPanel({ project, onChanged }: { project: ProjectDetail; onChanged: (p: ProjectDetail) => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const run = (action: string) => async () => {
    setBusy(true);
    setError("");
    try {
      onChanged(await api.resolveEscalation(project.id, action));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const lastEval = project.evaluations[project.evaluations.length - 1];

  return (
    <section>
      <h2>Abnahme — Grundsatzentscheidung nötig</h2>
      <p>
        Nach {project.evaluations.length} Prüfungsdurchläufen bestehen weiterhin geforderte Korrekturen.
        Wie soll fortgefahren werden?
      </p>
      {lastEval && lastEval.required_changes.length > 0 && (
        <ul>{lastEval.required_changes.map((c, i) => (
          <li key={i}><strong>{c.problem}</strong> — {c.required_correction}</li>
        ))}</ul>
      )}
      {error && <p role="alert" className="error">{error}</p>}
      <div className="actions">
        <button type="button" disabled={busy} onClick={run("RETRY_REVISION")}>
          Weiterer Revisionsversuch
        </button>
        <button type="button" className="secondary" disabled={busy} onClick={run("ACCEPT_WITH_OPEN_POINTS")}>
          Trotz offener Punkte abnehmen
        </button>
      </div>
    </section>
  );
}
