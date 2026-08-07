import { Navigate, Route, Routes } from "react-router-dom";

import PortalLayout from "./layouts/PortalLayout.jsx";
import LoginPage from "./pages/LoginPage.jsx";
import DashboardPage from "./pages/DashboardPage.jsx";
import ChatPage from "./pages/ChatPage.jsx";
import TicketsPage from "./pages/TicketsPage.jsx";
import KnowledgeBasePage from "./pages/KnowledgeBasePage.jsx";

/**
 * Route table for the End-User Portal.
 *
 * The prototype switched views with a `currentView` string in component state;
 * these are real routes, so the browser back button, deep links and per-route
 * code splitting all work.
 *
 * There is no auth guard yet. Phase 2 adds a <RequireAuth> wrapper around the
 * /app branch once JWT issuance exists (D-030..D-036). Adding a guard now that
 * checks nothing would look like security while providing none.
 */
export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />

      <Route path="/app" element={<PortalLayout />}>
        <Route index element={<DashboardPage />} />
        <Route path="chat" element={<ChatPage />} />
        <Route path="tickets" element={<TicketsPage />} />
        <Route path="knowledge" element={<KnowledgeBasePage />} />
      </Route>

      <Route path="/" element={<Navigate to="/login" replace />} />
      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  );
}
