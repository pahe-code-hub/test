import { useState } from "react";
import { api, ApiError, type ProjectDetail } from "./api";
import { Markdown } from "./Markdown";

/** Abschnitt 25: "Synthese: Zielkonzept prominent anzeigen, Buttons
 * ZIELKONZEPT FREIGEBEN / ÄNDERUNGSWUNSCH". `hint` erscheint laut
 * API_CONTRACT.md NUR in der change-request-Antwort (ab Runde 3), wird
 * hier also aus dem zuletzt empfangenen ProjectDetail übernommen, nicht
 * erneut per GET geholt. */
export function SynthesisPanel({ project, onChanged }: { project: ProjectDetail; onChanged: (p: ProjectDetail) => void }) {
  const synthesis = project.synthesis;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [comment, setComment] = useState("");

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

  if (!synthesis) return <section><h2>Synthese</h2><p className="muted">Synthese läuft…</p></section>;
  const o = synthesis.output;
  const showGate = project.workflow_state === "WAITING_FOR_SYNTHESIS_APPROVAL";

  return (
    <section>
      <h2>Synthese (Zielkonzept, Version {synthesis.version})</h2>
      <strong>Ansatz</strong><Markdown>{o.approach}</Markdown>
      <strong>Übernommene Kernelemente</strong>
      <ul>{o.adopted_core_elements.map((x) => <li key={x}><Markdown>{x}</Markdown></li>)}</ul>
      <strong>Verworfene/geänderte Ansätze</strong>
      <ul>{o.discarded_or_changed_approaches.map((x) => <li key={x}><Markdown>{x}</Markdown></li>)}</ul>
      <strong>Struktur</strong><Markdown>{o.structure}</Markdown>
      {o.existing_solutions_open_source.length > 0 && (
        <>
          <strong>Verwendete bestehende/Open-Source-Lösungen</strong>
          <ul>{o.existing_solutions_open_source.map((s) => (
            <li key={s.source_id}><Markdown>{s.note}</Markdown></li>
          ))}</ul>
        </>
      )}
      <strong>Kernentscheidungen</strong>
      <ul>{o.key_decisions.map((x) => <li key={x}><Markdown>{x}</Markdown></li>)}</ul>
      <strong>Risiken/offene Punkte</strong>
      <ul>{o.risks_open_points.map((x) => <li key={x}><Markdown>{x}</Markdown></li>)}</ul>
      <strong>Fazit</strong><Markdown>{o.conclusion}</Markdown>

      {showGate && (
        <div className="gate">
          {project.hint && <p className="callout">{project.hint}</p>}
          {error && <p role="alert" className="error">{error}</p>}
          <button type="button" disabled={busy} onClick={run(() => api.approveSynthesis(project.id))}>
            ZIELKONZEPT FREIGEBEN
          </button>
          <label>
            <span>Änderungswunsch</span>
            <textarea rows={3} value={comment} onChange={(e) => setComment(e.target.value)} />
          </label>
          <button type="button" className="secondary" disabled={busy || !comment.trim()} onClick={run(() => api.changeRequestSynthesis(project.id, comment))}>
            ÄNDERUNGSWUNSCH
          </button>
        </div>
      )}
    </section>
  );
}
