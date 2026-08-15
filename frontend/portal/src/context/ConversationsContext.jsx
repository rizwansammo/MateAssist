import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { chatApi } from "../lib/chat.js";

/**
 * The conversation list, shared between the sidebar and the chat page (D-164).
 *
 * It used to live inside ChatPage, which is why the product had two sidebars:
 * the navigation could not show recents because it had no access to them, so
 * the chat page grew a second column of its own. Every other chat product puts
 * both in one rail, and the split made MateAssist look like two apps stitched
 * together.
 *
 * Lifting the list here rather than passing it upward keeps the ownership
 * honest: the sidebar renders it, the chat page mutates it, and neither has to
 * know the other exists.
 */

const ConversationsContext = createContext(null);

export function ConversationsProvider({ children }) {
  const [threads, setThreads] = useState([]);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const rows = await chatApi.listConversations();
      setThreads(Array.isArray(rows) ? rows : (rows?.results ?? []));
    } catch {
      // A failed list must not break the page around it. The chat itself still
      // works with no history, and an empty rail is a smaller problem than a
      // crashed layout.
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Removes locally first. The row is gone from the server by the time this is
  // called, and waiting for a refetch leaves a deleted thread on screen.
  const drop = useCallback((id) => {
    setThreads((prev) => prev.filter((thread) => thread.id !== id));
  }, []);

  const value = useMemo(
    () => ({ threads, loading, refresh, drop }),
    [threads, loading, refresh, drop]
  );

  return <ConversationsContext.Provider value={value}>{children}</ConversationsContext.Provider>;
}

export function useConversations() {
  const context = useContext(ConversationsContext);
  if (!context) {
    throw new Error("useConversations must be used inside a ConversationsProvider");
  }
  return context;
}
