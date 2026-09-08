import UtilizationBars from "./UtilizationBars.jsx";

export default function CapacityCard({ cap }) {
  const stations = cap.stations.map((s) => ({ key: s.stngrp, label: s.stngrp, utilization: s.utilization }));
  return (
    <div className="card">
      <h2>Capacity &amp; Bottleneck (scenario)</h2>
      <div className="card-sub">Real SMT2020 tool counts · Little's Law + Kingman G/G/m queueing</div>
      <UtilizationBars stations={stations} bottleneckKey={cap.bottleneck} />
      <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 10 }}>
        ★ bottleneck: <b style={{ color: "var(--text-primary)" }}>{cap.bottleneck}</b>.
      </div>
    </div>
  );
}
