import { fmtNum, fmtPct } from "../api.js";

export default function HeroStats({ y, topo, opt, wafer }) {
  const meta = y.meta;
  const totalSteps = Object.values(topo.route_step_counts).reduce((a, b) => a + b, 0);
  const totalDemand = Object.values(topo.demand).reduce((a, b) => a + (b || 0), 0);

  let gapText = "…";
  if (opt) {
    if (opt.status !== "optimal") {
      gapText = "100%";
    } else {
      const released = Object.values(opt.release_plan).reduce((a, b) => a + b, 0);
      const unmet = 1 - released / totalDemand;
      gapText = fmtPct(Math.max(0, unmet));
    }
  }

  const tiles = [
    { v: fmtNum(meta.n_lots), l: "Real fab lots analyzed" },
    { v: fmtNum(meta.n_sensors_raw), l: "Real process sensors" },
    { v: fmtNum(totalSteps), l: "Real reentrant process steps modeled" },
    { v: "IEEE TSM 2020", l: "Published fab benchmark" },
  ];
  if (wafer && wafer.status === "trained") {
    tiles.push({ v: fmtNum(wafer.n_labeled_total), l: "Real labeled wafer defect images (CNN)" });
  }

  return (
    <section className="hero">
      {tiles.map((t) => (
        <div className="stat-tile" key={t.l}>
          <div className="value">{t.v}</div>
          <div className="label">{t.l}</div>
        </div>
      ))}
      <div className="stat-tile headline">
        <div className="value">{gapText}</div>
        <div className="label">of real weekly demand unmet at the bottleneck</div>
      </div>
    </section>
  );
}
