import { createContext, useCallback, useContext, useMemo, useState } from "react";

import { SEED_TICKETS } from "../seed/tickets.js";

/**
 * Portal-wide state seam.
 *
 * Dashboard, My Tickets and AI Support all read the same ticket list, so it
 * lives above them rather than being duplicated per page. Today it is seeded
 * (see seed/README.md); in Phase 3 the internals become TanStack Query calls
 * against the helpdesk API while this hook's shape stays the same - so the
 * pages consuming it do not change.
 */
const PortalContext = createContext(null);

export function PortalProvider({ children }) {
  const [tickets, setTickets] = useState(SEED_TICKETS);
  const [toast, setToast] = useState(null);

  const notify = useCallback((title, body, tone = "ok") => {
    setToast({ title, body, tone });
  }, []);

  const dismissToast = useCallback(() => setToast(null), []);

  const counts = useMemo(
    () => ({
      All: tickets.length,
      Open: tickets.filter((t) => t.status === "Open").length,
      Pending: tickets.filter((t) => t.status === "Pending").length,
      Resolved: tickets.filter((t) => t.status === "Resolved").length
    }),
    [tickets]
  );

  /**
   * Phase 3 replaces this with POST /api/v1/tickets/. The ticket number is
   * assigned by a database sequence there, never client-side (D-120).
   */
  const createTicket = useCallback(
    (draft) => {
      const ticket = {
        id: "IT-10943",
        subject: draft?.subject ?? "Microsoft 365 password reset blocked by MFA change",
        meta: draft?.meta ?? "Opened by MateAssist from chat - Priority High",
        category: draft?.category ?? "Access",
        status: "Open",
        date: "5 Aug 2026"
      };
      setTickets((prev) => [ticket, ...prev]);
      notify(
        `Ticket ${ticket.id} created successfully`,
        "Assigned to Daniel Koch - Identity & Access - SLA 4 hours"
      );
      return ticket;
    },
    [notify]
  );

  const value = useMemo(
    () => ({ tickets, counts, createTicket, toast, notify, dismissToast }),
    [tickets, counts, createTicket, toast, notify, dismissToast]
  );

  return <PortalContext.Provider value={value}>{children}</PortalContext.Provider>;
}

export function usePortal() {
  const context = useContext(PortalContext);
  if (!context) {
    throw new Error("usePortal must be used inside <PortalProvider>");
  }
  return context;
}
