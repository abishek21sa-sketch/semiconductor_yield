/** Renders one real wafer defect map (0=no die, 1=pass, 2=fail) as a small
 * SVG grid -- the actual real per-die pattern, not a stylized icon.
 * Optional `heatmap` (same-ish resolution 2D array, 0-1) overlays the CNN's
 * real Grad-CAM attention as a translucent glow -- where the model actually
 * looked, not just what it predicted. */
export default function WaferGrid({ grid, size = 90, heatmap = null }) {
  const n = grid.length;
  const cell = size / n;
  const colorFor = (v) => (v === 2 ? "var(--critical)" : v === 1 ? "var(--s1-blue)" : "var(--surface-2)");
  const hm = heatmap && heatmap.length ? heatmap : null;
  const hn = hm ? hm.length : 0;
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      {grid.map((row, y) =>
        row.map((v, x) =>
          v === 0 ? null : (
            <rect key={`${x}-${y}`} x={x * cell} y={y * cell} width={cell} height={cell} fill={colorFor(v)} />
          )
        )
      )}
      {hm &&
        hm.map((row, y) =>
          row.map((val, x) => {
            if (val < 0.35) return null;
            const hcell = size / hn;
            return (
              <rect
                key={`h-${x}-${y}`}
                x={x * hcell}
                y={y * hcell}
                width={hcell}
                height={hcell}
                fill="var(--s4-yellow)"
                opacity={Math.min(0.55, val * 0.55)}
              />
            );
          })
        )}
    </svg>
  );
}
