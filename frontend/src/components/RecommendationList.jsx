export default function RecommendationList({ lines }) {
  return (
    <div className="card wide">
      <h2>Explainable Recommendation</h2>
      <div className="card-sub">Each line is tagged with its evidence source</div>
      <ul className="rec-list">
        {lines.map((l, i) => {
          const m = l.match(/^\[([^\]]+)\]\s*(.*)$/);
          return <li key={i}>{m ? (<><span className="tag">[{m[1]}]</span> {m[2]}</>) : l}</li>;
        })}
      </ul>
    </div>
  );
}
