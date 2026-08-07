import { useState } from "react";
import { Switch } from "@mateassist/ui";

import { useAdmin } from "../context/AdminContext.jsx";
import { avatarClasses, avatarInitials } from "../lib/avatar.js";
import { PLAN_STYLE, SEED_PROVIDER_SPEND, SEED_USAGE } from "../seed/platform.js";

const RANGES = ["Today", "7 days", "MTD"];

export default function BillingPage() {
  const { notify } = useAdmin();
  const [range, setRange] = useState("MTD");
  // D-086: the only orchestration policy that survived the two-engine
  // restructure. Groq routing and OpenAI fallback are gone with their providers.
  const [tenantCaps, setTenantCaps] = useState(false);

  return (
    <main className="flex flex-col gap-5 px-6 pb-12 pt-7">
      <div>
        <h1 className="mb-2 text-[28px] font-semibold tracking-tight text-ink">Usage &amp; billing</h1>
        <p className="text-sm text-slate-500">
          Token consumption and inference cost per tenant, against plan revenue. Costs derive from
          editable ModelPrice rows, never hardcoded rates.
        </p>
      </div>

      <div className="grid gap-5 xl:grid-cols-[1.35fr_1fr]">
        <div className="rounded-none border border-hairline bg-white p-6">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500">
                Platform spend - month to date
              </div>
              <div className="mt-2 text-4xl font-semibold tracking-tight text-ink">$142.50</div>
            </div>
            <div className="text-right">
              <div className="text-[12.5px] text-slate-500">Budget cap $200.00</div>
              <div className="mt-0.5 text-[12.5px] font-semibold text-amber-700">
                71% consumed
              </div>
            </div>
          </div>
          <div className="mt-4 flex h-2.5 rounded-none bg-slate-100">
            <div className="rounded-none bg-emerald-600" style={{ width: "71%" }} />
            <div className="rounded-none bg-amber-500" style={{ width: "8%" }} />
          </div>
          <div className="mt-5 grid grid-cols-2 gap-px border border-hairline bg-hairline">
            {[
              ["Tokens MTD", "184.2M", "text-ink"],
              ["Cost / resolution", "$0.037", "text-ink"],
              ["Gross margin", "92.4%", "text-ink"],
              ["Vision share", "6%", "text-cyan-700"]
            ].map(([label, value, cls]) => (
              <div key={label} className="rounded-none bg-white px-4 py-3.5">
                <div className="text-[10.5px] uppercase tracking-[0.1em] text-slate-400">
                  {label}
                </div>
                <div className={`mt-1 font-mono text-lg font-semibold ${cls}`}>{value}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="flex flex-col gap-3.5 rounded-none border border-hairline bg-white p-6">
          <div>
            <div className="text-[15px] font-semibold text-ink">Cost by engine</div>
            <div className="mt-0.5 text-[12.5px] text-slate-500">
              Two engines, no fallback provider
            </div>
          </div>
          {SEED_PROVIDER_SPEND.map((provider) => (
            <div key={provider.name}>
              <div className="flex justify-between gap-3 text-[13px]">
                <span className="font-medium text-ink">{provider.name}</span>
                <span className="font-mono text-slate-600">{provider.cost}</span>
              </div>
              <div className="mt-1.5 h-2 rounded-none bg-slate-100">
                <div className={`h-2 rounded-none ${provider.bar}`} style={{ width: provider.pct }} />
              </div>
              <div className="mt-1 text-[11.5px] text-slate-400">
                {provider.tokens} tokens - {provider.share} of traffic
              </div>
            </div>
          ))}

          <button
            type="button"
            onClick={() => {
              setTenantCaps((v) => !v);
              notify(
                "Policy updated",
                `Per-tenant monthly token caps ${tenantCaps ? "off" : "on"}`,
                tenantCaps ? "warn" : "ok"
              );
            }}
            className="mt-auto flex items-start gap-3.5 rounded-none border border-hairline bg-slate-50 p-4 text-left transition hover:bg-slate-100"
          >
            <span className="mt-0.5">
              <Switch on={tenantCaps} />
            </span>
            <span>
              <span className="block text-[13px] font-semibold text-ink">
                Enforce per-tenant monthly token caps
              </span>
              <span className="mt-1 block text-[12px] leading-relaxed text-slate-500">
                Hard-stops a workspace at its plan allowance instead of absorbing overage into
                platform margin.
              </span>
            </span>
          </button>
        </div>
      </div>

      <div className="rounded-none border border-hairline bg-white">
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-hairline px-6 py-4">
          <div>
            <div className="text-[15px] font-semibold text-ink">Token consumption per tenant</div>
            <div className="mt-0.5 text-[12.5px] text-slate-500">
              Sorted by inference cost, {range}
            </div>
          </div>
          <div className="flex flex-none gap-2">
            {RANGES.map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => setRange(option)}
                aria-pressed={range === option}
                className={`whitespace-nowrap rounded-none border px-3.5 py-2 text-[12.5px] font-medium transition ${
                  range === option
                    ? "border-ink bg-ink text-white"
                    : "border-slate-300 bg-white text-slate-700 hover:bg-slate-50"
                }`}
              >
                {option}
              </button>
            ))}
          </div>
        </div>
        <div className="px-6 pb-5 pt-2">
          {SEED_USAGE.map((row) => {
            const thin = row.tone === "warn";
            return (
              <div key={row.slug} className="border-b border-slate-100 py-4">
                <div className="flex flex-wrap items-center gap-3.5">
                  <div
                    className={`flex h-[26px] w-[26px] flex-none items-center justify-center rounded-none font-mono text-[10.5px] font-bold ${avatarClasses(
                      row.slug
                    )}`}
                  >
                    {avatarInitials(row.name)}
                  </div>
                  <div className="min-w-[150px] text-[13.5px] font-medium text-ink">{row.name}</div>
                  <span
                    className={`whitespace-nowrap rounded-none border px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wider ${
                      PLAN_STYLE[row.plan]
                    }`}
                  >
                    {row.plan}
                  </span>
                  <div className="ml-auto flex flex-wrap items-center gap-6">
                    {[
                      ["Tokens", row.tokens, "text-ink"],
                      ["Cost", row.cost, "text-ink"],
                      ["Margin", row.margin, thin ? "text-amber-700" : "text-emerald-700"]
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
                    className={`h-2 rounded-none ${thin ? "bg-amber-500" : "bg-emerald-600"}`}
                    style={{ width: row.pct }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </main>
  );
}
