import { createContext, useCallback, useContext, useMemo, useState } from "react";

import { SEED_KEYS } from "../seed/engines.js";
import { SEED_TENANTS } from "../seed/platform.js";

/**
 * Platform-wide state seam.
 *
 * Phase 2 swaps tenants for the tenancy API and Phase 4 swaps keys for the
 * credential vault, without changing the shape this hook exposes.
 */
const AdminContext = createContext(null);

export function AdminProvider({ children }) {
  const [tenants, setTenants] = useState(SEED_TENANTS);
  const [keys, setKeys] = useState(SEED_KEYS);
  const [toast, setToast] = useState(null);

  const notify = useCallback((title, body, tone = "ok") => setToast({ title, body, tone }), []);
  const dismissToast = useCallback(() => setToast(null), []);

  const tenantStats = useMemo(
    () => ({
      total: tenants.length,
      active: tenants.filter((t) => t.status === "Active").length,
      suspended: tenants.filter((t) => t.status === "Suspended").length,
      seats: tenants.reduce((sum, t) => sum + t.users, 0),
      documents: tenants.reduce((sum, t) => sum + t.documents, 0)
    }),
    [tenants]
  );

  const keyStats = useCallback(
    (engineId) => {
      const pool = keys[engineId] ?? [];
      const live = pool.filter((k) => k.status !== "Revoked");
      return {
        active: pool.filter((k) => k.status === "Active").length,
        pool: live.length,
        limited: pool.filter((k) => k.status === "Rate-limited").length
      };
    },
    [keys]
  );

  const toggleTenant = useCallback(
    (tenant) => {
      const wasActive = tenant.status === "Active";
      setTenants((prev) =>
        prev.map((t) =>
          t.slug === tenant.slug ? { ...t, status: wasActive ? "Suspended" : "Active" } : t
        )
      );
      // D-035: suspension blocks sign-in AND pauses AI routing immediately.
      if (wasActive) {
        notify("Tenant suspended", `${tenant.name} - sign-in blocked, AI routing paused`, "warn");
      } else {
        notify("Tenant reactivated", `${tenant.name} - ${tenant.users} seats restored`);
      }
    },
    [notify]
  );

  /**
   * Phase 4 replaces this with POST/PATCH against the vault.
   *
   * Note what is stored even here: only the last four characters. The plaintext
   * secret is never held in component state, never echoed back, and has no read
   * path (D-072). Write-only is the absence of a code path, not a flag.
   */
  const saveKey = useCallback(
    ({ engineId, keyId, label, secret, quota }) => {
      const last4 = secret.slice(-4);
      setKeys((prev) => {
        const pool = prev[engineId] ?? [];
        if (keyId) {
          return {
            ...prev,
            [engineId]: pool.map((k) =>
              k.id === keyId
                ? { ...k, label, last4, quota, status: "Active", requests: "0", lastUsed: "just now" }
                : k
            )
          };
        }
        return {
          ...prev,
          [engineId]: pool.concat([
            {
              id: `${engineId}-${pool.length + 1}`,
              label,
              last4,
              quota,
              status: "Active",
              requests: "0",
              lastUsed: "just now",
              added: "7 Aug 2026"
            }
          ])
        };
      });
      notify(
        keyId ? "Key rotated" : "Key added",
        `${label} is live - audit event written`
      );
    },
    [notify]
  );

  const revokeKey = useCallback(
    (engineId, key) => {
      setKeys((prev) => {
        const pool = prev[engineId] ?? [];
        if (key.status === "Revoked") {
          return { ...prev, [engineId]: pool.filter((k) => k.id !== key.id) };
        }
        return {
          ...prev,
          [engineId]: pool.map((k) =>
            k.id === key.id ? { ...k, status: "Revoked", requests: "0" } : k
          )
        };
      });
      notify(
        key.status === "Revoked" ? "Key purged" : "Key revoked",
        `${key.label} - traffic rebalanced, audit event written`,
        "warn"
      );
    },
    [notify]
  );

  const value = useMemo(
    () => ({
      tenants,
      tenantStats,
      toggleTenant,
      keys,
      keyStats,
      saveKey,
      revokeKey,
      toast,
      notify,
      dismissToast
    }),
    [tenants, tenantStats, toggleTenant, keys, keyStats, saveKey, revokeKey, toast, notify, dismissToast]
  );

  return <AdminContext.Provider value={value}>{children}</AdminContext.Provider>;
}

export function useAdmin() {
  const context = useContext(AdminContext);
  if (!context) throw new Error("useAdmin must be used inside <AdminProvider>");
  return context;
}
