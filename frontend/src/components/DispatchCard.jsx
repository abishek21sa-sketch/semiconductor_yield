import BarRow from "./BarRow.jsx";
import { fmtNum } from "../api.js";

export default function DispatchCard({ d }) {
  return (
    <div className="card wide">
      <h2>Bottleneck Dispatch Scheduler</h2>
      <div className="card-sub">
        Exact MILP: real batch formation (Diffusion, real BATCHMN/BATCHMX wafer limits) + parallel-machine
        sequencing (Dry_Etch, 21 real tools), minimizing weighted tardiness against real due dates
        — the tractable exact complement to the full-scope-but-heuristic simulation above (see
        Methodology for why full-fab exact scheduling isn't tractable at real fab scale)
      </div>
      {d.status === "license_required" ? (
        <div style={{ fontSize: 13 }}>
          <span style={{ color: "var(--warning)" }}>No Gurobi license available.</span> This
          dispatch problem needs an estimated <b>{fmtNum(d.n_variables)}+ variables</b> — past the
          free tier, so it refuses to solve unlicensed.
        </div>
      ) : d.status !== "optimal" ? (
        <div style={{ color: "var(--critical)", fontSize: 13 }}>Infeasible at this configuration.</div>
      ) : (
        <DispatchBody d={d} />
      )}
    </div>
  );
}

function DispatchBody({ d }) {
  const diffPct = d.n_diffusion_batches ? d.on_time_diffusion / d.n_diffusion_batches : 1;
  const etchPct = d.n_dryetch_jobs ? d.on_time_dryetch / d.n_dryetch_jobs : 1;

  return (
    <>
      <div className="stat-row">
        <div className="stat">
          <div className="v">{d.n_diffusion_lots}</div>
          <div className="l">Diffusion lots</div>
        </div>
        <div className="stat">
          <div className="v">{d.n_diffusion_batches}</div>
          <div className="l">Batches formed</div>
        </div>
        <div className="stat">
          <div className="v">{d.n_dryetch_jobs}</div>
          <div className="l">Dry-etch jobs</div>
        </div>
        <div className="stat">
          <div className="v">{fmtNum(d.n_variables)}</div>
          <div className="l">Variables</div>
        </div>
        <div className="stat">
          <div className="v">{d.solve_time_sec.toFixed(2)}s</div>
          <div className="l">Solve time</div>
        </div>
        <div className="stat">
          <div className="v" style={{ color: d.total_weighted_tardiness_hours > 0 ? "var(--critical)" : "var(--good)" }}>
            {fmtNum(d.total_weighted_tardiness_hours, 0)}h
          </div>
          <div className="l">Total tardiness</div>
        </div>
      </div>
      <BarRow
        label="Diffusion (batched)"
        pct={diffPct * 100}
        valueText={`${d.on_time_diffusion}/${d.n_diffusion_batches} on time`}
        variant={diffPct < 0.9 ? "bottleneck" : ""}
      />
      <BarRow
        label="Dry-Etch (individual)"
        pct={etchPct * 100}
        valueText={`${d.on_time_dryetch}/${d.n_dryetch_jobs} on time`}
        variant={etchPct < 0.9 ? "bottleneck" : ""}
      />
      <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 10 }}>
        Real batch formation lets Diffusion absorb this load with {diffPct >= 0.99 ? "zero" : "little"}{" "}
        tardiness even though it has fewer machines (10) than Dry-Etch (21) — because batching
        multiple lots per furnace run multiplies effective throughput, while Dry-Etch schedules
        lots one at a time. That's a real, explainable reason batch processes and single-wafer
        processes need different capacity strategies, not an artifact of the model.
      </div>
    </>
  );
}
