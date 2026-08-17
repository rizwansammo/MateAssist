import { Navigate, Route, Routes } from "react-router-dom";

import { RequireAuth } from "./components/RequireAuth.jsx";
import { AuthProvider } from "./context/AuthContext.jsx";
import AdminLayout from "./layouts/AdminLayout.jsx";
import LoginPage from "./pages/LoginPage.jsx";
import OverviewPage from "./pages/OverviewPage.jsx";
import TenantsPage from "./pages/TenantsPage.jsx";
import AiConfigurationPage from "./pages/AiConfigurationPage.jsx";
import BillingPage from "./pages/BillingPage.jsx";
import PlatformMailPage from "./pages/PlatformMailPage.jsx";
import LogsPage from "./pages/LogsPage.jsx";

/**
 * Central Super Admin Panel.
 *
 * Served only on admin.mateassist.io, never on a tenant subdomain (D-145).
 * That host carries no tenant, so the API admits only PLATFORM_OWNER here.
 */
export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />

        <Route element={<RequireAuth />}>
          <Route path="/" element={<AdminLayout />}>
            <Route index element={<OverviewPage />} />
            <Route path="tenants" element={<TenantsPage />} />
            <Route path="ai" element={<AiConfigurationPage />} />
            <Route path="billing" element={<BillingPage />} />
            <Route path="mail" element={<PlatformMailPage />} />
            <Route path="logs" element={<LogsPage />} />
          </Route>
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AuthProvider>
  );
}
