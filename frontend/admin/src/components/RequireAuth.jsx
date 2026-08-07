import { Navigate, Outlet, useLocation } from "react-router-dom";

import { useAuth } from "../context/AuthContext.jsx";

/**
 * Route guard.
 *
 * A convenience, not a security boundary - the server authorises every request
 * independently and re-resolves the tenant from the Host header. Removing this
 * component would make the UI ugly, not insecure.
 *
 * The `restoring` state matters: without it a page refresh would flash the
 * login screen for the moment the refresh call is in flight, and any redirect
 * decided during that window would be wrong.
 */
export function RequireAuth() {
  const { status } = useAuth();
  const location = useLocation();

  if (status === "restoring") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-100">
        <div className="flex items-center gap-3 rounded-none border border-hairline bg-white px-5 py-4">
          <span className="h-1.5 w-1.5 animate-pulse rounded-none bg-emerald-500" />
          <span className="text-[13.5px] text-slate-600">Restoring your session...</span>
        </div>
      </div>
    );
  }

  if (status !== "authenticated") {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }

  return <Outlet />;
}
