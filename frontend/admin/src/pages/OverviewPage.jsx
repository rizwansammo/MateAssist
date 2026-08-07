import { useNavigate } from "react-router-dom";
import { Metric, Pill, TONE_DOT } from "@mateassist/ui";

import { useAdmin } from "../context/AdminContext.jsx";
import { SEED_HEALTH, SEED_USAGE } from "../seed/platform.js";

export default function OverviewPage() {
  const navigate = useNavigate();
  const { tenantStats, keyStats } = useAdmin();

  const text = keyStats("text");
  const vision = keyStats("vision");
  const activeKeys = text.active + vision.active;
  const poolKeys = text.pool + vision.pool;
  const limited = text.limited + vision.limited;

  return (
    <main className="flex flex-col gap-6 px-6 pb-12 pt-7">
      <div className="flex flex-wrap items-end justify-between gap-6">
        <div>
          <h1 className="mb-2 text-[30px] font-semibold tracking-tight text-ink">Global overview</h1>
          <p className="text-[14.5px] text-slate-600">
            {tenantStats.active} active tenants, {tenantStats.documents} indexed documents.
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
          value={tenantStats.active}
          valueClass="text-[32px]"
          note={`${tenantStats.suspended} suspended`}
        />
        <Metric
          label="API cost this month"
          value="$142.50"
          valueClass="text-[32px]"
          note="71% of $200 budget cap"
        />
        <Metric
          label="AI success rate"
          value="78%"
          valueClass="text-[32px]"
          note="Resolved without escalation"
          noteClass="text-emerald-700"
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
                Phase 7 drives this from the real /api/v1/health aggregate
              </div>
            </div>
          </div>
          {SEED_HEALTH.map((row) => (
            <div key={row.name} className="flex items-center gap-4 border-b border-slate-100 px-6 py-4">
              <span className={`h-2 w-2 flex-none rounded-none ${TONE_DOT[row.tone]}`} />
              <div className="min-w-0 flex-1">
                <div className="text-[13.5px] font-medium text-ink">{row.name}</div>
                <div className="mt-0.5 text-xs text-slate-500">{row.detail}</div>
              </div>
              <span className="hidden whitespace-nowrap font-mono text-xs text-slate-600 sm:block">
                {row.metric}
              </span>
              <Pill tone={row.tone} dot={false}>
                {row.state}
              </Pill>
            </div>
          ))}
        </div>

        <div className="rounded-none border border-hairline bg-white">
          <div className="border-b border-hairline px-5 py-4">
            <div className="text-[15px] font-semibold text-ink">Top tenants by spend</div>
            <div className="mt-0.5 text-[12.5px] text-slate-500">Month to date</div>
          </div>
          <div className="flex flex-col gap-3.5 px-5 pb-4 pt-4">
            {SEED_USAGE.slice(0, 4).map((row, index) => (
              <div key={row.slug}>
                <div className="flex justify-between gap-3 text-[13px]">
                  <span className="font-medium text-ink">{row.name}</span>
                  <span className="font-mono text-slate-600">{row.cost}</span>
                </div>
                <div className="mt-1.5 h-1.5 rounded-none bg-slate-100">
                  <div
                    className={`h-1.5 rounded-none ${
                      ["bg-emerald-600", "bg-cyan-600", "bg-amber-500", "bg-slate-500"][index]
                    }`}
                    style={{ width: row.pct }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </main>
  );
}
