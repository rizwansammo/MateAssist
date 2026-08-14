import { useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { Metric, Pill, TONE_DOT } from "@mateassist/ui";

import { DataState } from "../components/DataState.jsx";
import { useAdmin } from "../context/AdminContext.jsx";
import { api } from "../lib/api.js";
import { compact, money, percent, platformApi, share } from "../lib/platform.js";
import { useResource } from "../lib/useResource.js";

/** health.run_all() reports ok | degraded | error; the UI speaks in tones. */
const HEALTH_TONE = { ok: "ok", degraded: "warn", error: "bad" };
const HEALTH_LABEL = { ok: "Operational", degraded: "Degraded", error: "Down" };
const BAR = ["bg-emerald-600", "bg-cyan-600", "bg-amber-500", "bg-slate-500"];

export default function OverviewPage() {
  const navigate = useNavigate();
  const { tenantStats, tenantsLoading, pools } = useAdmin();

  const usage = useResource(useCallback((signal) => platformApi.usage(undefined, signal), []));
  const spend = useResource(useCallback((signal) => platformApi.spend(undefined, signal), []));
  const health = useResource(useCallback((signal) => api.health(signal), []));

  const activeKeys = pools.TEXT.active + pools.VISION.active;
  const poolKeys = pools.TEXT.pool + pools.VISION.pool;
  const limited = pools.TEXT.rate_limited + pools.VISION.rate_limited;

  const totals = usage.data?.totals;
  const topTenants = (spend.data?.tenants ?? []).slice(0, 4);
  const topSpend = Number(spend.data?.tenants?.[0]?.cost_usd ?? 0);
  const checks = health.data?.checks ?? [];

  return (
    <main className="flex flex-col gap-6 px-6 pb-12 pt-7">
      <div className="flex flex-wrap items-end justify-between gap-6">
        <div>
          <h1 className="mb-2 text-[30px] font-semibold tracking-tight text-ink">Global overview</h1>
          <p className="text-[14.5px] text-slate-600">
            {tenantsLoading
              ? "Loading workspaces..."
              : `${tenantStats.active} active tenants, ${tenantStats.documents} indexed documents.`}
          </p>
        </div>
        <div className="flex flex-none gap-2.5">
          <button
            type="button"
            onClick={() => navigate("/ai")}
            className="whitespace-nowrap rounded-none border border-slate-300 bg-white px-4 py-3 text-[13px] font-medium text-ink transition hover:bg-slate-50"
          >
            Manage API keys
          </button>
          <button
            type="button"
            onClick={() => navigate("/billing")}
            className="whitespace-nowrap rounded-none bg-emerald-600 px-4 py-3 text-[13px] font-semibold text-white transition hover:bg-emerald-700"
          >
            Cost report
          </button>
        </div>
      </div>

      <div className="grid gap-px border border-hairline bg-hairline sm:grid-cols-2 xl:grid-cols-4">
        <Metric
          label="Total active tenants"
          value={tenantsLoading ? "--" : tenantStats.active}
          valueClass="text-[32px]"
          note={`${tenantStats.suspended} suspended`}
        />
        <Metric
          label="API cost this month"
          value={usage.loading ? "--" : money(totals?.cost_usd)}
          valueClass="text-[32px]"
          note={
            totals?.unpriced_models?.length
              ? `${totals.unpriced_models.length} model(s) unpriced`
              : "All models priced"
          }
          noteClass={totals?.unpriced_models?.length ? "text-amber-700" : "text-slate-400"}
        />
        <Metric
          label="Call success rate"
          value={usage.loading ? "--" : percent(totals?.success_rate)}
          valueClass="text-[32px]"
          note={totals ? `${totals.failed} failed of ${totals.requests}` : "No calls yet"}
          noteClass={totals?.failed ? "text-amber-700" : "text-emerald-700"}
        />
        <Metric
          label="Active API keys"
          value={`${activeKeys}/${poolKeys}`}
          valueClass="text-[32px]"
          mono
          note={limited ? `${limited} rate-limited, cooling down` : "All pooled keys healthy"}
          noteClass={limited ? "text-amber-700" : "text-slate-400"}
        />
      </div>

      <div className="grid gap-5 xl:grid-cols-[1.35fr_1fr]">
        <div className="rounded-none border border-hairline bg-white">
          <div className="flex flex-wrap items-center justify-between gap-4 border-b border-hairline px-6 py-4">
            <div>
              <div className="text-[15px] font-semibold text-ink">Status centre</div>
              <div className="mt-0.5 text-[12.5px] text-slate-500">
                Live from /api/v1/health - each dependency is exercised, not pinged
              </div>
            </div>
            {health.data && (
              <Pill tone={HEALTH_TONE[health.data.status] ?? "warn"} dot={false}>
                {HEALTH_LABEL[health.data.status] ?? health.data.status}
              </Pill>
            )}
          </div>
          <DataState
            loading={health.loading}
            error={health.error}
            isEmpty={!checks.length}
            onRetry={health.reload}
            rows={5}
          >
            {checks.map((check) => (
              <div
                key={check.name}
                className="flex items-center gap-4 border-b border-slate-100 px-6 py-4"
              >
                <span
                  className={`h-2 w-2 flex-none rounded-none ${
                    TONE_DOT[HEALTH_TONE[check.status] ?? "warn"]
                  }`}
                />
                <div className="min-w-0 flex-1">
                  <div className="text-[13.5px] font-medium capitalize text-ink">
                    {check.name.replace(/_/g, " ")}
                  </div>
                  <div className="mt-0.5 text-xs text-slate-500">{check.detail}</div>
                </div>
                <span className="hidden whitespace-nowrap font-mono text-xs text-slate-600 sm:block">
                  {check.latency_ms != null ? `${check.latency_ms} ms` : "--"}
                </span>
                <Pill tone={HEALTH_TONE[check.status] ?? "warn"} dot={false}>
                  {HEALTH_LABEL[check.status] ?? check.status}
                </Pill>
              </div>
            ))}
          </DataState>
        </div>

        <div className="rounded-none border border-hairline bg-white">
          <div className="border-b border-hairline px-5 py-4">
            <div className="text-[15px] font-semibold text-ink">Top tenants by spend</div>
            <div className="mt-0.5 text-[12.5px] text-slate-500">Month to date</div>
          </div>
          <DataState
            loading={spend.loading}
            error={spend.error}
            isEmpty={!topTenants.length}
            onRetry={spend.reload}
            rows={4}
            empty={
              <div className="px-5 py-10 text-center">
                <div className="text-sm font-semibold text-ink">No usage recorded yet</div>
                <div className="mt-1.5 text-[12.5px] text-slate-500">
                  Spend appears here once a workspace makes its first engine call.
                </div>
              </div>
            }
          >
            <div className="flex flex-col gap-3.5 px-5 pb-4 pt-4">
              {topTenants.map((row, index) => (
                <div key={row.tenant_slug}>
                  <div className="flex justify-between gap-3 text-[13px]">
                    <span className="font-medium text-ink">{row.tenant_name}</span>
                    <span className="font-mono text-slate-600">{money(row.cost_usd)}</span>
                  </div>
                  <div className="mt-1.5 h-1.5 rounded-none bg-slate-100">
                    <div
                      className={`h-1.5 rounded-none ${BAR[index]}`}
                      style={{ width: share(row.cost_usd, topSpend) }}
                    />
                  </div>
                  <div className="mt-1 text-[11.5px] text-slate-400">
                    {compact(row.total_tokens)} tokens - {row.requests} calls
                  </div>
                </div>
              ))}
            </div>
          </DataState>
        </div>
      </div>
    </main>
  );
}
