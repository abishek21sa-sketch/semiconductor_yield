export default function ScenarioNav({ scenarios, activeKey, onSelect, description }) {
  return (
    <>
      <nav id="scenarios">
        <span className="nav-label">Quick scenario:</span>
        {scenarios.map((s) => (
          <button key={s.key} className={s.key === activeKey ? "active" : ""} onClick={() => onSelect(s.key)}>
            {s.label}
          </button>
        ))}
      </nav>
      <div id="scenario-desc">{description}</div>
    </>
  );
}
