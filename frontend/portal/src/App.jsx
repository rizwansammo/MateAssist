import { Navigate, Route, Routes } from "react-router-dom";

import { RequireAuth } from "./components/RequireAuth.jsx";
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
            {/* A-008 retired internal ticketing. Anyone with an old bookmark
                lands on the assistant rather than a 404. */}
            <Route path="tickets" element={<Navigate to="/app/chat" replace />} />
            <Route path="knowledge" element={<KnowledgeBasePage />} />
          </Route>
        </Route>

        <Route path="/" element={<Navigate to="/app" replace />} />
        <Route path="*" element={<Navigate to="/app" replace />} />
      </Routes>
    </AuthProvider>
  );
}
