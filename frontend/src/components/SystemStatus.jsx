import { useEffect, useState } from "react";
import { getHealth } from "../api";

const POLL_INTERVAL_MS = 30000;

// Sidebar footer indicator - the backend is a real dependency that can
// genuinely go down (the models/index take a while to load on startup, and
// upstream LLM calls can fail), so "is JIRVA actually reachable right now"
// is worth surfacing rather than leaving that dead space in the sidebar.
export default function SystemStatus() {
  const [online, setOnline] = useState(null);

  useEffect(() => {
    let cancelled = false;

    function check() {
      getHealth().then((ok) => {
        if (!cancelled) setOnline(ok);
      });
    }

    check();
    const interval = setInterval(check, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  const label = online === null ? "Checking..." : online ? "API Connected" : "API Offline";
  const dotClass = online === null ? "status-dot-pending" : online ? "status-dot-online" : "status-dot-offline";

  return (
    <div className="system-status">
      <span className={`status-dot ${dotClass}`} />
      <span>{label}</span>
    </div>
  );
}
