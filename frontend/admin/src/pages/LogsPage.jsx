import { useCallback, useState } from "react";
import { RefreshCw, X } from "lucide-react";
import { useSearchParams } from "react-router-dom";

import { DataState } from "../components/DataState.jsx";
import { platformApi } from "../lib/platform.js";
import { useResource } from "../lib/useResource.js";

const LEVELS = ["all", "info", "warn", "error", "auth"];

const LOG_LEVEL_STYLE = {
  info: "border-slate-800 text-slate-400",
  warn: "border-amber-900 text-amber-400",
  error: "border-red-900 text-red-400",
  auth: "border-teal-900 text-teal-300"
};

/**
 * System Logs, from AuditEvent (D-114).
 *
 * Metadata only - tenant payloads are never written to this log, so there is
 * nothing here to redact at render time.
 *
 * Filtering happens server-side. The prototype filtered a fixed array in the
 * browser, which cannot work once the log is longer than one page: a client
 * filter over the most recent 100 rows silently answers "no warnings" when it
 * means "no warnings in the last 100 events".
 *
 * The tenant filter reads from the query string so "View logs" on the tenants
 * page produces a shareable, back-button-friendly URL rather than hidden state.
 */
export default function LogsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [level, setLevel] = useState("all");
  const tenant = searchParams.get("tenant") ?? "";

  const logs = useResource(
    useCallback(
      (signal) => platformApi.logs({ level, tenant: tenant || undefined, limit: 100 }, signal),
      [level, tenant]
    ),
    [level, tenant]
  );

  const rows = logs.data?.results ?? [];
  const total = logs.data?.count ?? 0;

  const clearTenant = () => {
    searchParams.delete("tenant");
    setSearchParams(searchParams, { replace: true });
  };

  /** Metadata rendered as key=value, the way an operator greps a log. */
  const renderMeta = (row) => {
    const pairs = Object.entries(row.metadata ?? {})
      .map(([key, value]) => `${key}=${typeof value === "object" ? JSON.stringify(value) : value}`)
      .join(" ");
    return [row.target && `target=${row.target}`, pairs].filter(Boolean).join(" ");
  };

  return (
    <main className="flex flex-col gap-4 px-6 pb-12 pt-7">
      <div>
        <h1 className="mb-2 text-[28px] font-semibold tracking-tight text-ink">System logs</h1>
        <p className="text-sm text-slate-500">
          Platform-wide event stream, append-only. Metadata only - tenant payloads are never
          written here.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {LEVELS.map((option) => {
          const active = level === option;
          return (
            <button
              key={option}
              type="button"
              onClick={() => setLevel(option)}
              aria-pressed={active}
              className={`whitespace-nowrap rounded-none border px-3.5 py-2 text-[12.5px] font-medium capitalize transition ${
                active
                  ? "border-ink bg-ink text-white"
                  : "border-slate-300 bg-white text-slate-700 hover:bg-slate-50"
              }`}
            >
              {option}
            </button>
          );
        })}
        <button
          type="button"
          onClick={logs.reload}
          className="flex items-center gap-2 whitespace-nowrap rounded-none border border-slate-300 bg-white px-3.5 py-2 text-[12.5px] font-medium text-slate-700 transition hover:bg-slate-50"
        >
          <RefreshCw size={13} />
          Refresh
        </button>
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
            Event stream
          </span>
          <span className="ml-auto font-mono text-[11.5px] text-slate-600">
            {rows.length} of {total} events
          </span>
        </div>

        <DataState
          loading={logs.loading}
          error={logs.error}
          isEmpty={!rows.length}
          onRetry={logs.reload}
          dark
          rows={6}
          empty={
            <div className="px-5 py-10 text-center">
              <div className="text-sm font-semibold text-white">No events match this filter</div>
              <button
                type="button"
                onClick={() => {
                  setLevel("all");
                  clearTenant();
                }}
                className="mt-3.5 rounded-none border border-emerald-500 bg-transparent px-4 py-2 text-[12.5px] font-semibold text-emerald-400"
              >
                Reset filters
              </button>
            </div>
          }
        >
          <div className="overflow-x-auto">
            <table className="w-full min-w-[900px] border-collapse">
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id}>
                    <td className="whitespace-nowrap border-b border-slate-900 px-5 py-2.5 align-top font-mono text-xs text-slate-500">
                      {row.created_at?.slice(11, 19)}
                    </td>
                    <td className="border-b border-slate-900 px-2.5 py-2.5 align-top">
                      <span
                        className={`whitespace-nowrap rounded-none border px-2 py-0.5 font-mono text-[10.5px] font-semibold uppercase tracking-[0.1em] ${
                          LOG_LEVEL_STYLE[row.level] ?? LOG_LEVEL_STYLE.info
                        }`}
                      >
                        {row.level}
                      </span>
                    </td>
                    <td className="whitespace-nowrap border-b border-slate-900 px-2.5 py-2.5 align-top font-mono text-xs text-slate-400">
                      {row.tenant_name ?? "platform"}
                    </td>
                    <td className="border-b border-slate-900 px-5 py-2.5 font-mono text-[12.5px] leading-relaxed text-slate-200">
                      <span className="text-emerald-400">{row.action}</span> {renderMeta(row)}
                      {row.actor_email && (
                        <span className="text-slate-500"> actor={row.actor_email}</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </DataState>
      </div>
    </main>
  );
}
