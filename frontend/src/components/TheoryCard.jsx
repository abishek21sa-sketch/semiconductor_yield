import { useEffect, useState } from "react";
import SvgLineChart from "./SvgLineChart.jsx";
import { fetchJSON } from "../api.js";

export default function TheoryCard() {
  const [curve, setCurve] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchJSON("/api/yield/theory?defect_density=0.5")
      .then(setCurve)
      .catch((e) => setError(e.message));
  }, []);

  return (
    <div className="card">
      <h2>Classical Yield Theory</h2>
      <div className="card-sub">Poisson vs. Murphy vs. Negative-Binomial yield models</div>
      {error && <div className="error-card">{error}</div>}
      {!curve && !error && (
        <div className="loading">
          <span className="spinner" />
        </div>
      )}
      {curve && (
        <>
          <SvgLineChart
            xDomain={[0, Math.max(...curve.map((c) => c.die_area_cm2))]}
            yDomain={[0, 1]}
            series={[
              { points: curve.map((c) => [c.die_area_cm2, c.poisson]), color: "var(--critical)" },
              { points: curve.map((c) => [c.die_area_cm2, c.murphy]), color: "var(--s1-blue)" },
              { points: curve.map((c) => [c.die_area_cm2, c.negative_binomial]), color: "var(--s3-aqua)" },
            ]}
            xLabel="die area (cm²) →"
            yLabel="yield"
          />
          <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4 }}>
            <span style={{ color: "var(--critical)" }}>—</span> Poisson{" "}
            <span style={{ color: "var(--s1-blue)" }}>—</span> Murphy{" "}
            <span style={{ color: "var(--s3-aqua)" }}>—</span> Negative-Binomial (α=2) at D₀=0.5
            defects/cm²
          </div>
        </>
      )}
    </div>
  );
}
