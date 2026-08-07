import { Pill } from "@mateassist/ui";

/**
 * Ticket status chip. Portal-local: it maps a helpdesk domain concept onto the
 * shared Pill vocabulary, and the admin bundle has no tickets. Only genuinely
 * shared primitives belong in packages/ui.
 */
const STATUS_TONE = {
  Open: "info",
  Pending: "warn",
  Resolved: "ok"
};

export function StatusBadge({ status }) {
  return <Pill tone={STATUS_TONE[status] ?? "off"}>{status}</Pill>;
}
