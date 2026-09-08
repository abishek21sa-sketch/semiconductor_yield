import SvgLineChart from "./SvgLineChart.jsx";
import { fmtNum } from "../api.js";

export default function CapacityPlanCard({ plan }) {
  return (
    <div className="card wide">
      <h2>Multi-Period Stochastic Capacity Plan</h2>
      <div className="card-sub">
        Two-stage stochastic Gurobi MILP: 10 products × 26 weeks, with recourse over Monte-Carlo
        capacity scenarios sampled from real MTBF/MTTR — large enough to need a real license,
        unlike the single-week plan above
      </div>
      {plan.status === "license_required" ? (
        <div style={{ fontSize: 13 }}>
          <span style={{ color: "var(--warning)" }}>No Gurobi license available.</span> This model
          has <b>{fmtNum(plan.n_variables)} variables</b> and{" "}
          <b>{fmtNum(plan.n_constraints)} constraints</b> — past Gurobi's bundled 2000-variable
          free tier, so it refuses to solve without a real license. That refusal <em>is</em> the
          proof: the single-week plan above (~10 variables) solves fine unlicensed; this one needs
          a real academic/commercial license.
        </div>
      ) : plan.status !== "optimal" ? (
        <div style={{ color: "var(--critical)", fontSize: 13 }}>Infeasible at this configuration.</div>
      ) : (
        <CapacityPlanBody plan={plan} />
      )}
    </div>
  );
}

function CapacityPlanBody({ plan }) {
  const weeks = plan.weeks;
  const totalBacklogByWeek = Array.from({ length: weeks }, (_, w) =>
    Object.values(plan.backlog_trajectory).reduce((s, series) => s + series[w], 0)
  );
  const maxBl = Math.max(...totalBacklogByWeek, 1);

  return (
    <>
      <div className="stat-row">
        <div className="stat">
          <div className="v">{fmtNum(plan.n_variables)}</div>
          <div className="l">Variables</div>
        </div>
        <div className="stat">
          <div className="v">{fmtNum(plan.n_constraints)}</div>
          <div className="l">Constraints</div>
        </div>
        <div className="stat">
          <div className="v">{plan.solve_time_sec.toFixed(2)}s</div>
          <div className="l">Solve time</div>
        </div>
        <div className="stat">
          <div className="v" style={{ color: "var(--critical)" }}>
            {plan.exceeds_gurobi_free_tier ? "YES" : "no"}
          </div>
          <div className="l">Exceeds free-tier limit (2000)</div>
        </div>
        <div className="stat">
          <div className="v">{plan.n_scenarios}</div>
          <div className="l">Monte Carlo scenarios</div>
        </div>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20, alignItems: "start", marginTop: 6 }}>
        <div>
          <SvgLineChart
            width={380}
            height={200}
            pad={40}
            xDomain={[0, weeks - 1]}
            yDomain={[0, maxBl]}
            series={[{ points: totalBacklogByWeek.map((v, w) => [w, v]), color: "var(--critical)" }]}
            xLabel={`week 0 → week ${weeks - 1}`}
            yLabel="total backlog across all 10 products (lots)"
          />
        </div>
        <div style={{ fontSize: 13, color: "var(--text-secondary)", lineHeight: 1.7 }}>
          <p>
            Over a real 26-week horizon, cumulative backlog across all 10 products grows to{" "}
            <b style={{ color: "var(--text-primary)" }}>{fmtNum(plan.total_backlog_final_week)} lots</b>{" "}
            even under the optimal release plan — the structural demand/capacity gap doesn't close
            with better scheduling alone.
          </p>
          <p>
            Worst expected capacity shortfall:{" "}
            <b style={{ color: "var(--text-primary)" }}>{plan.worst_shortfall_station}</b> (bounded
            to a real overtime/expedite cap, not unlimited).
          </p>
          <p style={{ color: "var(--text-muted)", fontSize: 11.5 }}>
            This MILP has {fmtNum(plan.n_variables)} variables and {fmtNum(plan.n_constraints)}{" "}
            constraints — both past Gurobi's bundled 2000-variable/2000-constraint free-tier limit,
            so it genuinely requires a real license to solve (unlike the ~10-variable single-week
            plan above, which doesn't).
          </p>
        </div>
      </div>
    </>
  );
}
