import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { vaultApi } from "../lib/vault.js";
import { SEED_TENANTS } from "../seed/platform.js";

/**
 * Platform-wide state seam.
 *
 * Key-pool health is live (Phase 4). Tenants are still seeded until the Phase 2
 * tenancy API grows a platform-admin listing endpoint.
 */
const AdminContext = createContext(null);

const EMPTY_POOL = { total: 0, pool: 0, active: 0, rate_limited: 0, usable: false };

export function AdminProvider({ children }) {
  const [tenants, setTenants] = useState(SEED_TENANTS);
  const [pools, setPools] = useState({ TEXT: EMPTY_POOL, VISION: EMPTY_POOL });
  const [toast, setToast] = useState(null);

  const notify = useCallback((title, body, tone = "ok") => setToast({ title, body, tone }), []);
  const dismissToast = useCallback(() => setToast(null), []);

  const refreshPools = useCallback(async () => {
    try {
      const status = await vaultApi.poolStatus();
      setPools({ TEXT: status.TEXT ?? EMPTY_POOL, VISION: status.VISION ?? EMPTY_POOL });
    } catch {
      // The sidebar badge is informational; a failed poll must not surface as an
      // error toast on every page load.
      setPools({ TEXT: EMPTY_POOL, VISION: EMPTY_POOL });
    }
  }, []);

  useEffect(() => {
    refreshPools();
  }, [refreshPools]);

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

  const toggleTenant = useCallback(
    (tenant) => {
      const wasActive = tenant.status === "Active";
      setTenants((prev) =>
        prev.map((t) =>
          t.slug === tenant.slug ? { ...t, status: wasActive ? "Suspended" : "Active" } : t
        )
      );
      if (wasActive) {
        notify("Tenant suspended", `${tenant.name} - sign-in blocked, AI routing paused`, "warn");
      } else {
        notify("Tenant reactivated", `${tenant.name} - ${tenant.users} seats restored`);
      }
    },
    [notify]
  );

  const value = useMemo(
    () => ({
      tenants,
      tenantStats,
      toggleTenant,
      pools,
      refreshPools,
      toast,
      notify,
      dismissToast
    }),
    [tenants, tenantStats, toggleTenant, pools, refreshPools, toast, notify, dismissToast]
  );

  return <AdminContext.Provider value={value}>{children}</AdminContext.Provider>;
}

export function useAdmin() {
  const context = useContext(AdminContext);
  if (!context) throw new Error("useAdmin must be used inside <AdminProvider>");
  return context;
}
