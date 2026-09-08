import SPCChart from "./SPCChart.jsx";

export default function SPCCard({ spc }) {
  return (
    <div className="card">
      <h2>SPC Control Chart</h2>
      <div className="card-sub">
        Sensor {spc.sensor} · {spc.n_out_of_band} lots outside ±3σ band
      </div>
      <SPCChart spc={spc} />
    </div>
  );
}
