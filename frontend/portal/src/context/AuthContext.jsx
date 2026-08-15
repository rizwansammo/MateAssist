import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { api, onSessionExpired, setAccessToken } from "../lib/api.js";

const AuthContext = createContext(null);

/**
 * Session state.
 *
 * On mount it attempts a refresh. The access token is memory-only, so a page
 * reload always starts with none - but the httpOnly refresh cookie survives,
 * which is what makes "still signed in after F5" work without ever exposing a
 * long-lived credential to JavaScript.
 */
export function AuthProvider({ children }) {
  const [session, setSession] = useState(null);
  const [status, setStatus] = useState("restoring"); // restoring | anonymous | authenticated

  useEffect(() => {
    let cancelled = false;

    api
      .restoreSession()
      .then((restored) => {
        if (cancelled) return;
        setSession(restored);
        setStatus("authenticated");
      })
      .catch(() => {
        if (cancelled) return;
        setStatus("anonymous");
      });

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(
    () =>
      onSessionExpired(() => {
        setSession(null);
        setStatus("anonymous");
      }),
    []
  );

  const login = useCallback(async (email, password) => {
    const next = await api.login(email, password);
    setAccessToken(next.access);
    setSession(next);
    setStatus("authenticated");
    return next;
  }, []);

  const logout = useCallback(async () => {
    try {
      await api.logout();
    } finally {
      setAccessToken(null);
      setSession(null);
      setStatus("anonymous");
    }
  }, []);

  // Re-read the session after the user edits their own profile. The header
  // renders the name, initials and email from this object, so without it a
  // rename appears not to have worked until the next full page load.
  const refresh = useCallback(async () => {
    try {
      setSession(await api.me());
    } catch {
      // A failed refresh must not sign anyone out. The save that triggered it
      // already succeeded; a stale header is a much smaller problem than
      // dropping someone's session because a follow-up request failed.
    }
  }, []);

  const value = useMemo(
    () => ({
      session,
      status,
      user: session?.user ?? null,
      tenant: session?.tenant ?? null,
      role: session?.role ?? null,
      isAuthenticated: status === "authenticated",
      login,
      logout,
      refresh
    }),
    [session, status, login, logout, refresh]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside <AuthProvider>");
  return context;
}
