import { useCountUp } from "../hooks/useCountUp";

// Shared by Dashboard's metric row and TicketsList's summary row - one
// definition so a stat card looks identical wherever it appears. Styles
// live in index.css under "Shared stat card".
export default function StatCard({ icon: Icon, label, count, onClick, active }) {
  const animated = useCountUp(count);
  return (
    <button className={`stat-card${active ? " active" : ""}`} onClick={onClick}>
      <div className="stat-card-icon"><Icon width={18} height={18} /></div>
      <span className="stat-card-count">{animated}</span>
      <span className="stat-card-label">{label}</span>
    </button>
  );
}
