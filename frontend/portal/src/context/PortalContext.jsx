import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { chatApi } from "../lib/chat.js";

/**
 * Portal-wide state seam.
 *
 * Was the ticket list. A-008 retired internal ticketing in favour of an email
 * handoff to whatever helpdesk the workspace already runs, so there is no ticket
 * table to read and inventing one in the UI would be a fabricated fact.
 *
 * What replaced it is the thing the product actually keeps: the user's own
 * conversations, each of which is either still open, escalated to a human, or
 * resolved by the assistant.
 */
const PortalContext = createContext(null);

export function PortalProvider({ children }) {
  const [conversations, setConversations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [toast, setToast] = useState(null);

  const notify = useCallback((title, body, tone = "ok") => {
    setToast({ title, body, tone });
  }, []);

  const dismissToast = useCallback(() => setToast(null), []);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const payload = await chatApi.listConversations();
      setConversations(Array.isArray(payload) ? payload : (payload?.results ?? []));
    } catch (cause) {
      setError(cause);
      setConversations([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  /**
   * A conversation is escalated, resolved, or still open - derived from the two
   * fields the backend actually sets, not from a status column that would need
   * to be kept in sync.
   */
  const counts = useMemo(
    () => ({
      all: conversations.length,
      escalated: conversations.filter((c) => c.escalated_at).length,
      resolved: conversations.filter((c) => c.resolved).length,
      open: conversations.filter((c) => !c.escalated_at && !c.resolved).length
    }),
    [conversations]
  );

  const value = useMemo(
    () => ({ conversations, counts, loading, error, refresh, toast, notify, dismissToast }),
    [conversations, counts, loading, error, refresh, toast, notify, dismissToast]
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
