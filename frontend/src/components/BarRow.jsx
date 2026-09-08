export default function BarRow({ label, pct, valueText, variant = "" }) {
  return (
    <div className="bar-row">
      <div className="bar-label">{label}</div>
      <div className="bar-track">
        <div className={`bar-fill ${variant}`} style={{ width: `${pct}%` }} />
      </div>
      <div className="bar-val">{valueText}</div>
    </div>
  );
}
