import { useState } from "react";
import { api, ApiError, type ProjectDetail } from "./api";
import { Markdown, safeUrl } from "./Markdown";

/** Integriert die ursprüngliche Phase-2-Recherche-Ansicht (Solutions/
 * Best-Practices/Quellen) in den Gesamt-Workflow und ergänzt das
 * konfigurierbare Recherche-Gate (Abschnitt 25: "optional RECHERCHE
 * FREIGEBEN / ANMERKUNG / NEU RECHERCHIEREN"). Erhält die Daten jetzt
 * vom Orchestrator statt selbst zu fetchen (vermeidet einen doppelten
 * GET, da ProjectDetailView project bereits geladen hat). */
export function ResearchPanel({ project, onChanged }: { project: ProjectDetail; onChanged: (p: ProjectDetail) => void }) {
  const research = project.research;
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

  if (!research) return <section><h2>Recherche</h2><p className="muted">Recherche läuft…</p></section>;

  const showGate = project.workflow_state === "WAITING_FOR_RESEARCH_APPROVAL";

  return (
    <section>
      <h2>Recherche</h2>
      <section className="cards">
        {research.solutions.map((s) => (
          <article key={s.name}>
            <h3>{s.name} <small>{s.fit}</small></h3>
            <Markdown>{s.interesting}</Markdown>
            <strong>Wiederverwendbar</strong><Markdown>{s.reusable}</Markdown>
            <strong>Einschränkung</strong><Markdown>{s.constraint}</Markdown>
          </article>
        ))}
      </section>
      <h3>Best Practices</h3>
      <ul>{research.best_practices.map((x) => <li key={x}><Markdown>{x}</Markdown></li>)}</ul>
      <h3>Open-Source-Potenzial</h3>
      <Markdown>{research.open_source_potential}</Markdown>
      <h3>Fazit</h3>
      <Markdown>{research.conclusion}</Markdown>
      <h3>Quellen</h3>
      <ol>
        {research.sources.map((s) => (
          <li key={s.id}>
            <a href={safeUrl(s.url)} target="_blank" rel="noreferrer">{s.title}</a>
            {s.license_info && <> · Lizenz: {s.license_info}</>}
            <Markdown>{s.finding}</Markdown>
            <small>Abruf: {new Date(s.retrieved_at).toLocaleString()} · {s.provider}</small>
          </li>
        ))}
      </ol>

      {showGate && (
        <div className="gate">
          <h3>Recherche freigeben?</h3>
          {error && <p role="alert" className="error">{error}</p>}
          <div className="actions">
            <button type="button" disabled={busy} onClick={run(() => api.approveResearch(project.id))}>
              RECHERCHE FREIGEBEN
            </button>
            <button type="button" className="secondary" disabled={busy} onClick={run(() => api.rerunResearch(project.id, null))}>
              NEU RECHERCHIEREN
            </button>
          </div>
          <label>
            <span>Anmerkung (löst neue Recherche mit diesem Hinweis aus)</span>
            <textarea rows={2} value={comment} onChange={(e) => setComment(e.target.value)} />
          </label>
          <button type="button" className="secondary" disabled={busy || !comment.trim()} onClick={run(() => api.rerunResearch(project.id, comment))}>
            ANMERKUNG
          </button>
        </div>
      )}
    </section>
  );
}
