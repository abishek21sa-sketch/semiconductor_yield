const FLOW_STEPS = [
  { n: "01", t: "Real fab sensor data", d: "SECOM: 1567 lots, real pass/fail" },
  { n: "02", t: "Yield-risk AI", d: "Cross-validated RF + classical yield theory" },
  { n: "03", t: "SPC monitoring", d: "3σ band on top failure sensor" },
  { n: "04", t: "Capacity & bottleneck", d: "Little's Law + Kingman on real topology" },
  { n: "05", t: "Stochastic simulation", d: "SimPy twin, Monte Carlo, real MTBF/MTTR" },
  { n: "06", t: "Gurobi optimization", d: "Real-demand-constrained release MILP" },
];

export default function PipelineFlow() {
  return (
    <section className="pipeline">
      <h2>Pipeline</h2>
      <div className="card-sub">Six stages, each computed from real data — no stage is a placeholder</div>
      <div className="flow">
        {FLOW_STEPS.map((s) => (
          <div className="flow-step" key={s.n}>
            <div className="n">{s.n}</div>
            <div className="t">{s.t}</div>
            <div className="d">{s.d}</div>
          </div>
        ))}
      </div>
    </section>
  );
}
