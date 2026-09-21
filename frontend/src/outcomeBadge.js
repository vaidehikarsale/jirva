// Single source of truth for how an outcome maps to badge text/color.
// Used by TicketResult.jsx and TicketsList.jsx so the two views can't
// silently drift into showing different colors for the same outcome.
export function getOutcomeBadge(outcome) {
  switch (outcome) {
    case "RESOLVE":
      return { text: "RESOLVE", badgeClass: "badge-success" };
    case "GUIDE":
      return { text: "GUIDE", badgeClass: "badge-info" };
    case "ESCALATE":
      return { text: "ESCALATED", badgeClass: "badge-danger" };
    case "FALLBACK":
      return { text: "INSUFFICIENT EVIDENCE", badgeClass: "badge-warning" };
    case "OUT_OF_DOMAIN":
      return { text: "OUT OF DOMAIN", badgeClass: "badge-neutral" };
    default:
      return { text: outcome || "UNKNOWN", badgeClass: "badge-neutral" };
  }
}
