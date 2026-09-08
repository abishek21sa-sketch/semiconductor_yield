import BarRow from "./BarRow.jsx";
import { fmtPct } from "../api.js";

export default function OptCard({ opt }) {
  return (
    <div className="card">
      <h2>Release Optimization</h2>
      <div className="card-sub">Gurobi MILP against real order-demand data</div>
      {opt.status !== "optimal" ? (
        <div style={{ color: "var(--critical)", fontSize: 13 }}>
          Infeasible: no release plan can satisfy the minimum committed fill rate for all products
          under this scenario's capacity.
        </div>
      ) : (
        <OptBars opt={opt} />
      )}
    </div>
  );
}

function OptBars({ opt }) {
  const entries = Object.entries(opt.release_plan);
  const maxV = Math.max(...entries.map(([, v]) => v), 1);
  const total = entries.reduce((a, [, v]) => a + v, 0);
  return (
    <>
      {entries.map(([rid, v]) => (
        <BarRow
          key={rid}
          label={`part_${rid}`}
          pct={(v / maxV) * 100}
          valueText={`${v} lots (${fmtPct(opt.demand[rid].fill_rate)})`}
        />
      ))}
      <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 10 }}>
        Total: <b style={{ color: "var(--text-primary)" }}>{total} lots/week</b>. Binding
        constraint: <b style={{ color: "var(--text-primary)" }}>{opt.binding_station}</b>.
      </div>
    </>
  );
}
