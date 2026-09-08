import BarRow from "./BarRow.jsx";
import { fmtPct } from "../api.js";

/**
 * stations: [{ key, label, utilization }].
 * sortDescending: reorder worst-first (used by the What-If panel); when false,
 * the given order is kept as-is (used by the scenario Capacity card).
 * Renders bars only -- callers render their own caption line below.
 */
export default function UtilizationBars({ stations, bottleneckKey, sortDescending = false }) {
  const ordered = sortDescending ? [...stations].sort((a, b) => b.utilization - a.utilization) : stations;
  const maxUtil = Math.max(1.0, ...ordered.map((s) => s.utilization));

  return (
    <>
      {ordered.map((s) => {
        const pct = Math.min(100, (s.utilization / maxUtil) * 100);
        const variant = s.key === bottleneckKey ? "bottleneck" : s.utilization > 0.8 ? "warn" : "";
        return (
          <BarRow
            key={s.key}
            label={s.key === bottleneckKey ? `${s.label} ★` : s.label}
            pct={pct}
            valueText={fmtPct(s.utilization)}
            variant={variant}
          />
        );
      })}
    </>
  );
}
