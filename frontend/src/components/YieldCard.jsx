import BarRow from "./BarRow.jsx";
import { fmtPct } from "../api.js";

export default function YieldCard({ y }) {
  const m = y.model,
    meta = y.meta;
  const top = y.top_sensors.slice(0, 8);
  const maxImp = Math.max(...top.map((s) => s.importance));

  return (
    <div className="card wide">
      <h2>Yield Risk — SECOM real fab sensor data</h2>
      <div className="card-sub">UCI ML Repository #179 · 1567 real production lots, real pass/fail outcomes</div>
      <div className="stat-row">
        <div className="stat">
          <div className="v">{fmtPct(meta.yield_rate)}</div>
          <div className="l">Yield rate</div>
        </div>
        <div className="stat">
          <div className="v">{meta.n_lots}</div>
          <div className="l">Lots ({meta.n_fails} fails)</div>
        </div>
        <div className="stat">
          <div className="v">{meta.n_sensors_raw}</div>
          <div className="l">Real sensors ({meta.n_sensors_used} used)</div>
        </div>
        <div className="stat">
          <div className="v">{m.roc_auc.toFixed(3)}</div>
          <div className="l">ROC-AUC</div>
        </div>
        <div className="stat">
          <div className="v">{m.pr_auc.toFixed(3)}</div>
          <div className="l">PR-AUC</div>
        </div>
      </div>
      <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 10 }}>
        {m.type}. Majority-class baseline accuracy: {fmtPct(m.majority_class_accuracy)} (imbalanced{" "}
        {fmtPct(1 - meta.yield_rate)} fail rate — accuracy alone is misleading here, which is why
        ROC/PR-AUC matter).
      </div>
      <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 6 }}>
        Top sensors driving predicted failure (Random Forest importance):
      </div>
      {top.map((s) => (
        <BarRow
          key={s.sensor}
          label={s.sensor}
          pct={(s.importance / maxImp) * 100}
          valueText={`${(s.importance * 100).toFixed(2)}%`}
        />
      ))}
    </div>
  );
}
