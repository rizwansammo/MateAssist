import { useCallback, useMemo, useState } from "react";
import { Switch } from "@mateassist/ui";

import { DataState } from "../components/DataState.jsx";
import { RevenueSection } from "../components/RevenueSection.jsx";
import { useAdmin } from "../context/AdminContext.jsx";
import { avatarClasses, avatarInitials } from "../lib/avatar.js";
import { compact, money, platformApi, share } from "../lib/platform.js";
import { useResource } from "../lib/useResource.js";

const RANGES = [
  { label: "Today", days: 1 },
  { label: "7 days", days: 7 },
  { label: "MTD", days: null }
];

const PLAN_STYLE = {
  ENTERPRISE: "border-ink bg-ink text-white",
  PRO: "border-cyan-200 bg-cyan-50 text-cyan-700",
  GROWTH: "border-slate-300 bg-slate-50 text-slate-600"
};

const ENGINE_LABEL = { TEXT: "Text & reasoning", VISION: "Vision & OCR" };
const ENGINE_BAR = { TEXT: "bg-emerald-600", VISION: "bg-cyan-600" };

export default function BillingPage() {
  const { notify } = useAdmin();
  const [range, setRange] = useState("MTD");
  const days = RANGES.find((r) => r.label === range)?.days ?? null;

  const spend = useResource(
    useCallback((signal) => platformApi.spend(days, signal), [days]),
    [days]
  );
  const usage = useResource(
    useCallback((signal) => platformApi.usage(days, signal), [days]),
    [days]
  );
  const budgets = useResource(useCallback(() => platformApi.budgets(), []));

  const rows = spend.data?.tenants ?? [];
  const totals = spend.data?.totals;
  const byEngine = usage.data?.by_engine ?? [];
  const topSpend = Number(rows[0]?.cost_usd ?? 0);
  const engineMax = Math.max(...byEngine.map((e) => Number(e.cost_usd ?? 0)), 0);

  const budgetList = useMemo(() => {
    const payload = budgets.data;
    return Array.isArray(payload) ? payload : (payload?.results ?? []);
  }, [budgets.data]);

  const budgetFor = useCallback(
    (tenantId) => budgetList.find((b) => b.tenant === tenantId),
    [budgetList]
  );

  const [saving, setSaving] = useState(null);

  const toggleEnforcement = useCallback(
    async (row) => {
      const existing = budgetFor(row.tenant_id);
      if (!existing) {
        notify(
          "No budget set",
          `${row.tenant_name} has no monthly cap yet. Set one before enforcing.`,
          "warn"
        );
        return;
      }
      setSaving(row.tenant_id);
      try {
        await platformApi.saveBudget({
          id: existing.id,
          monthly_usd: existing.monthly_usd,
          enforce: !existing.enforce,
          alert_at_percent: existing.alert_at_percent
        });
        budgets.reload();
        notify(
          existing.enforce ? "Enforcement off" : "Enforcement on",
          `${row.tenant_name} - ${
            existing.enforce
              ? "the cap is now advisory"
              : `calls stop at ${money(existing.monthly_usd)}`
          }`,
          existing.enforce ? "warn" : "ok"
        );
      } catch (cause) {
        notify("Could not update budget", cause?.message ?? "The change was not saved.", "warn");
      } finally {
        setSaving(null);
      }
    },
    [budgetFor, budgets, notify]
  );

  const setCap = useCallback(
    async (row) => {
      const existing = budgetFor(row.tenant_id);
      const entered = window.prompt(
        `Monthly cap for ${row.tenant_name}, in USD.\n\nZero means no limit. A cap is advisory until enforcement is switched on.`,
        existing?.monthly_usd ?? "50.00"
      );
      if (entered === null) return;

      const amount = Number(entered);
      if (!Number.isFinite(amount) || amount < 0) {
        notify("Not a valid amount", "Enter a number of dollars, or 0 for no limit.", "warn");
        return;
      }

      setSaving(row.tenant_id);
      try {
        await platformApi.saveBudget({
          id: existing?.id,
          tenant: row.tenant_id,
          monthly_usd: amount.toFixed(2),
          enforce: existing?.enforce ?? false,
          alert_at_percent: existing?.alert_at_percent ?? 80
        });
        budgets.reload();
        notify("Budget saved", `${row.tenant_name} - cap ${money(amount)} per month`);
      } catch (cause) {
        notify("Could not save budget", cause?.message ?? "The change was not saved.", "warn");
      } finally {
        setSaving(null);
      }
    },
    [budgetFor, budgets, notify]
  );

  return (
    <main className="flex flex-col gap-5 px-6 pb-12 pt-7">
      <div>
        <h1 className="mb-2 text-[28px] font-semibold tracking-tight text-ink">Usage &amp; billing</h1>
        <p className="text-sm text-slate-500">
          What each workspace is charged, and what it cost to serve them. The two are different
          numbers: rates below are the sell price, ModelPrice rows are what providers charge us.
        </p>
      </div>

      {/* Revenue first, then the cost of producing it (D-160). */}
      {/* `tenant_name`, not `tenant`: the spend rows come from
          platform_by_tenant, which annotates the name under that key. Reading
          the wrong field left every option in the "Applies to" dropdown blank,
          so a per-workspace rate looked impossible to create. */}
      <RevenueSection
        tenants={rows.map((row) => ({ id: row.tenant_id, name: row.tenant_name }))}
      />

      {totals?.unpriced_models?.length > 0 && (
        <div className="rounded-none border border-amber-300 bg-amber-50 px-5 py-3.5">
          <div className="text-[13px] font-semibold text-amber-900">
            {totals.unpriced_models.length} model(s) have no price, so their calls record $0.00
          </div>
          <div className="mt-1 font-mono text-[12px] text-amber-800">
            {totals.unpriced_models.join(", ")}
          </div>
          <div className="mt-1.5 text-[12px] leading-relaxed text-amber-800">
            Cost is stored when a call is metered, so adding a rate now will not reprice traffic
            already recorded. Set rates before the traffic arrives.
          </div>
        </div>
      )}

      <div className="grid gap-5 xl:grid-cols-[1.35fr_1fr]">
        <div className="rounded-none border border-hairline bg-white p-6">
          <DataState
            loading={spend.loading}
            error={spend.error}
            onRetry={spend.reload}
            rows={4}
            isEmpty={false}
          >
            <>
              <div className="flex flex-wrap items-end justify-between gap-4">
                <div>
                  <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500">
                    Platform spend - {range.toLowerCase()}
                  </div>
                  <div className="mt-2 text-4xl font-semibold tracking-tight text-ink">
                    {money(totals?.cost_usd)}
                  </div>
                </div>
                <div className="text-right">
                  <div className="text-[12.5px] text-slate-500">
                    {rows.length} workspace{rows.length === 1 ? "" : "s"} with usage
                  </div>
                  <div className="mt-0.5 text-[12.5px] font-semibold text-slate-600">
                    {totals?.requests ?? 0} calls
                  </div>
                </div>
              </div>
              <div className="mt-5 grid grid-cols-2 gap-px border border-hairline bg-hairline">
                {[
                  ["Tokens", compact(totals?.total_tokens), "text-ink"],
                  ["Prompt / completion", `${compact(totals?.prompt_tokens)} / ${compact(totals?.completion_tokens)}`, "text-ink"],
                  ["Avg latency", `${totals?.avg_latency_ms ?? 0} ms`, "text-ink"],
                  ["Failed calls", String(totals?.failed ?? 0), totals?.failed ? "text-amber-700" : "text-emerald-700"]
                ].map(([label, value, cls]) => (
                  <div key={label} className="rounded-none bg-white px-4 py-3.5">
                    <div className="text-[10.5px] uppercase tracking-[0.1em] text-slate-400">
                      {label}
                    </div>
                    <div className={`mt-1 font-mono text-lg font-semibold ${cls}`}>{value}</div>
                  </div>
                ))}
              </div>
            </>
          </DataState>
        </div>

        <div className="flex flex-col gap-3.5 rounded-none border border-hairline bg-white p-6">
          <div>
            <div className="text-[15px] font-semibold text-ink">Cost by engine</div>
            <div className="mt-0.5 text-[12.5px] text-slate-500">
              Two roles. The vendor behind each is configuration (A-010).
            </div>
          </div>
          <DataState
            loading={usage.loading}
            error={usage.error}
            isEmpty={!byEngine.length}
            onRetry={usage.reload}
            rows={2}
            empty={
              <div className="py-6 text-center text-[12.5px] text-slate-500">
                No engine calls in this window.
              </div>
            }
          >
            <>
              {byEngine.map((row) => (
                <div key={row.engine}>
                  <div className="flex justify-between gap-3 text-[13px]">
                    <span className="font-medium text-ink">
                      {ENGINE_LABEL[row.engine] ?? row.engine}
                    </span>
                    <span className="font-mono text-slate-600">{money(row.cost_usd)}</span>
                  </div>
                  <div className="mt-1.5 h-2 rounded-none bg-slate-100">
                    <div
                      className={`h-2 rounded-none ${ENGINE_BAR[row.engine] ?? "bg-slate-500"}`}
                      style={{ width: share(row.cost_usd, engineMax) }}
                    />
                  </div>
                  <div className="mt-1 text-[11.5px] text-slate-400">
                    {compact(row.total_tokens)} tokens - {row.requests} calls
                  </div>
                </div>
              ))}
            </>
          </DataState>
        </div>
      </div>

      <div className="rounded-none border border-hairline bg-white">
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-hairline px-6 py-4">
          <div>
            <div className="text-[15px] font-semibold text-ink">Consumption per tenant</div>
            <div className="mt-0.5 text-[12.5px] text-slate-500">
              Sorted by inference cost, {range}
            </div>
          </div>
          <div className="flex flex-none gap-2">
            {RANGES.map((option) => (
              <button
                key={option.label}
                type="button"
                onClick={() => setRange(option.label)}
                aria-pressed={range === option.label}
                className={`whitespace-nowrap rounded-none border px-3.5 py-2 text-[12.5px] font-medium transition ${
                  range === option.label
                    ? "border-ink bg-ink text-white"
                    : "border-slate-300 bg-white text-slate-700 hover:bg-slate-50"
                }`}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>

        <DataState
          loading={spend.loading}
          error={spend.error}
          isEmpty={!rows.length}
          onRetry={spend.reload}
          rows={5}
          empty={
            <div className="px-6 py-10 text-center">
              <div className="text-sm font-semibold text-ink">No usage in this window</div>
              <div className="mt-1.5 text-[12.5px] text-slate-500">
                Try a wider range, or check that a workspace has made an engine call.
              </div>
            </div>
          }
        >
          <div className="px-6 pb-5 pt-2">
            {rows.map((row) => {
              const budget = budgetFor(row.tenant_id);
              const cap = Number(budget?.monthly_usd ?? 0);
              const spent = Number(row.cost_usd ?? 0);
              const over = cap > 0 && spent >= cap;
              const alerting = cap > 0 && !over && spent >= (cap * (budget?.alert_at_percent ?? 80)) / 100;

              return (
                <div key={row.tenant_id} className="border-b border-slate-100 py-4">
                  <div className="flex flex-wrap items-center gap-3.5">
                    <div
                      className={`flex h-[26px] w-[26px] flex-none items-center justify-center rounded-none font-mono text-[10.5px] font-bold ${avatarClasses(
                        row.tenant_slug
                      )}`}
                    >
                      {avatarInitials(row.tenant_name)}
                    </div>
                    <div className="min-w-[150px] text-[13.5px] font-medium text-ink">
                      {row.tenant_name}
                    </div>
                    <span
                      className={`whitespace-nowrap rounded-none border px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wider ${
                        PLAN_STYLE[row.tenant_plan] ?? PLAN_STYLE.GROWTH
                      }`}
                    >
                      {row.tenant_plan}
                    </span>
                    <div className="ml-auto flex flex-wrap items-center gap-6">
                      {[
                        ["Tokens", compact(row.total_tokens), "text-ink"],
                        ["Calls", String(row.requests), "text-ink"],
                        ["Cost", money(row.cost_usd), "text-ink"],
                        [
                          "Cap",
                          cap > 0 ? money(cap) : "none",
                          over ? "text-red-700" : alerting ? "text-amber-700" : "text-slate-500"
                        ]
                      ].map(([label, value, cls]) => (
                        <div key={label} className="min-w-[80px] text-right">
                          <div className="text-[10.5px] uppercase tracking-[0.1em] text-slate-400">
                            {label}
                          </div>
                          <div className={`mt-0.5 font-mono text-[13px] font-semibold ${cls}`}>
                            {value}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="mt-3 h-2 rounded-none bg-slate-100">
                    <div
                      className={`h-2 rounded-none ${
                        over ? "bg-red-600" : alerting ? "bg-amber-500" : "bg-emerald-600"
                      }`}
                      style={{ width: cap > 0 ? share(spent, cap) : share(spent, topSpend) }}
                    />
                  </div>

                  <div className="mt-2.5 flex flex-wrap items-center gap-3">
                    <button
                      type="button"
                      onClick={() => setCap(row)}
                      disabled={saving === row.tenant_id}
                      className="rounded-none border border-slate-300 bg-white px-3 py-1.5 text-[12px] font-medium text-ink transition hover:bg-slate-50 disabled:opacity-50"
                    >
                      {budget ? "Change cap" : "Set cap"}
                    </button>
                    <button
                      type="button"
                      onClick={() => toggleEnforcement(row)}
                      disabled={saving === row.tenant_id}
                      className="flex items-center gap-2.5 rounded-none border border-hairline bg-slate-50 px-3 py-1.5 text-left transition hover:bg-slate-100 disabled:opacity-50"
                    >
                      <Switch on={Boolean(budget?.enforce)} />
                      <span className="text-[12px] font-medium text-ink">
                        {budget?.enforce ? "Enforced - calls stop at the cap" : "Advisory only"}
                      </span>
                    </button>
                    {over && budget?.enforce && (
                      <span className="rounded-none border border-red-300 bg-red-50 px-2.5 py-1 text-[11.5px] font-semibold text-red-700">
                        Over cap - engine calls are being refused
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </DataState>
      </div>
    </main>
  );
}
