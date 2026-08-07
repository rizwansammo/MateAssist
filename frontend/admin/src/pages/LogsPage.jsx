import { useMemo, useState } from "react";
import { X } from "lucide-react";
import { useSearchParams } from "react-router-dom";

import { LOG_LEVEL_STYLE, SEED_LOGS } from "../seed/platform.js";

const LEVELS = ["All", "Info", "Warn", "Error", "Auth"];

/**
 * System Logs.
 *
 * Phase 7 streams this from AuditEvent (D-114). Metadata only - tenant payloads
 * are redacted, and retention is 90 days.
 *
 * The tenant filter reads from the query string so "View logs" on the tenants
 * page produces a shareable, back-button-friendly URL rather than hidden state.
 */
export default function LogsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [level, setLevel] = useState("All");
  const tenant = searchParams.get("tenant") ?? "";

  const logs = useMemo(
    () =>
      SEED_LOGS.filter((log) => {
        if (level !== "All" && log.level !== level.toLowerCase()) return false;
        if (tenant && log.tenant !== tenant) return false;
        return true;
      }),
    [level, tenant]
  );

  const clearTenant = () => {
    searchParams.delete("tenant");
    setSearchParams(searchParams, { replace: true });
  };

  return (
    <main className="flex flex-col gap-4 px-6 pb-12 pt-7">
      <div>
        <h1 className="mb-2 text-[28px] font-semibold tracking-tight text-ink">System logs</h1>
        <p className="text-sm text-slate-500">
          Platform-wide event stream. Tenant payloads are redacted; only metadata is retained for
          90 days.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {LEVELS.map((option) => {
          const count =
            option === "All"
              ? SEED_LOGS.length
              : SEED_LOGS.filter((l) => l.level === option.toLowerCase()).length;
          const active = level === option;
          return (
            <button
              key={option}
              type="button"
              onClick={() => setLevel(option)}
              aria-pressed={active}
              className={`whitespace-nowrap rounded-none border px-3.5 py-2 text-[12.5px] font-medium transition ${
                active
                  ? "border-ink bg-ink text-white"
                  : "border-slate-300 bg-white text-slate-700 hover:bg-slate-50"
              }`}
            >
              {option} <span className="font-mono opacity-70">{count}</span>
            </button>
          );
        })}
        {tenant && (
          <button
            type="button"
            onClick={clearTenant}
            className="ml-auto flex items-center gap-2.5 whitespace-nowrap rounded-none border border-ink bg-ink px-3.5 py-2 text-[12.5px] font-medium text-white"
          >
            tenant: {tenant}
            <X size={13} />
          </button>
        )}
      </div>

      <div className="rounded-none border border-hairline bg-ink">
        <div className="flex items-center gap-4 border-b border-slate-800 px-5 py-3">
          <span className="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-400">
            Live tail
          </span>
          <span className="ml-auto font-mono text-[11.5px] text-slate-600">
            {logs.length} events
          </span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[900px] border-collapse">
            <tbody>
              {logs.map((log) => (
                <tr key={`${log.time}-${log.message}`}>
                  <td className="whitespace-nowrap border-b border-slate-900 px-5 py-2.5 align-top font-mono text-xs text-slate-500">
                    {log.time}
                  </td>
                  <td className="border-b border-slate-900 px-2.5 py-2.5 align-top">
                    <span
                      className={`whitespace-nowrap rounded-none border px-2 py-0.5 font-mono text-[10.5px] font-semibold uppercase tracking-[0.1em] ${
                        LOG_LEVEL_STYLE[log.level]
                      }`}
                    >
                      {log.level}
                    </span>
                  </td>
                  <td className="whitespace-nowrap border-b border-slate-900 px-2.5 py-2.5 align-top font-mono text-xs text-slate-400">
                    {log.tenant}
                  </td>
                  <td className="border-b border-slate-900 px-5 py-2.5 font-mono text-[12.5px] leading-relaxed text-slate-200">
                    {log.message}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {logs.length === 0 && (
          <div className="px-5 py-10 text-center">
            <div className="text-sm font-semibold text-white">No events match this filter</div>
            <button
              type="button"
              onClick={() => {
                setLevel("All");
                clearTenant();
              }}
              className="mt-3.5 rounded-none border border-emerald-500 bg-transparent px-4 py-2 text-[12.5px] font-semibold text-emerald-400"
            >
              Reset filters
            </button>
          </div>
        )}
      </div>
    </main>
  );
}
