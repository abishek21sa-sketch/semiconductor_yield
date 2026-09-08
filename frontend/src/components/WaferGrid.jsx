/** Renders one real wafer defect map (0=no die, 1=pass, 2=fail) as a small
 * SVG grid -- the actual real per-die pattern, not a stylized icon. */
export default function WaferGrid({ grid, size = 90 }) {
  const n = grid.length;
  const cell = size / n;
  const colorFor = (v) => (v === 2 ? "var(--critical)" : v === 1 ? "var(--s1-blue)" : "var(--surface-2)");
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      {grid.map((row, y) =>
        row.map((v, x) =>
          v === 0 ? null : (
            <rect key={`${x}-${y}`} x={x * cell} y={y * cell} width={cell} height={cell} fill={colorFor(v)} />
          )
        )
      )}
    </svg>
  );
}
