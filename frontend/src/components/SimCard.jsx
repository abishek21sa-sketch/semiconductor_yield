import { fmtMin } from "../api.js";

export default function SimCard({ sim }) {
  const best = sim.reduce(
    (a, b) => (b.mean_cycle_time_min != null && (a.mean_cycle_time_min == null || b.mean_cycle_time_min < a.mean_cycle_time_min) ? b : a),
    sim[0]
  );

  return (
    <div className="card">
      <h2>Stochastic Simulation</h2>
      <div className="card-sub">SimPy discrete-event twin · Monte Carlo over dispatch/release policies</div>
      <table>
        <thead>
          <tr>
            <th>Policy</th>
            <th className="num">Mean CT</th>
            <th className="num">P95 CT</th>
            <th className="num">CVaR tail P95</th>
          </tr>
        </thead>
        <tbody>
          {sim.map((p) => (
            <tr key={p.policy} className={p === best ? "best" : ""}>
              <td>{p.policy}</td>
              <td className="num">{fmtMin(p.mean_cycle_time_min)}</td>
              <td className="num">{fmtMin(p.mean_p95_cycle_time_min)}</td>
              <td className="num">{fmtMin(p.cvar_tail_p95_cycle_time_min)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 8 }}>
        CT = cycle time. CVaR tail P95 = mean of the worst-case P95 outcomes across Monte Carlo
        replications (tail risk).
      </div>
    </div>
  );
}
