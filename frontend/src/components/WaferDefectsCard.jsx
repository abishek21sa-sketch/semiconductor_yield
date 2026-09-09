import { useState } from "react";
import BarRow from "./BarRow.jsx";
import ConfusionMatrix from "./ConfusionMatrix.jsx";
import WaferGrid from "./WaferGrid.jsx";
import { fmtNum } from "../api.js";

export default function WaferDefectsCard({ w, baseline }) {
  return (
    <div className="card wide">
      <h2>Wafer Defect Pattern Classification</h2>
      <div className="card-sub">
        Real CNN (PyTorch) over the real WM-811K wafer defect-map dataset -- 172,950 human-labeled
        real wafers from 46,293 real lots, 9 real classes
      </div>
      {w.status === "not_trained" ? (
        <div style={{ fontSize: 13 }}>
          <span style={{ color: "var(--warning)" }}>No trained model available.</span> {w.message}
        </div>
      ) : (
        <WaferDefectsBody w={w} baseline={baseline} />
      )}
    </div>
  );
}

function WaferDefectsBody({ w, baseline }) {
  const [showHeatmap, setShowHeatmap] = useState(true);
  const distEntries = Object.entries(w.class_distribution);
  const maxCount = Math.max(...distEntries.map(([, v]) => v));
  const hasBaseline = baseline && baseline.status === "trained";

  return (
    <>
      <div className="stat-row">
        <div className="stat">
          <div className="v">{w.test_macro_f1.toFixed(3)}</div>
          <div className="l">Test macro-F1</div>
        </div>
        <div className="stat">
          <div className="v">{(w.test_accuracy * 100).toFixed(1)}%</div>
          <div className="l">Test accuracy</div>
        </div>
        <div className="stat">
          <div className="v">{fmtNum(w.n_labeled_total)}</div>
          <div className="l">Labeled real wafers</div>
        </div>
        <div className="stat">
          <div className="v">{fmtNum(w.n_unlabeled_total)}</div>
          <div className="l">Unlabeled real wafers (unused)</div>
        </div>
        <div className="stat">
          <div className="v">{fmtNum(w.n_train)}</div>
          <div className="l">Training examples ({w.epochs} epochs)</div>
        </div>
        <div className="stat">
          <div className="v">{(w.train_seconds / 60).toFixed(1)}m</div>
          <div className="l">Training time (CPU)</div>
        </div>
      </div>

      {hasBaseline && (
        <div
          style={{
            display: "flex", gap: 20, alignItems: "center", background: "var(--surface-2)",
            borderRadius: 8, padding: "10px 14px", marginTop: 4, marginBottom: 14, fontSize: 13,
          }}
        >
          <div>
            <b style={{ color: "var(--text-primary)" }}>CNN: {w.test_macro_f1.toFixed(3)} macro-F1</b>
          </div>
          <div style={{ color: "var(--text-muted)" }}>vs.</div>
          <div style={{ color: "var(--text-secondary)" }}>
            Hand-engineered-feature baseline (RandomForest, same real split): {baseline.test_macro_f1.toFixed(3)}
          </div>
          <div style={{ color: w.test_macro_f1 > baseline.test_macro_f1 ? "var(--good)" : "var(--critical)", fontWeight: 600 }}>
            {w.test_macro_f1 > baseline.test_macro_f1 ? "+" : ""}
            {(w.test_macro_f1 - baseline.test_macro_f1).toFixed(3)}
          </div>
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "1.1fr 1fr", gap: 24, alignItems: "start", marginTop: 14 }}>
        <div>
          <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 8 }}>
            Real class distribution (log scale imbalance: {fmtNum(w.class_distribution.none)} "none" vs{" "}
            {fmtNum(w.class_distribution["Near-full"])} "Near-full")
          </div>
          {distEntries
            .sort((a, b) => b[1] - a[1])
            .map(([cls, count]) => (
              <BarRow key={cls} label={cls} pct={(count / maxCount) * 100} valueText={fmtNum(count)} />
            ))}

          <div style={{ fontSize: 12, color: "var(--text-muted)", margin: "16px 0 8px" }}>
            Per-class test-set performance (never rebalanced -- real distribution)
          </div>
          <table>
            <thead>
              <tr>
                <th>Class</th>
                <th className="num">Precision</th>
                <th className="num">Recall</th>
                <th className="num">F1</th>
                <th className="num">n</th>
              </tr>
            </thead>
            <tbody>
              {w.test_per_class.map((p) => (
                <tr key={p.class}>
                  <td>{p.class}</td>
                  <td className="num">{(p.precision * 100).toFixed(0)}%</td>
                  <td className="num">{(p.recall * 100).toFixed(0)}%</td>
                  <td className="num">{p.f1.toFixed(2)}</td>
                  <td className="num">{p.support}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div>
          <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 8 }}>
            Confusion matrix (real test-set predictions, {fmtNum(w.n_test)} wafers)
          </div>
          <ConfusionMatrix classes={w.classes} matrix={w.test_confusion_matrix} />
        </div>
      </div>

      {w.sample_gallery && (
        <>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", margin: "18px 0 8px" }}>
            <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
              Real test-set wafer maps, true vs. predicted (blue = pass die, red = fail die)
              {w.sample_gallery[0]?.heatmap && " -- yellow glow = real Grad-CAM attention (what the model looked at)"}
            </div>
            {w.sample_gallery[0]?.heatmap && (
              <label style={{ fontSize: 11.5, color: "var(--text-secondary)", display: "flex", alignItems: "center", gap: 5, cursor: "pointer" }}>
                <input type="checkbox" checked={showHeatmap} onChange={(e) => setShowHeatmap(e.target.checked)} />
                Grad-CAM overlay
              </label>
            )}
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
            {w.sample_gallery.map((s, i) => (
              <div
                key={i}
                style={{
                  background: "var(--surface-2)", borderRadius: 8, padding: 8, width: 108,
                  border: `1px solid ${s.correct ? "var(--good)" : "var(--critical)"}`,
                }}
              >
                <WaferGrid grid={s.grid} size={90} heatmap={showHeatmap ? s.heatmap : null} />
                <div style={{ fontSize: 9.5, marginTop: 4, textAlign: "center", lineHeight: 1.3 }}>
                  <div style={{ color: "var(--text-secondary)" }}>true: {s.true_label}</div>
                  <div style={{ color: s.correct ? "var(--good)" : "var(--critical)" }}>
                    pred: {s.predicted_label}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      <div style={{ fontSize: 11.5, color: "var(--text-muted)", marginTop: 14 }}>
        Trained with class-weighted loss against the real ~1000:1 imbalance between "none" and
        "Near-full"; the training split additionally caps the dominant "none" class (real: 117,944
        of 138,357 training examples) to {fmtNum(w.max_none_train)} so an epoch doesn't spend
        nearly all its time on the majority class -- every other class keeps every real training
        example, and validation/test are never rebalanced. Nearest-neighbor resize to{" "}
        {w.wafer_size}×{w.wafer_size} preserves the real categorical {"{0,1,2}"} values (no
        interpolation artifacts). Rotation/flip augmentation is {w.augment ? "on" : "off"} for this
        run, based on a real same-seed controlled A/B (69.8% vs 69.0% macro-F1) -- a first,
        unseeded comparison wrongly suggested it hurt; fixing that bug and rerunning it properly
        reversed the conclusion. See Methodology for the full write-up.
      </div>
    </>
  );
}
