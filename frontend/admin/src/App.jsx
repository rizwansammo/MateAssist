import { Navigate, Route, Routes } from "react-router-dom";

import AdminLayout from "./layouts/AdminLayout.jsx";
import OverviewPage from "./pages/OverviewPage.jsx";
import TenantsPage from "./pages/TenantsPage.jsx";
import AiConfigurationPage from "./pages/AiConfigurationPage.jsx";
import BillingPage from "./pages/BillingPage.jsx";
import LogsPage from "./pages/LogsPage.jsx";

/**
 * Central Super Admin Panel routes.
 *
 * This bundle is served only on admin.mateassist.io and never on a tenant
 * subdomain (D-145). Phase 2 adds a PLATFORM_OWNER guard; there is none yet,
 * because a guard that checks nothing looks like security while providing none.
 */
export default function App() {
  return (
    <Routes>
      <Route path="/" element={<AdminLayout />}>
        <Route index element={<OverviewPage />} />
        <Route path="tenants" element={<TenantsPage />} />
        <Route path="ai" element={<AiConfigurationPage />} />
        <Route path="billing" element={<BillingPage />} />
        <Route path="logs" element={<LogsPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
