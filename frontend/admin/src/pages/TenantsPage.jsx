import { Plus } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { Pill } from "@mateassist/ui";

import { useAdmin } from "../context/AdminContext.jsx";
import { avatarClasses, avatarInitials } from "../lib/avatar.js";
import { PLAN_STYLE } from "../seed/platform.js";

export default function TenantsPage() {
  const navigate = useNavigate();
  const { tenants, tenantStats, toggleTenant, notify } = useAdmin();

  return (
    <main className="flex flex-col gap-5 px-6 pb-12 pt-7">
      <div className="flex flex-wrap items-end justify-between gap-6">
        <div>
          <h1 className="mb-2 text-[28px] font-semibold tracking-tight text-ink">
            Tenant management
          </h1>
          <p className="text-sm text-slate-500">
            Every workspace on the platform, its plan, footprint and isolation state.
          </p>
        </div>
        <button
          type="button"
          onClick={() =>
            notify("Not yet available", "Tenant provisioning lands in Phase 2.", "warn")
          }
          className="flex flex-none items-center gap-2 whitespace-nowrap rounded-none bg-emerald-600 px-4 py-3 text-[13.5px] font-semibold text-white transition hover:bg-emerald-700"
        >
          <Plus size={15} />
          Provision tenant
        </button>
      </div>

      <div className="grid gap-px border border-hairline bg-hairline sm:grid-cols-2 xl:grid-cols-4">
        {[
          ["Active", tenantStats.active, "text-ink"],
          ["Suspended", tenantStats.suspended, "text-amber-700"],
          ["Seats in use", tenantStats.seats.toLocaleString("en-GB"), "text-ink"],
          ["Indexed documents", tenantStats.documents, "text-ink"]
        ].map(([label, value, cls]) => (
          <div key={label} className="rounded-none bg-white px-5 py-4">
            <div className="text-[10.5px] font-semibold uppercase tracking-[0.12em] text-slate-500">
              {label}
            </div>
            <div className={`mt-1.5 text-2xl font-semibold ${cls}`}>{value}</div>
          </div>
        ))}
      </div>

      <div className="overflow-x-auto rounded-none border border-hairline bg-white">
        <table className="w-full min-w-[1040px] border-collapse">
          <thead>
            <tr className="bg-slate-50 text-left text-[10.5px] font-semibold uppercase tracking-[0.12em] text-slate-500">
              <th className="border-b border-hairline px-6 py-3">Tenant</th>
              <th className="border-b border-hairline px-4 py-3">Subdomain</th>
              <th className="border-b border-hairline px-4 py-3">Plan</th>
              <th className="border-b border-hairline px-4 py-3 text-right">Users</th>
              <th className="border-b border-hairline px-4 py-3">Knowledge base</th>
              <th className="border-b border-hairline px-4 py-3">Status</th>
              <th className="border-b border-hairline px-6 py-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {tenants.map((tenant) => {
              const active = tenant.status === "Active";
              return (
                <tr key={tenant.slug}>
                  <td className="border-b border-slate-100 px-6 py-4">
                    <div className="flex items-center gap-3">
                      {/* D-088: colour derived from the slug, not a hardcoded map. */}
                      <div
                        className={`flex h-7 w-7 flex-none items-center justify-center rounded-none font-mono text-[11px] font-bold ${avatarClasses(
                          tenant.slug
                        )}`}
                      >
                        {avatarInitials(tenant.name)}
                      </div>
                      <div>
                        <div className="text-[13.5px] font-medium text-ink">{tenant.name}</div>
                        <div className="mt-0.5 text-[11.5px] text-slate-400">
                          {tenant.region} - since {tenant.since}
                        </div>
                      </div>
                    </div>
                  </td>
                  <td className="whitespace-nowrap border-b border-slate-100 px-4 py-4 font-mono text-[12.5px] text-slate-700">
                    {tenant.subdomain}
                  </td>
                  <td className="border-b border-slate-100 px-4 py-4">
                    <span
                      className={`whitespace-nowrap rounded-none border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wider ${
                        PLAN_STYLE[tenant.plan]
                      }`}
                    >
                      {tenant.plan}
                    </span>
                  </td>
                  <td className="border-b border-slate-100 px-4 py-4 text-right font-mono text-[13px] text-ink">
                    {tenant.users}
                  </td>
                  <td className="whitespace-nowrap border-b border-slate-100 px-4 py-4 text-[13px] text-slate-600">
                    {tenant.documents} documents - {tenant.kbSize}
                  </td>
                  <td className="border-b border-slate-100 px-4 py-4">
                    <Pill tone={active ? "ok" : "warn"}>{tenant.status}</Pill>
                  </td>
                  <td className="border-b border-slate-100 px-6 py-4">
                    <div className="flex justify-end gap-2">
                      <button
                        type="button"
                        onClick={() => navigate(`/logs?tenant=${tenant.slug}`)}
                        className="whitespace-nowrap rounded-none border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 transition hover:bg-slate-50"
                      >
                        View logs
                      </button>
                      <button
                        type="button"
                        onClick={() => toggleTenant(tenant)}
                        className={`whitespace-nowrap rounded-none border bg-white px-3 py-1.5 text-xs font-semibold transition hover:bg-slate-50 ${
                          active
                            ? "border-amber-200 text-amber-700"
                            : "border-emerald-200 text-emerald-700"
                        }`}
                      >
                        {active ? "Suspend" : "Reactivate"}
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <p className="text-[12.5px] text-slate-500">
        Suspending a tenant blocks portal sign-in and pauses its AI routing immediately.
      </p>
    </main>
  );
}
