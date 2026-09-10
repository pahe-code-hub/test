import { useState } from "react";
import { api, ApiError, type IntakeFields, type ProjectDetail } from "./api";

/** Abschnitt 3: sechs Eingabebereiche. PATCH .../intake ist nur bei
 * DRAFT erlaubt (Guard in routers/projects.py) und speichert bei jedem
 * Feldverlust automatisch als Entwurf - "IDEE PRÜFEN" (submit) prüft
 * serverseitig, dass alle sechs Felder ausgefüllt sind
 * (INCOMPLETE_INTAKE sonst). */
const FIELDS: { key: keyof IntakeFields; label: string; hint: string }[] = [
  { key: "goal", label: "Ziel", hint: "Was soll erreicht werden?" },
  { key: "problem", label: "Problem", hint: "Welches Problem wird gelöst?" },
  { key: "users_structure", label: "Nutzer/Struktur", hint: "Wer nutzt es, wie viele, welche Struktur?" },
  { key: "interface_output", label: "Interface/Ausgabe", hint: "Wie wird interagiert, was kommt raus?" },
  { key: "constraints", label: "Einschränkungen", hint: "Technische/organisatorische Grenzen?" },
  { key: "core_features", label: "Kernfunktionen", hint: "Was muss es können (Minimum)?" },
];

export function IntakeForm({ project, onChanged }: { project: ProjectDetail; onChanged: (p: ProjectDetail) => void }) {
  const [values, setValues] = useState<IntakeFields>({ ...project.intake });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const save = async (key: keyof IntakeFields, value: string) => {
    if (value === project.intake[key]) return; // nichts geändert, kein Request nötig
    setSaving(true);
    try {
      const updated = await api.patchIntake(project.id, { [key]: value });
      onChanged(updated);
      setError("");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  const submit = async () => {
    setSubmitting(true);
    setError("");
    try {
      const updated = await api.submit(project.id);
      onChanged(updated);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  };

  const allFilled = FIELDS.every((f) => values[f.key].trim().length > 0);

  return (
    <section>
      <h2>Idee</h2>
      <p className="muted">Alle sechs Felder sind Pflicht, bevor die Idee geprüft werden kann. Änderungen werden beim Verlassen eines Felds automatisch als Entwurf gespeichert.</p>
      <div className="intake-grid">
        {FIELDS.map((f) => (
          <label key={f.key} className="intake-field">
            <span>{f.label}</span>
            <textarea
              rows={4}
              maxLength={4000}
              value={values[f.key]}
              placeholder={f.hint}
              onChange={(e) => setValues((v) => ({ ...v, [f.key]: e.target.value }))}
              onBlur={(e) => save(f.key, e.target.value)}
            />
          </label>
        ))}
      </div>
      {saving && <p className="muted">Speichere Entwurf…</p>}
      {error && <p role="alert" className="error">{error}</p>}
      <button type="button" disabled={!allFilled || submitting} onClick={submit}>
        {submitting ? "Prüfe…" : "IDEE PRÜFEN"}
      </button>
      {!allFilled && <p className="muted">Alle sechs Felder ausfüllen, um fortzufahren.</p>}
    </section>
  );
}
