import { BarChart3, Building2, KeyRound, LayoutDashboard, ScrollText, ShieldCheck } from "lucide-react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { Toast } from "@mateassist/ui";

import { ProfileMenu } from "../components/ProfileMenu.jsx";
import { useAuth } from "../context/AuthContext.jsx";
import { AdminProvider, useAdmin } from "../context/AdminContext.jsx";

const NAV = [
  { to: "/", end: true, label: "Global Overview", icon: LayoutDashboard, crumb: "Global overview" },
  { to: "/tenants", label: "Tenant Management", icon: Building2, crumb: "Tenant management" },
  { to: "/ai", label: "AI Configuration", icon: KeyRound, crumb: "AI configuration" },
  { to: "/billing", label: "Usage & Billing", icon: BarChart3, crumb: "Usage & billing" },
  { to: "/logs", label: "System Logs", icon: ScrollText, crumb: "System logs" }
];

function Sidebar() {
  const { tenantStats, pools } = useAdmin();
  const text = pools.TEXT;
  const vision = pools.VISION;
  const anyLimited = text.rate_limited + vision.rate_limited > 0;

  return (
    <aside className="sticky top-0 hidden h-screen flex-col border-r border-slate-800 bg-[#07101C] lg:flex">
      <div className="border-b border-slate-800 px-5 pb-4 pt-5">
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 flex-none items-center justify-center rounded-none bg-emerald-500">
            <ShieldCheck size={18} strokeWidth={2} className="text-emerald-950" />
          </div>
          <span className="font-wordmark text-xl uppercase tracking-wide text-white">
            MateAssist
          </span>
        </div>
        <div className="mt-3 inline-flex items-center gap-2 rounded-none border border-amber-700 bg-amber-950/40 px-2.5 py-1">
          <ShieldCheck size={12} className="text-amber-500" />
          <span className="text-[10px] font-semibold uppercase tracking-[0.14em] text-amber-400">
            Super Admin Mode
          </span>
        </div>
      </div>

      <div className="px-5 pb-2.5 pt-5 text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-600">
        Platform
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
                    ? "border-emerald-500 bg-[#0F1B2D] text-white"
                    : "border-transparent text-slate-400 hover:bg-[#0F1B2D] hover:text-slate-200"
                }`
              }
            >
              <Icon size={17} strokeWidth={1.8} />
              {item.label}
              {item.to === "/tenants" && (
                <span className="ml-auto font-mono text-[11px] text-slate-500">
                  {tenantStats.total}
                </span>
              )}
              {item.to === "/ai" && (
                <span
                  className={`ml-auto rounded-none px-1.5 py-0.5 font-mono text-[10px] font-semibold ${
                    anyLimited ? "bg-amber-950 text-amber-400" : "bg-emerald-950 text-emerald-300"
                  }`}
                >
                  {text.active + vision.active}/{text.pool + vision.pool || 0}
                </span>
              )}
            </NavLink>
          );
        })}
      </nav>

      <div className="mt-auto px-3.5 pb-4 pt-4">
        <div className="px-1 font-mono text-[10.5px] text-slate-700">
          v0.1.0 - phase 1
        </div>
      </div>
    </aside>
  );
}

function Header({ crumb, user, role, onSignOut }) {
  return (
    <header className="sticky top-0 z-20 flex h-[66px] items-center gap-4 border-b border-slate-800 bg-ink px-6">
      <div className="flex min-w-0 items-center gap-2.5">
        <span className="font-mono text-[13px] text-slate-500">platform</span>
        <span className="text-xs text-slate-700">/</span>
        <span className="truncate text-sm font-semibold text-white">{crumb}</span>
      </div>
      <div className="ml-auto flex flex-none items-center gap-3">
        <ProfileMenu user={user} role={role} onSignOut={onSignOut} />
      </div>
    </header>
  );
}

function AdminShell() {
  const { toast, dismissToast } = useAdmin();
  const { user, role, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const active = NAV.find((item) =>
    item.end ? location.pathname === item.to : location.pathname.startsWith(item.to)
  );

  const onSignOut = async () => {
    await logout();
    navigate("/login", { replace: true });
  };

  return (
    <div className="grid min-h-screen grid-cols-1 bg-slate-100 lg:grid-cols-[268px_1fr]">
      <Sidebar />
      <div className="flex min-w-0 flex-col">
        <Header
          crumb={active?.crumb ?? "Global overview"}
          user={user}
          role={role}
          onSignOut={onSignOut}
        />
        <Outlet />
      </div>
      <Toast toast={toast} onDismiss={dismissToast} />
    </div>
  );
}

export default function AdminLayout() {
  return (
    <AdminProvider>
      <AdminShell />
    </AdminProvider>
  );
}
