import { fmtNum, fmtPct } from "../api.js";

function ArchetypeColumn({ label, sub, a }) {
  return (
    <div style={{ background: "var(--surface-2)", borderRadius: 8, padding: 14 }}>
      <div style={{ fontSize: 13, fontWeight: 650 }}>{label}</div>
      <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 10 }}>{sub}</div>
      <div className="stat-row" style={{ marginBottom: 0 }}>
        <div className="stat">
          <div className="v">{a.n_products}</div>
          <div className="l">Real products</div>
        </div>
        <div className="stat">
          <div className="v">{fmtNum(a.total_real_weekly_demand_lots)}</div>
          <div className="l">Real demand (lots/wk)</div>
        </div>
      </div>
      <div style={{ marginTop: 10 }}>
        <div style={{ fontSize: 11, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: ".04em" }}>
          Bottleneck
        </div>
        <div style={{ fontSize: 18, fontWeight: 650, color: "var(--critical)" }}>{a.bottleneck}</div>
        <div style={{ fontSize: 12.5, color: "var(--text-secondary)", marginTop: 2 }}>
          {fmtPct(a.bottleneck_utilization)} utilized &middot; {fmtNum(a.bottleneck_wait_min)} min Kingman wait
        </div>
      </div>
    </div>
  );
}

export default function ArchetypeComparisonCard({ cmp }) {
  return (
    <div className="card wide">
      <h2>Real Fab Archetype Comparison: LVHM vs. HVLM</h2>
      <div className="card-sub">
        The same real SMT2020 fab -- same {fmtNum(106)} real tools, even the same two route files reused
        verbatim -- under two real published demand-concentration scenarios, evaluated at the same total
        release rate so the comparison is apples-to-apples. See Methodology / data/smt2020_hvlm/ATTRIBUTION.md.
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20 }}>
        <ArchetypeColumn
          label="LVHM -- Low-Volume-High-Mix"
          sub="10 real products sharing the same real demand pool"
          a={cmp.lvhm}
        />
        <ArchetypeColumn
          label="HVLM -- High-Volume-Low-Mix"
          sub="Same real demand pool concentrated onto 2 real products"
          a={cmp.hvlm}
        />
      </div>
      <div style={{ fontSize: 12.5, color: "var(--text-secondary)", marginTop: 14, lineHeight: 1.55 }}>
        {cmp.same_bottleneck_station ? (
          <>
            Both archetypes bottleneck at the <b style={{ color: "var(--text-primary)" }}>same station</b>{" "}
            ({cmp.lvhm.bottleneck}), but concentrating the identical total real demand onto HVLM's 2 products
            instead of LVHM's 10 pushes utilization{" "}
            <b style={{ color: "var(--text-primary)" }}>{fmtPct(Math.abs(cmp.bottleneck_utilization_delta))} higher</b>{" "}
            and Kingman queueing wait{" "}
            <b style={{ color: "var(--text-primary)" }}>{fmtPct(Math.abs(cmp.bottleneck_wait_delta_fraction))} worse</b> --
            same tools, same total volume, worse congestion, purely from product-mix concentration.
          </>
        ) : (
          <>
            The two archetypes bottleneck at <b style={{ color: "var(--text-primary)" }}>different stations</b> despite
            sharing the exact same real tool inventory -- product-mix concentration alone shifts where the real
            constraint is.
          </>
        )}
      </div>
    </div>
  );
}
