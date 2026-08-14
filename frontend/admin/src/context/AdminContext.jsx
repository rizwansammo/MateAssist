import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { platformApi } from "../lib/platform.js";
import { vaultApi } from "../lib/vault.js";

/**
 * Platform-wide state seam.
 *
 * Every figure here now comes from the API. The tenant list is the workspace
 * registry with real membership and document counts annotated server-side
 * (Phase 7B); suspension writes through the platform surface and is audited.
 */
const AdminContext = createContext(null);

const EMPTY_POOL = { total: 0, pool: 0, active: 0, rate_limited: 0, usable: false };

export function AdminProvider({ children }) {
  const [tenants, setTenants] = useState([]);
  const [tenantsLoading, setTenantsLoading] = useState(true);
  const [tenantsError, setTenantsError] = useState(null);
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

  const refreshTenants = useCallback(async () => {
    setTenantsLoading(true);
    setTenantsError(null);
    try {
      const payload = await platformApi.tenants();
      // DRF pagination is on by default (PAGE_SIZE 25), so the list arrives
      // under `results`. Tolerating both shapes keeps this working if the
      // endpoint is ever made unpaginated.
      setTenants(Array.isArray(payload) ? payload : (payload?.results ?? []));
    } catch (cause) {
      setTenantsError(cause);
      setTenants([]);
    } finally {
      setTenantsLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshPools();
    refreshTenants();
  }, [refreshPools, refreshTenants]);

  const tenantStats = useMemo(
    () => ({
      total: tenants.length,
      active: tenants.filter((t) => t.status === "ACTIVE").length,
      suspended: tenants.filter((t) => t.status === "SUSPENDED").length,
      seats: tenants.reduce((sum, t) => sum + (t.users ?? 0), 0),
      documents: tenants.reduce((sum, t) => sum + (t.documents ?? 0), 0)
    }),
    [tenants]
  );

  const toggleTenant = useCallback(
    async (tenant) => {
      const wasActive = tenant.status === "ACTIVE";
      try {
        const updated = wasActive
          ? await platformApi.suspendTenant(tenant.id)
          : await platformApi.activateTenant(tenant.id);

        // Replace with what the server returned rather than the optimistic
        // guess: the row now reflects committed state, so a failed write can
        // never leave the table showing a suspension that did not happen.
        setTenants((prev) => prev.map((t) => (t.id === updated.id ? updated : t)));

        if (wasActive) {
          notify("Tenant suspended", `${tenant.name} - sign-in blocked, AI routing paused`, "warn");
        } else {
          notify("Tenant reactivated", `${tenant.name} - ${tenant.users} seats restored`);
        }
      } catch (cause) {
        notify("Could not update tenant", cause?.message ?? "The change was not saved.", "warn");
      }
    },
    [notify]
  );

  const value = useMemo(
    () => ({
      tenants,
      tenantsLoading,
      tenantsError,
      refreshTenants,
      tenantStats,
      toggleTenant,
      pools,
      refreshPools,
      toast,
      notify,
      dismissToast
    }),
    [
      tenants,
      tenantsLoading,
      tenantsError,
      refreshTenants,
      tenantStats,
      toggleTenant,
      pools,
      refreshPools,
      toast,
      notify,
      dismissToast
    ]
  );

  return <AdminContext.Provider value={value}>{children}</AdminContext.Provider>;
}

export function useAdmin() {
  const context = useContext(AdminContext);
  if (!context) throw new Error("useAdmin must be used inside <AdminProvider>");
  return context;
}
