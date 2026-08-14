import { Navigate, Outlet } from "react-router-dom";

import { useAuth } from "../context/AuthContext.jsx";

/**
 * Route guard for the runbook surface (D-140).
 *
 * A convenience, not a security boundary. The API refuses an end user
 * independently - `IsTenantAdmin` no longer exempts GET, so the document list,
 * its chunks and its figure descriptions all return 403 whatever the browser
 * does. This exists so an end user who follows an old link lands on the
 * assistant rather than on a page of failed requests.
 */
export function RequireTenantAdmin() {
  const { role } = useAuth();

  if (role !== "TENANT_ADMIN") {
    return <Navigate to="/app/chat" replace />;
  }

  return <Outlet />;
}
