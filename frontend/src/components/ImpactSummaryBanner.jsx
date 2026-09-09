export default function ImpactSummaryBanner({ summary }) {
  if (!summary || summary.status !== "optimal" || !summary.narrative) return null;
  return (
    <section className="impact-banner">
      <div className="impact-banner-label">Decision Intelligence Summary</div>
      <p className="impact-banner-text">{summary.narrative}</p>
    </section>
  );
}
