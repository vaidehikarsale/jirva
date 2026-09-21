import { NavLink } from "react-router-dom";
import { GridIcon, PlusCircleIcon, ListIcon, BookIcon, BarChartIcon, TerminalIcon } from "../icons";
import "./Sidebar.css";

const NAV_PRIMARY = [
  { to: "/", label: "Dashboard", icon: GridIcon, end: true },
  { to: "/raise", label: "Raise Ticket", icon: PlusCircleIcon },
  { to: "/tickets", label: "Tickets", icon: ListIcon },
];

const NAV_SECONDARY = [
  { to: "/knowledge-base", label: "Knowledge Base", icon: BookIcon },
  { to: "/evaluation", label: "Evaluation", icon: BarChartIcon },
  { to: "/system-logs", label: "System Logs", icon: TerminalIcon },
];

function NavGroup({ items }) {
  return (
    <>
      {items.map(({ to, label, icon: Icon, end }) => (
        <NavLink
          key={to}
          to={to}
          end={end}
          className={({ isActive }) => "sidebar-link" + (isActive ? " active" : "")}
        >
          <Icon width={17} height={17} className="sidebar-link-icon" />
          <span>{label}</span>
        </NavLink>
      ))}
    </>
  );
}

export default function Sidebar() {
  return (
    <aside className="sidebar">
      <div className="sidebar-logo">
        <span className="logo-text">JIRVA</span>
      </div>

      <nav className="sidebar-nav">
        <NavGroup items={NAV_PRIMARY} />
        <div className="sidebar-divider" />
        <NavGroup items={NAV_SECONDARY} />
      </nav>

      <div className="sidebar-footer">JIRVA prototype - v0.1</div>
    </aside>
  );
}
