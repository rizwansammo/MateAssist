import { Navigate, Route, Routes } from "react-router-dom";

import { RequireAuth } from "./components/RequireAuth.jsx";
import { RequireTenantAdmin } from "./components/RequireTenantAdmin.jsx";
import { AuthProvider } from "./context/AuthContext.jsx";
import PortalLayout from "./layouts/PortalLayout.jsx";
import LoginPage from "./pages/LoginPage.jsx";
import DashboardPage from "./pages/DashboardPage.jsx";
import ChatPage from "./pages/ChatPage.jsx";
import KnowledgeBasePage from "./pages/KnowledgeBasePage.jsx";

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />

        <Route element={<RequireAuth />}>
          <Route path="/app" element={<PortalLayout />}>
            <Route index element={<DashboardPage />} />
            <Route path="chat" element={<ChatPage />} />
            {/* D-142: the open thread lives in the URL, so a refresh or a back
                button returns to it instead of silently starting a new one. */}
            <Route path="chat/:conversationId" element={<ChatPage />} />
            {/* A-008 retired internal ticketing. Anyone with an old bookmark
                lands on the assistant rather than a 404. */}
            <Route path="tickets" element={<Navigate to="/app/chat" replace />} />
            {/* Administrator-only (D-140). The API refuses an end user
                regardless; this keeps them from landing on a broken page. */}
            <Route path="knowledge" element={<RequireTenantAdmin />}>
              <Route index element={<KnowledgeBasePage />} />
            </Route>
          </Route>
        </Route>

        <Route path="/" element={<Navigate to="/app" replace />} />
        <Route path="*" element={<Navigate to="/app" replace />} />
      </Routes>
    </AuthProvider>
  );
}
