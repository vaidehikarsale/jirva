// Shared header used by every page except Dashboard (which keeps its own
// distinct "hero" treatment as the landing page). Styles live in index.css
// under "Shared page header" since every consumer needs the exact same
// look - a page-local CSS override here would just reintroduce the drift
// this component exists to remove.
export default function PageHeader({ icon: Icon, title, description, action }) {
  return (
    <div className="page-header">
      {Icon && <div className="page-header-icon"><Icon width={20} height={20} /></div>}
      <div className="page-header-text">
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      {action && <div className="page-header-action">{action}</div>}
    </div>
  );
}
