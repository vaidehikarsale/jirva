import {
  ListIcon, CheckCircleIcon, CompassIcon, AlertTriangleIcon,
  HelpCircleIcon, GlobeIcon,
} from "./icons";

// Single source of truth for which outcomes get a stat card, in what
// order, with what label/icon - shared by Dashboard and TicketsList so the
// two pages can't drift into showing different cards for the same data.
export const OUTCOME_STAT_DEFS = [
  { key: "total", label: "Total Queries", outcome: null, icon: ListIcon },
  { key: "RESOLVE", label: "Resolved", outcome: "RESOLVE", icon: CheckCircleIcon },
  { key: "GUIDE", label: "Guided", outcome: "GUIDE", icon: CompassIcon },
  { key: "ESCALATE", label: "Escalated", outcome: "ESCALATE", icon: AlertTriangleIcon },
  { key: "FALLBACK", label: "Insufficient Evidence", outcome: "FALLBACK", icon: HelpCircleIcon },
  { key: "OUT_OF_DOMAIN", label: "Out of Domain", outcome: "OUT_OF_DOMAIN", icon: GlobeIcon },
];
