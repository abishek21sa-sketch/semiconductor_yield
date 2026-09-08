/** Generic multi-series line chart. Domains are passed explicitly by the caller
 * (matches each card's own axis convention) rather than inferred, so behavior
 * stays exact per use site. */
export default function SvgLineChart({
  width = 380,
  height = 220,
  pad = 36,
  xDomain,
  yDomain,
  series,
  xLabel,
  yLabel,
}) {
  const [xmin, xmax] = xDomain;
  const [ymin, ymax] = yDomain;
  const x = (v) => pad + ((v - xmin) / (xmax - xmin)) * (width - 2 * pad);
  const y = (v) => height - pad - ((v - ymin) / (ymax - ymin)) * (height - 2 * pad);

  return (
    <svg className="chart" viewBox={`0 0 ${width} ${height}`}>
      {series.map((s, i) => {
        const d = s.points.map(([px, py], j) => `${j === 0 ? "M" : "L"} ${x(px)} ${y(py)}`).join(" ");
        return (
          <path
            key={i}
            d={d}
            fill="none"
            stroke={s.color}
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        );
      })}
      {xLabel && (
        <text className="axis-label" x={pad} y={height - 6}>
          {xLabel}
        </text>
      )}
      {yLabel && (
        <text className="axis-label" x={pad} y={14}>
          {yLabel}
        </text>
      )}
    </svg>
  );
}
