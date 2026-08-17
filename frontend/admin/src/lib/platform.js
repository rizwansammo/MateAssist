import { apiFetch } from "./api.js";

/**
 * Platform reporting client (Phase 7).
 *
 * Every call here reads across tenants on the server's RLS-bypassing connection
 * and is gated by IsPlatformOwner. A 403 from any of these is the backend
 * working correctly, not a bug to route around.
 */
export const platformApi = {
  usage: (days, signal) => apiFetch(`/platform/usage/${days ? `?days=${days}` : ""}`, { signal }),
  spend: (days, signal) => apiFetch(`/platform/spend/${days ? `?days=${days}` : ""}`, { signal }),

  logs: ({ level, tenant, action, limit = 100, offset = 0 } = {}, signal) => {
    const query = new URLSearchParams({ limit: String(limit), offset: String(offset) });
    if (level && level !== "all") query.set("level", level);
    if (tenant) query.set("tenant", String(tenant));
    if (action) query.set("action", action);
    return apiFetch(`/platform/logs/?${query}`, { signal });
  },

  tenants: (signal) => apiFetch("/platform/tenants/", { signal }),
  suspendTenant: (id) => apiFetch(`/platform/tenants/${id}/suspend/`, { method: "POST" }),
  activateTenant: (id) => apiFetch(`/platform/tenants/${id}/activate/`, { method: "POST" }),

  budgets: () => apiFetch("/platform/budgets/"),
  budgetStatus: (id) => apiFetch(`/platform/budgets/${id}/status/`),
  // ---- platform mail (D-175) ----
  //
  // MateAssist's OWN mail, not a workspace's. This carries password reset
  // codes, so it must never route through a customer's SMTP server.
  mailSettings: (signal) => apiFetch("/platform/mail/", { signal }),

  /**
   * `smtp_password` is sent only when the operator typed one. An empty string
   * clears the stored credential, so passing it unconditionally would wipe a
   * working password every time the From address was edited.
   */
  saveMailSettings: (fields) =>
    apiFetch("/platform/mail/", { method: "PATCH", body: fields }),

  sendMailTest: (to) =>
    apiFetch("/platform/mail-test/", { method: "POST", body: to ? { to } : {} }),

  /** Create a workspace and its first administrator in one call (D-173). */
  createTenant: (payload) => apiFetch("/platform/tenants/", { method: "POST", body: payload }),

  /** Returns the new password once. Nothing can show it again. */
  resetTenantOwnerPassword: (id, newPassword) =>
    apiFetch(`/platform/tenants/${id}/reset-owner-password/`, {
      method: "POST",
      body: newPassword ? { new_password: newPassword } : {}
    }),

  saveBudget: ({ id, tenant, monthly_tokens, enforce, alert_at_percent = 80 }) =>
    id
      ? apiFetch(`/platform/budgets/${id}/`, {
          method: "PATCH",
          body: { monthly_tokens, enforce, alert_at_percent }
        })
      : apiFetch("/platform/budgets/", {
          method: "POST",
          body: { tenant, monthly_tokens, enforce, alert_at_percent }
        })
};

/** Money, from a decimal string the server sent. Never computed in the UI. */
export function money(value, { decimals = 2 } = {}) {
  const amount = Number(value ?? 0);
  return `$${amount.toFixed(decimals)}`;
}

/** 1_234_567 -> "1.2M". Compact enough for a table cell without losing scale. */
export function compact(value) {
  const n = Number(value ?? 0);
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

export function percent(value, { decimals = 0 } = {}) {
  return `${(Number(value ?? 0) * 100).toFixed(decimals)}%`;
}

/**
 * Width for a bar, as a share of the largest row.
 *
 * Relative rather than absolute: with real data the top tenant is often an
 * order of magnitude above the rest, and scaling to a fixed ceiling would render
 * every bar as an invisible sliver.
 */
export function share(value, max) {
  const ceiling = Number(max ?? 0);
  if (!ceiling) return "0%";
  return `${Math.max(2, Math.round((Number(value ?? 0) / ceiling) * 100))}%`;
}
