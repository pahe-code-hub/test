import { useState } from "react";
import { api, ApiError, type ProjectDetail } from "./api";
import { Markdown } from "./Markdown";

type Props = { project: ProjectDetail; onChanged: (p: ProjectDetail) => void };

/** Abschnitt 7: WAITING_FOR_USER_CONFIRMATION (RICHTIG VERSTANDEN/
 * KORRIGIEREN), WAITING_FOR_USER_CLARIFICATION (Rückfragen, max. 3
 * Fragen), sowie ESCALATION_REQUIRED(CLARIFICATION_LIMIT) - nach
 * MAX_CLARIFICATION_ROUNDS Runden einziger gültiger Ausgang
 * REWORK_INTAKE (AT-1.4). */
export function UnderstandingGate({ project, onChanged }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [answers, setAnswers] = useState("");

  const run = (fn: () => Promise<ProjectDetail>) => async () => {
    setBusy(true);
    setError("");
    try {
      onChanged(await fn());
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  if (project.workflow_state === "ESCALATION_REQUIRED" && project.escalation_reason === "CLARIFICATION_LIMIT") {
    return (
      <section>
        <h2>Verständnis — Grundsatzentscheidung nötig</h2>
        <p>
          Nach {project.clarification_round_count} Rückfragerunden konnte die Idee nicht ausreichend geklärt werden.
          Die Idee muss grundlegend überarbeitet werden.
        </p>
        {error && <p role="alert" className="error">{error}</p>}
        <button type="button" disabled={busy} onClick={run(() => api.resolveEscalation(project.id, "REWORK_INTAKE"))}>
          Idee überarbeiten
        </button>
      </section>
    );
  }

  if (project.workflow_state === "WAITING_FOR_USER_CLARIFICATION") {
    const u = project.understanding;
    return (
      <section>
        <h2>Rückfragen ({project.clarification_round_count} von 3 Runden)</h2>
        {u?.contradiction_note && (
          <p className="callout"><strong>Widerspruch erkannt:</strong> <Markdown>{u.contradiction_note}</Markdown></p>
        )}
        <ul>{(u?.questions ?? []).map((q, i) => <li key={i}><Markdown>{q}</Markdown></li>)}</ul>
        <label>
          <span>Antworten</span>
          <textarea rows={4} value={answers} onChange={(e) => setAnswers(e.target.value)} />
        </label>
        {error && <p role="alert" className="error">{error}</p>}
        <button
          type="button"
          disabled={busy || !answers.trim()}
          onClick={run(() => api.answerClarification(project.id, answers))}
        >
          Antworten senden
        </button>
      </section>
    );
  }

  // WAITING_FOR_USER_CONFIRMATION
  return (
    <section>
      <h2>Verständnis</h2>
      <Markdown>{project.understanding?.summary ?? ""}</Markdown>
      {error && <p role="alert" className="error">{error}</p>}
      <div className="actions">
        <button type="button" disabled={busy} onClick={run(() => api.confirmUnderstanding(project.id))}>
          RICHTIG VERSTANDEN
        </button>
        <button type="button" className="secondary" disabled={busy} onClick={run(() => api.correctUnderstanding(project.id))}>
          KORRIGIEREN
        </button>
      </div>
    </section>
  );
}
