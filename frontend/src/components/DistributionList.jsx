// Shared horizontal bar breakdown - used by the Evaluation page's live
// stats section and Dashboard's Category Breakdown panel. Styles live in
// index.css under "Shared distribution list".
export default function DistributionList({ title, distribution }) {
  const entries = Object.entries(distribution).sort((a, b) => b[1] - a[1]);
  const total = entries.reduce((sum, [, v]) => sum + v, 0);
  return (
    <div className="distribution-block">
      {title && <h3>{title}</h3>}
      {entries.length === 0 && <p className="distribution-empty">No data yet.</p>}
      {entries.map(([label, count]) => (
        <div key={label} className="distribution-row">
          <span className="distribution-row-label">{label}</span>
          <div className="distribution-bar-track">
            <div
              className="distribution-bar-fill"
              style={{ width: total ? `${(count / total) * 100}%` : "0%" }}
            />
          </div>
          <span className="distribution-row-value">{count}</span>
        </div>
      ))}
    </div>
  );
}
