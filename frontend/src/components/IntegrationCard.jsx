import BarRow from "./BarRow.jsx";
import { fmtNum, fmtPct } from "../api.js";

export default function IntegrationCard({ integ }) {
  return (
    <div className="card wide">
      <h2>Cross-Pipeline Integration</h2>
      <div className="card-sub">
        Two genuinely different real datasets feeding as parameters into the same real fab's planning
        problem -- not a fabricated row-level join between unrelated fabs. See Methodology.
      </div>

      <div className="stat-row">
        <div className="stat">
          <div className="v">{fmtPct(integ.yield_rate_used)}</div>
          <div className="l">Real SECOM yield rate used</div>
        </div>
        <div className="stat">
          <div className="v">{fmtNum(integ.capacity_plan_unadjusted_backlog)}</div>
          <div className="l">26-wk backlog, no yield adj.</div>
        </div>
        <div className="stat">
          <div className="v" style={{ color: "var(--warning)" }}>
            {fmtNum(integ.capacity_plan_yield_adjusted_backlog)}
          </div>
          <div className="l">26-wk backlog, yield-adjusted</div>
        </div>
        <div className="stat">
          <div className="v">
            {integ.backlog_delta_from_yield_loss != null ? `+${fmtNum(integ.backlog_delta_from_yield_loss)}` : "—"}
          </div>
          <div className="l">Backlog increase from real yield loss</div>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24, marginTop: 14 }}>
        <div
          style={{
            background: "var(--surface-2)", borderRadius: 8, padding: 14,
            border: "1px solid var(--critical)",
          }}
        >
          <div style={{ fontSize: 11, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: ".04em" }}>
            Capacity bottleneck
          </div>
          <div style={{ fontSize: 20, fontWeight: 650, marginTop: 4 }}>{integ.capacity_bottleneck_station}</div>
          <div style={{ fontSize: 11.5, color: "var(--text-muted)", marginTop: 6 }}>
            Where the fab is busiest (Little's Law + Kingman queueing on real tool counts)
          </div>
        </div>
        <div
          style={{
            background: "var(--surface-2)", borderRadius: 8, padding: 14,
            border: `1px solid ${integ.same_station_both_lenses ? "var(--good)" : "var(--warning)"}`,
          }}
        >
          <div style={{ fontSize: 11, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: ".04em" }}>
            Top quality-risk area
          </div>
          <div style={{ fontSize: 20, fontWeight: 650, marginTop: 4 }}>
            {integ.quality_risk?.top_quality_risk_station ?? "—"}
          </div>
          <div style={{ fontSize: 11.5, color: "var(--text-muted)", marginTop: 6 }}>
            Where real WM-811K defect patterns conventionally originate (stated heuristic mapping)
          </div>
        </div>
      </div>

      {integ.quality_risk && (
        <div style={{ marginTop: 16 }}>
          <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 8 }}>
            Real defect volume mapped to process area (share of all real classified defects)
          </div>
          {integ.quality_risk.stations.map((s) => (
            <BarRow
              key={s.stngrp}
              label={s.stngrp}
              pct={s.share_of_mapped_defects * 100}
              valueText={fmtPct(s.share_of_mapped_defects)}
              variant={s.stngrp === integ.quality_risk.top_quality_risk_station ? "bottleneck" : ""}
            />
          ))}
        </div>
      )}

      {!integ.same_station_both_lenses && integ.quality_risk && (
        <div style={{ fontSize: 12.5, color: "var(--text-secondary)", marginTop: 12, lineHeight: 1.5 }}>
          The capacity bottleneck ({integ.capacity_bottleneck_station}) and the top quality-risk area (
          {integ.quality_risk.top_quality_risk_station}) are <b style={{ color: "var(--text-primary)" }}>different stations</b> --
          fixing one wouldn't fix the other. A capacity investment at {integ.capacity_bottleneck_station} increases
          throughput; it does nothing for the real defect patterns pointing at {integ.quality_risk.top_quality_risk_station}.
        </div>
      )}
    </div>
  );
}
