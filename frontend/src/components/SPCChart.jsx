import { fmtNum } from "../api.js";

export default function SPCChart({ spc }) {
  const pts = spc.points;
  const w = 380,
    h = 220,
    pad = 36;
  const vals = pts.map((p) => p.v);
  const vmin = Math.min(...vals, spc.lcl);
  const vmax = Math.max(...vals, spc.ucl);
  const x = (i) => pad + (i / (pts.length - 1)) * (w - 2 * pad);
  const y = (v) => h - pad - ((v - vmin) / (vmax - vmin)) * (h - 2 * pad);

  return (
    <>
      <svg className="chart" viewBox={`0 0 ${w} ${h}`}>
        <line x1={pad} y1={y(spc.ucl)} x2={w - pad} y2={y(spc.ucl)} stroke="var(--warning)" strokeDasharray="4 3" strokeWidth="1" />
        <line x1={pad} y1={y(spc.lcl)} x2={w - pad} y2={y(spc.lcl)} stroke="var(--warning)" strokeDasharray="4 3" strokeWidth="1" />
        <line x1={pad} y1={y(spc.mu)} x2={w - pad} y2={y(spc.mu)} stroke="var(--baseline)" strokeWidth="1" />
        {pts.map((p, i) => {
          const oob = p.v > spc.ucl || p.v < spc.lcl;
          const color = p.fail ? "var(--critical)" : oob ? "var(--warning)" : "var(--s1-blue)";
          return <circle key={i} cx={x(i)} cy={y(p.v)} r={p.fail ? 2.8 : 1.8} fill={color} opacity={p.fail ? 0.95 : 0.55} />;
        })}
        <text className="axis-label" x={pad} y={14}>
          UCL {fmtNum(spc.ucl, 1)}
        </text>
        <text className="axis-label" x={pad} y={h - 6}>
          LCL {fmtNum(spc.lcl, 1)}
        </text>
      </svg>
      <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4 }}>
        <span style={{ color: "var(--critical)" }}>●</span> fail lot{" "}
        <span style={{ color: "var(--warning)" }}>●</span> pass, out-of-band{" "}
        <span style={{ color: "var(--s1-blue)" }}>●</span> pass, in-band
      </div>
    </>
  );
}
