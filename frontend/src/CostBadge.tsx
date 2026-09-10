import { useState } from "react";
import { api, ROLE_LABELS, type CostOut } from "./api";

const fmtUsd = (n: number) => `$${n.toFixed(4)}`;

/** Abschnitt 32 (Kostenkontrolle): Anzahl Modellaufrufe, geschätzte
 * Kosten - Gesamtsumme immer sichtbar (schon Teil von ProjectDetail,
 * kein Extra-Request nötig), Aufschlüsselung je Rolle on-demand über
 * GET /cost. */
export function CostBadge({ projectId, totalCalls, totalCost }: { projectId: string; totalCalls: number; totalCost: number }) {
  const [breakdown, setBreakdown] = useState<CostOut | null>(null);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState("");

  const toggle = () => {
    if (open) { setOpen(false); return; }
    setOpen(true);
    api.getCost(projectId).then(setBreakdown).catch((e) => setError(String(e.message ?? e)));
  };

  return (
    <div className="cost-badge">
      <button type="button" className="link-button" onClick={toggle}>
        {totalCalls} Modellaufrufe · {fmtUsd(totalCost)}
      </button>
      {open && (
        <div className="cost-detail" role="region" aria-label="Kosten je Rolle">
          {error && <p role="alert">{error}</p>}
          {!error && !breakdown && <p>Lädt…</p>}
          {breakdown && (
            <table>
              <tbody>
                {Object.entries(breakdown.by_role).map(([role, v]) => (
                  <tr key={role}>
                    <td>{ROLE_LABELS[role] ?? role}</td>
                    <td>{v.calls}×</td>
                    <td>{fmtUsd(v.estimated_cost_usd)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}
