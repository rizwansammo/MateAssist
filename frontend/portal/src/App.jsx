import { Navigate, Route, Routes } from "react-router-dom";

import { RequireAuth } from "./components/RequireAuth.jsx";
import { AuthProvider } from "./context/AuthContext.jsx";
import PortalLayout from "./layouts/PortalLayout.jsx";
import LoginPage from "./pages/LoginPage.jsx";
import DashboardPage from "./pages/DashboardPage.jsx";
import ChatPage from "./pages/ChatPage.jsx";
import TicketsPage from "./pages/TicketsPage.jsx";
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
            <Route path="tickets" element={<TicketsPage />} />
            <Route path="knowledge" element={<KnowledgeBasePage />} />
          </Route>
        </Route>

        <Route path="/" element={<Navigate to="/app" replace />} />
        <Route path="*" element={<Navigate to="/app" replace />} />
      </Routes>
    </AuthProvider>
  );
}
