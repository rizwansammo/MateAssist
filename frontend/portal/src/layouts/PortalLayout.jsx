import { useEffect, useState } from "react";
import {
  Bot,
  BookOpen,
  Bell,
  LayoutDashboard,
  MessageSquare,
  Plus,
  Search,
  Settings,
  Trash2,
  Users
} from "lucide-react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { Toast, Wordmark } from "@mateassist/ui";

import { useAuth } from "../context/AuthContext.jsx";
import { ConversationsProvider, useConversations } from "../context/ConversationsContext.jsx";
import { PortalProvider, usePortal } from "../context/PortalContext.jsx";
import { ProfileMenu } from "../components/ProfileMenu.jsx";
import { workspaceHost } from "../lib/domain.js";
import { api } from "../lib/api.js";
import { chatApi } from "../lib/chat.js";

// "My Tickets" is gone with A-008: there is no ticket table, and a nav item
// pointing at invented rows is worse than one fewer link.
//
// Knowledge Base is administrator-only (D-140). Runbooks are written for IT and
// carry admin console paths, service account names and identity-verification
// procedures that stop working once the person being verified has read them. An
// end user reaches that content through the assistant, which is the point of
// the assistant.
const NAV = [
  { to: "/app", end: true, label: "Dashboard", icon: LayoutDashboard, crumb: "Dashboard" },
  { to: "/app/chat", label: "AI Support", icon: Bot, badge: "LIVE", crumb: "AI Support" },
  {
    to: "/app/knowledge",
    label: "Knowledge Base",
    icon: BookOpen,
    crumb: "Knowledge Base",
    adminOnly: true
  },
  {
    to: "/app/people",
    label: "People",
    icon: Users,
    crumb: "People",
    adminOnly: true
  },
  {
    to: "/app/settings",
    label: "Settings",
    icon: Settings,
    crumb: "Workspace settings",
    adminOnly: true
  }
];

const HEALTH_STATE = {
  ok: { label: "All systems operational", dot: "bg-emerald-500", text: "text-emerald-400" },
  degraded: { label: "Degraded performance", dot: "bg-amber-500", text: "text-amber-400" },
  error: { label: "Service disruption", dot: "bg-red-500", text: "text-red-400" },
  unknown: { label: "Status unavailable", dot: "bg-slate-500", text: "text-slate-400" }
};

function Recents() {
  /* The conversation list, in the one sidebar rather than a second column of
     its own (D-164). Dark-surface styling to match the rail it now lives in -
     the light card treatment came from being on a white page. */
  const { threads, loading } = useConversations();
  const navigate = useNavigate();
  const location = useLocation();
  const { drop } = useConversations();

  // Read from the URL rather than props: the layout has no chat state, and the
  // path is the single source of truth for which thread is open.
  const openId = Number(location.pathname.match(/\/app\/chat\/(\d+)/)?.[1]);

  const remove = async (id, event) => {
    event.stopPropagation();
    if (!window.confirm("Delete this conversation? This cannot be undone.")) return;
    try {
      await chatApi.remove(id);
      drop(id);
      if (id === openId) navigate("/app/chat", { replace: true });
    } catch {
      /* the thread stays; the next refresh corrects it */
    }
  };

  if (loading && threads.length === 0) return null;

  return (
    <div className="mt-5 flex min-h-0 flex-1 flex-col">
      <div className="px-5 pb-2.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-600">
        Recents
      </div>

      {threads.length === 0 ? (
        <p className="px-5 text-[12px] leading-relaxed text-slate-600">
          Nothing yet. Ask a question and it will be saved here.
        </p>
      ) : (
        <div className="flex min-h-0 flex-1 flex-col gap-px overflow-y-auto px-3.5">
          {threads.map((thread) => {
            const active = thread.id === openId;
            return (
              <button
                key={thread.id}
                type="button"
                onClick={() => navigate(`/app/chat/${thread.id}`)}
                className={`group flex items-center gap-2.5 rounded-none border-l-2 px-3.5 py-2 text-left transition ${
                  active
                    ? "border-emerald-500 bg-ink2 text-white"
                    : "border-transparent text-slate-400 hover:bg-ink2 hover:text-slate-200"
                }`}
              >
                <MessageSquare size={14} strokeWidth={1.8} className="flex-none opacity-70" />
                <span className="min-w-0 flex-1 truncate text-[13px]">
                  {thread.title || "New conversation"}
                </span>
                {thread.escalated_at && (
                  <span
                    title="Sent to IT"
                    className="h-[6px] w-[6px] flex-none rounded-none bg-emerald-500"
                  />
                )}
                <span
                  role="button"
                  tabIndex={-1}
                  aria-label="Delete conversation"
                  onClick={(event) => remove(thread.id, event)}
                  className="flex-none p-0.5 text-slate-600 opacity-0 transition hover:text-red-400 group-hover:opacity-100"
                >
                  <Trash2 size={13} strokeWidth={1.8} />
                </span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

function Sidebar({ tenant, isAdmin, user, onOpenAccount, onSignOut }) {
  const navigate = useNavigate();
  // D-089: the prototype asserted "All systems operational" unconditionally,
  // which is a claim the UI is in no position to make. This reads the real
  // aggregate, and says "unavailable" rather than "fine" when it cannot.
  const [status, setStatus] = useState("unknown");

  useEffect(() => {
    let live = true;
    const poll = () =>
      api
        .health()
        .then((payload) => live && setStatus(payload?.status ?? "unknown"))
        .catch(() => live && setStatus("unknown"));

    poll();
    const timer = setInterval(poll, 60_000);
    return () => {
      live = false;
      clearInterval(timer);
    };
  }, []);

  const health = HEALTH_STATE[status] ?? HEALTH_STATE.unknown;
  return (
    <aside className="sticky top-0 hidden h-screen flex-col bg-ink lg:flex">
      <div className="border-b border-slate-800 px-5 py-4">
        <Wordmark size="text-xl" mark="h-8 w-8" icon={18} />
      </div>

      <div className="px-5 pb-2.5 pt-5 text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-600">
        Workspace
      </div>
      <div className="mx-3.5 mb-5 flex items-center gap-3 rounded-none border-l-2 border-emerald-500 bg-ink2 px-3.5 py-3">
        <div className="flex h-6 w-6 items-center justify-center rounded-none bg-slate-800 text-[11px] font-semibold text-slate-200">
          {(tenant?.name ?? "??").slice(0, 2).toUpperCase()}
        </div>
        <div className="min-w-0">
          {/* Resolved server-side from the Host header (D-021). */}
          <div className="truncate text-[13px] font-medium text-slate-100">
            {tenant?.name ?? "Workspace"}
          </div>
          <div className="truncate font-mono text-[10px] text-slate-500">
            {workspaceHost(tenant?.slug)}
          </div>
        </div>
      </div>

      {/* Primary action, above the navigation - the thing people come here to
          do, not a page they navigate to. */}
      <div className="mb-4 px-3.5">
        <button
          type="button"
          onClick={() => navigate("/app/chat")}
          className="flex w-full items-center justify-center gap-2 rounded-none bg-emerald-600 px-3.5 py-2.5 text-[13px] font-semibold text-white transition hover:bg-emerald-700"
        >
          <Plus size={15} strokeWidth={2} />
          New chat
        </button>
      </div>

      <div className="px-5 pb-2.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-600">
        Menu
      </div>
      <nav className="flex flex-col gap-0.5 px-3.5">
        {NAV.filter((item) => isAdmin || !item.adminOnly).map((item) => {
          const Icon = item.icon;
          return (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-none border-l-2 px-3.5 py-2.5 text-left text-[13.5px] font-medium no-underline transition ${
                  isActive
                    ? "border-emerald-500 bg-ink2 text-white"
                    : "border-transparent text-slate-400 hover:bg-ink2 hover:text-slate-200"
                }`
              }
            >
              <Icon size={17} strokeWidth={1.8} />
              {item.label}
              {item.badge && (
                <span className="ml-auto rounded-none bg-emerald-500 px-1.5 py-0.5 text-[10px] font-semibold tracking-wider text-emerald-950">
                  {item.badge}
                </span>
              )}
            </NavLink>
          );
        })}
      </nav>

      <Recents />

      <div className="mt-auto flex-none border-t border-slate-800">
        <div className="px-5 py-3">
          <div
            className={`flex items-center gap-2 text-[10.5px] font-semibold uppercase tracking-[0.1em] ${health.text}`}
          >
            <span className={`h-[7px] w-[7px] rounded-none ${health.dot}`} />
            {health.label}
          </div>
        </div>

        {/* The account lives at the foot of the rail, where every other chat
            product puts it, rather than in the top-right of a header the chat
            page barely uses. */}
        <div className="border-t border-slate-800 px-3.5 py-3">
          <ProfileMenu
            user={user}
            subtitle={user?.job_title}
            tone="dark"
            onOpenAccount={onOpenAccount}
            onSignOut={onSignOut}
          />
        </div>
      </div>
    </aside>
  );
}

function Header({ crumb, tenant }) {
  const navigate = useNavigate();

  return (
    <header className="sticky top-0 z-20 flex h-[66px] items-center gap-5 border-b border-hairline bg-white px-7">
      <div className="flex min-w-0 items-center gap-2.5">
        <div className="flex h-[26px] w-[26px] flex-none items-center justify-center rounded-none bg-ink font-mono text-[11px] font-bold text-emerald-400">
          {(tenant?.name ?? "??").slice(0, 2).toUpperCase()}
        </div>
        <span className="text-[13.5px] font-semibold text-ink">{tenant?.name ?? "Workspace"}</span>
        <span className="text-xs text-slate-400">/</span>
        <span className="truncate text-[13.5px] text-slate-600">{crumb}</span>
      </div>

      <div className="ml-auto flex flex-none items-center gap-2.5">
        {/* Points at the assistant, not the runbook list: an end user has no
            access to that page (D-140), and the assistant IS the search. */}
        <button
          type="button"
          onClick={() => navigate("/app/chat")}
          className="hidden w-60 items-center gap-2.5 rounded-none border border-hairline bg-slate-50 px-3 py-2 xl:flex"
        >
          <Search size={15} className="text-slate-400" />
          <span className="text-[13px] text-slate-400">Ask about an IT issue</span>
        </button>
        <button
          type="button"
          aria-label="Notifications"
          className="relative flex h-9 w-9 items-center justify-center rounded-none border border-hairline bg-white transition hover:bg-slate-50"
        >
          <Bell size={17} strokeWidth={1.8} className="text-slate-700" />
          <span className="absolute -right-px -top-px h-[7px] w-[7px] rounded-none bg-emerald-600" />
        </button>
      </div>
    </header>
  );
}

function PortalShell() {
  const { toast, dismissToast } = usePortal();
  const { tenant, user, role, logout } = useAuth();
  const isAdmin = role === "TENANT_ADMIN";
  const location = useLocation();
  const navigate = useNavigate();

  const onSignOut = async () => {
    await logout();
    navigate("/login", { replace: true });
  };

  const active = NAV.find((item) =>
    item.end ? location.pathname === item.to : location.pathname.startsWith(item.to)
  );
  const onChat = location.pathname.startsWith("/app/chat");

  return (
    <div className="grid min-h-screen grid-cols-1 bg-slate-100 lg:grid-cols-[260px_1fr]">
      <Sidebar
        tenant={tenant}
        isAdmin={isAdmin}
        user={user}
        onOpenAccount={() => navigate("/app/account")}
        onSignOut={onSignOut}
      />

      <div className="flex min-w-0 flex-col">
        <Header
          crumb={active?.crumb ?? "Dashboard"}
          tenant={tenant}
        />
        <Outlet />
      </div>

      {!onChat && (
        <button
          type="button"
          onClick={() => navigate("/app/chat")}
          className="fixed bottom-6 right-6 z-40 flex items-center gap-3 rounded-none bg-ink px-4 py-3.5 text-white shadow-2xl transition hover:bg-emerald-600"
        >
          <span className="flex h-[30px] w-[30px] flex-none items-center justify-center rounded-none bg-emerald-500">
            <Bot size={17} strokeWidth={2} className="text-emerald-950" />
          </span>
          <span className="text-left">
            <span className="block text-[13px] font-semibold">Ask MateAssist</span>
          </span>
        </button>
      )}

      <Toast toast={toast} onDismiss={dismissToast} />
    </div>
  );
}

export default function PortalLayout() {
  return (
    <PortalProvider>
      <ConversationsProvider>
      <PortalShell />
      </ConversationsProvider>
    </PortalProvider>
  );
}
