import { useMemo, useState } from "react";
import UtilizationBars from "./UtilizationBars.jsx";
import { fmtPct } from "../api.js";
import { computeWhatIf } from "../lib/whatif.js";

export default function WhatIfPanel({ topology }) {
  const [diff, setDiff] = useState(10);
  const [litho, setLitho] = useState(11);
  const [rate, setRate] = useState(19);

  const results = useMemo(() => computeWhatIf(topology, diff, litho, rate), [topology, diff, litho, rate]);
  const worst = useMemo(() => [...results].sort((a, b) => b.utilization - a.utilization)[0], [results]);

  return (
    <section className="whatif">
      <h2>What-If: drag the levers yourself</h2>
      <div className="card-sub">
        Live client-side recompute against the real SMT2020 topology — not a canned scenario, an
        actual model you can perturb
      </div>
      <div className="whatif-grid">
        <div>
          <div className="slider-row">
            <label>
              Diffusion furnaces available <span className="val">{diff} / 10</span>
            </label>
            <input type="range" min="1" max="10" step="1" value={diff} onChange={(e) => setDiff(+e.target.value)} />
            <div className="whatif-note">Real count: 10. This is the fab's actual bottleneck.</div>
          </div>
          <div className="slider-row">
            <label>
              Litho tools available <span className="val">{litho} / 11</span>
            </label>
            <input type="range" min="1" max="11" step="1" value={litho} onChange={(e) => setLitho(+e.target.value)} />
            <div className="whatif-note">Real count: 11. Try cutting this — watch output not move.</div>
          </div>
          <div className="slider-row">
            <label>
              Weekly release pace <span className="val">{rate} lots/wk</span>
            </label>
            <input type="range" min="5" max="60" step="1" value={rate} onChange={(e) => setRate(+e.target.value)} />
            <div className="whatif-note">Real weekly order demand across all 10 products: ~390 lots/wk.</div>
          </div>
          <div id="whatif-bottleneck-line">
            {worst && worst.utilization >= 1 ? (
              <span style={{ color: "var(--critical)" }}>
                Unstable — {worst.key} exceeds capacity, queue grows without bound.
              </span>
            ) : (
              worst && (
                <>
                  Stable. Bottleneck: <b>{worst.key}</b> at {fmtPct(worst.utilization)}.
                </>
              )
            )}
          </div>
        </div>
        <div>
          <UtilizationBars stations={results} bottleneckKey={worst?.key} sortDescending />
        </div>
      </div>
    </section>
  );
}
