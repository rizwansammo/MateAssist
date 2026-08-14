import { useEffect, useState } from "react";
import { Bot, BookOpen, Bell, ChevronDown, LayoutDashboard, Search } from "lucide-react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { Toast, Wordmark } from "@mateassist/ui";

import { useAuth } from "../context/AuthContext.jsx";
import { PortalProvider, usePortal } from "../context/PortalContext.jsx";
import { api } from "../lib/api.js";

// "My Tickets" is gone with A-008: there is no ticket table, and a nav item
// pointing at invented rows is worse than one fewer link.
const NAV = [
  { to: "/app", end: true, label: "Dashboard", icon: LayoutDashboard, crumb: "Dashboard" },
  { to: "/app/chat", label: "AI Support", icon: Bot, badge: "LIVE", crumb: "AI Support" },
  { to: "/app/knowledge", label: "Knowledge Base", icon: BookOpen, crumb: "Knowledge Base" }
];

const HEALTH_STATE = {
  ok: { label: "All systems operational", dot: "bg-emerald-500", text: "text-emerald-400" },
  degraded: { label: "Degraded performance", dot: "bg-amber-500", text: "text-amber-400" },
  error: { label: "Service disruption", dot: "bg-red-500", text: "text-red-400" },
  unknown: { label: "Status unavailable", dot: "bg-slate-500", text: "text-slate-400" }
};

function Sidebar({ tenant }) {
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
            {tenant?.slug ? `${tenant.slug}.mateassist.io` : ""}
          </div>
        </div>
      </div>

      <div className="px-5 pb-2.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-600">
        Menu
      </div>
      <nav className="flex flex-col gap-0.5 px-3.5">
        {NAV.map((item) => {
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

      <div className="mt-auto px-3.5 pb-4 pt-4">
        <div className="rounded-none border border-slate-800 bg-ink2 p-3.5">
          <div
            className={`flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.1em] ${health.text}`}
          >
            <span className={`h-[7px] w-[7px] rounded-none ${health.dot}`} />
            {health.label}
          </div>
        </div>
      </div>
    </aside>
  );
}

function Header({ crumb, tenant, user, onSignOut }) {
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
        <button
          type="button"
          onClick={() => navigate("/app/knowledge")}
          className="hidden w-60 items-center gap-2.5 rounded-none border border-hairline bg-slate-50 px-3 py-2 xl:flex"
        >
          <Search size={15} className="text-slate-400" />
          <span className="text-[13px] text-slate-400">Search runbooks</span>
        </button>
        <button
          type="button"
          aria-label="Notifications"
          className="relative flex h-9 w-9 items-center justify-center rounded-none border border-hairline bg-white transition hover:bg-slate-50"
        >
          <Bell size={17} strokeWidth={1.8} className="text-slate-700" />
          <span className="absolute -right-px -top-px h-[7px] w-[7px] rounded-none bg-emerald-600" />
        </button>
        <div className="h-7 w-px bg-hairline" />
        <button
          type="button"
          onClick={onSignOut}
          title="Sign out"
          className="flex items-center gap-2.5 rounded-none border border-transparent p-1 pr-1.5 transition hover:border-hairline hover:bg-slate-50"
        >
          <div className="flex h-[30px] w-[30px] items-center justify-center rounded-none bg-teal-700 text-xs font-semibold text-white">
            {user?.initials ?? "?"}
          </div>
          <div className="hidden text-left sm:block">
            <div className="text-[13px] font-medium leading-tight text-ink">
              {user?.display_name ?? user?.email}
            </div>
            <div className="text-[11px] leading-tight text-slate-500">{user?.job_title || ""}</div>
          </div>
          <ChevronDown size={14} className="text-slate-400" />
        </button>
      </div>
    </header>
  );
}

function PortalShell() {
  const { toast, dismissToast } = usePortal();
  const { tenant, user, logout } = useAuth();
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
      <Sidebar tenant={tenant} />

      <div className="flex min-w-0 flex-col">
        <Header
          crumb={active?.crumb ?? "Dashboard"}
          tenant={tenant}
          user={user}
          onSignOut={onSignOut}
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
      <PortalShell />
    </PortalProvider>
  );
}
