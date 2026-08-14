import { Plus } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { Pill } from "@mateassist/ui";

import { DataState } from "../components/DataState.jsx";
import { useAdmin } from "../context/AdminContext.jsx";
import { avatarClasses, avatarInitials } from "../lib/avatar.js";

/** Plan is a TextChoices value on the wire; the UI supplies the label. */
const PLAN_STYLE = {
  ENTERPRISE: "border-ink bg-ink text-white",
  PRO: "border-cyan-200 bg-cyan-50 text-cyan-700",
  GROWTH: "border-slate-300 bg-slate-50 text-slate-600"
};

const STATUS_LABEL = { ACTIVE: "Active", SUSPENDED: "Suspended" };

function since(iso) {
  if (!iso) return "unknown";
  return new Date(iso).toLocaleDateString("en-GB", { month: "short", year: "numeric" });
}

export default function TenantsPage() {
  const navigate = useNavigate();
  const { tenants, tenantsLoading, tenantsError, refreshTenants, tenantStats, toggleTenant, notify } =
    useAdmin();

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
            notify(
              "Not yet available",
              "Self-serve provisioning arrives with the subscription flow (A-011). Workspaces are created by an operator until then.",
              "warn"
            )
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
            <div className={`mt-1.5 text-2xl font-semibold ${cls}`}>
              {tenantsLoading ? "--" : value}
            </div>
          </div>
        ))}
      </div>

      <div className="rounded-none border border-hairline bg-white">
        <DataState
          loading={tenantsLoading}
          error={tenantsError}
          isEmpty={!tenants.length}
          onRetry={refreshTenants}
          rows={5}
          empty={
            <div className="px-6 py-10 text-center">
              <div className="text-sm font-semibold text-ink">No workspaces yet</div>
              <div className="mt-1.5 text-[12.5px] text-slate-500">
                Run <span className="font-mono">manage.py seed_dev</span> to create the development
                workspaces.
              </div>
            </div>
          }
        >
          <div className="overflow-x-auto">
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
                  const active = tenant.status === "ACTIVE";
                  return (
                    <tr key={tenant.id}>
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
                              {tenant.region} - since {since(tenant.created_at)}
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
                            PLAN_STYLE[tenant.plan] ?? PLAN_STYLE.GROWTH
                          }`}
                        >
                          {tenant.plan}
                        </span>
                      </td>
                      <td className="border-b border-slate-100 px-4 py-4 text-right font-mono text-[13px] text-ink">
                        {tenant.users}
                      </td>
                      <td className="whitespace-nowrap border-b border-slate-100 px-4 py-4 text-[13px] text-slate-600">
                        {tenant.documents} document{tenant.documents === 1 ? "" : "s"}
                      </td>
                      <td className="border-b border-slate-100 px-4 py-4">
                        <Pill tone={active ? "ok" : "warn"}>
                          {STATUS_LABEL[tenant.status] ?? tenant.status}
                        </Pill>
                      </td>
                      <td className="border-b border-slate-100 px-6 py-4">
                        <div className="flex justify-end gap-2">
                          <button
                            type="button"
                            onClick={() => navigate(`/logs?tenant=${tenant.id}`)}
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
        </DataState>
      </div>

      <p className="text-[12.5px] text-slate-500">
        Suspending a tenant blocks portal sign-in and pauses its AI routing immediately. The change
        is written to the audit log.
      </p>
    </main>
  );
}
