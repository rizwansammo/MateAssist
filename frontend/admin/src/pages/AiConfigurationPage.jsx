import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, ArrowRight, Lock, Plus, RefreshCw, ShieldCheck } from "lucide-react";
import { Pill } from "@mateassist/ui";

import { KeyModal } from "../components/KeyModal.jsx";
import { useAdmin } from "../context/AdminContext.jsx";
import { vaultApi } from "../lib/vault.js";
import {
  ENGINES,
  ENGINE_ASSIGNMENT,
  KEY_STATUS_LABEL,
  KEY_STATUS_TONE
} from "../lib/engines.js";

/**
 * AI Configuration - two dedicated sections (D-092), now backed by the live
 * credential vault.
 *
 * The plaintext of a key exists in this file for exactly as long as it takes to
 * POST it. Nothing reads a secret back: the API has no endpoint that returns
 * one, so the tables below can only ever show `last4` (D-072).
 */

function EngineSection({ engine, keys, loading, onAdd, onRotate, onRevoke, onPurge }) {
  const live = keys.filter((k) => k.status !== "REVOKED");
  const active = live.filter((k) => k.is_available).length;
  const limited = live.filter((k) => k.status === "RATE_LIMITED").length;

  return (
    <section
      className={`rounded-none border border-hairline border-t-[3px] ${engine.accent} bg-white`}
    >
      <div className="flex flex-wrap items-start justify-between gap-4 border-b border-hairline px-6 py-5">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-3">
            <h2 className="text-[18px] font-semibold tracking-tight text-ink">{engine.section}</h2>
            <Pill tone={engine.tone} dot={false}>
              {live.length} key{live.length === 1 ? "" : "s"}
            </Pill>
          </div>
          <p className="mt-2 max-w-[560px] text-[13px] leading-relaxed text-slate-500">
            {engine.purpose}
          </p>
          <div className="mt-2 text-xs text-slate-500">{engine.role}</div>
        </div>
        <button
          type="button"
          onClick={() => onAdd(engine)}
          className="flex flex-none items-center gap-2 whitespace-nowrap rounded-none bg-emerald-600 px-4 py-2.5 text-[13px] font-semibold text-white transition hover:bg-emerald-700"
        >
          <Plus size={15} />
          Add key
        </button>
      </div>

      <div className="grid gap-px border-b border-hairline bg-hairline sm:grid-cols-2">
        <div className="bg-emerald-50/40 px-6 py-4">
          <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.1em] text-emerald-700">
            <ShieldCheck size={13} />
            Receives
          </div>
          <p className="mt-1.5 text-[12.5px] leading-relaxed text-slate-700">{engine.receives}</p>
        </div>
        <div className="bg-slate-50 px-6 py-4">
          <div className="text-[11px] font-semibold uppercase tracking-[0.1em] text-slate-500">
            Never receives
          </div>
          <p className="mt-1.5 text-[12.5px] leading-relaxed text-slate-700">
            {engine.neverReceives}
          </p>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-4 border-b border-hairline px-6 py-3.5">
        <span className="text-[12.5px] text-slate-500">
          {loading ? "Loading pool..." : `${active}/${live.length} keys usable`}
        </span>
        {limited > 0 && <Pill tone="warn">{limited} rate-limited</Pill>}
        {!loading && live.length === 0 && (
          <span className="inline-flex items-center gap-2 text-[12.5px] font-medium text-amber-700">
            <AlertTriangle size={14} />
            This engine cannot serve requests until a key is added.
          </span>
        )}
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[860px] border-collapse">
          <thead>
            <tr className="bg-slate-50 text-left text-[10.5px] font-semibold uppercase tracking-[0.12em] text-slate-500">
              <th className="border-b border-hairline px-6 py-3">Label</th>
              <th className="border-b border-hairline px-4 py-3">Key</th>
              <th className="border-b border-hairline px-4 py-3">Status</th>
              <th className="border-b border-hairline px-4 py-3 text-right">Requests today</th>
              <th className="border-b border-hairline px-4 py-3">Last used</th>
              <th className="border-b border-hairline px-6 py-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {keys.map((key) => (
              <tr key={key.id}>
                <td className="border-b border-slate-100 px-6 py-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-[13.5px] font-medium text-ink">{key.label}</span>
                    <span className="rounded-none border border-hairline bg-slate-50 px-1.5 py-0.5 font-mono text-[10.5px] uppercase tracking-wider text-slate-600">
                      {key.provider}
                    </span>
                  </div>
                  {/* The RESOLVED model, not the override - an operator needs to
                      see what will actually be called, not a blank field. */}
                  <div className="mt-0.5 font-mono text-[11.5px] text-slate-500">
                    {key.resolved_model}
                  </div>
                  <div className="mt-0.5 text-[11.5px] text-slate-400">
                    Added {new Date(key.created_at).toLocaleDateString("en-GB")} - quota{" "}
                    {key.daily_quota ?? "unmetered"}
                  </div>
                </td>
                <td className="border-b border-slate-100 px-4 py-4">
                  <div className="inline-flex items-center gap-2.5 rounded-none border border-hairline bg-slate-50 px-2.5 py-1.5">
                    <Lock size={13} className="text-slate-500" />
                    <span className="font-mono text-[12.5px] tracking-wide text-slate-700">
                      {key.masked}
                    </span>
                  </div>
                </td>
                <td className="border-b border-slate-100 px-4 py-4">
                  <Pill tone={KEY_STATUS_TONE[key.status] ?? "off"}>
                    {KEY_STATUS_LABEL[key.status] ?? key.status}
                  </Pill>
                </td>
                <td className="border-b border-slate-100 px-4 py-4 text-right font-mono text-[13px] text-ink">
                  {key.requests_today}
                </td>
                <td className="whitespace-nowrap border-b border-slate-100 px-4 py-4 text-[13px] text-slate-500">
                  {key.last_used_at
                    ? new Date(key.last_used_at).toLocaleString("en-GB")
                    : "never"}
                </td>
                <td className="border-b border-slate-100 px-6 py-4">
                  <div className="flex justify-end gap-2">
                    <button
                      type="button"
                      onClick={() => onRotate(engine, key)}
                      className="whitespace-nowrap rounded-none border border-ink bg-white px-3 py-1.5 text-xs font-semibold text-ink transition hover:bg-slate-50"
                    >
                      Rotate
                    </button>
                    <button
                      type="button"
                      onClick={() =>
                        key.status === "REVOKED" ? onPurge(key) : onRevoke(key)
                      }
                      className="whitespace-nowrap rounded-none border border-red-200 bg-white px-3 py-1.5 text-xs font-medium text-red-700 transition hover:bg-red-50"
                    >
                      {key.status === "REVOKED" ? "Purge" : "Revoke"}
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {!loading && keys.length === 0 && (
              <tr>
                <td colSpan={6} className="px-6 py-10 text-center text-[13.5px] text-slate-500">
                  No keys configured for this engine.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export default function AiConfigurationPage() {
  const { notify } = useAdmin();
  const [keys, setKeys] = useState({ TEXT: [], VISION: [] });
  const [loading, setLoading] = useState(true);
  const [modal, setModal] = useState(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const rows = await vaultApi.list();
      const list = Array.isArray(rows) ? rows : (rows?.results ?? []);
      setKeys({
        TEXT: list.filter((k) => k.engine === "TEXT"),
        VISION: list.filter((k) => k.engine === "VISION")
      });
    } catch (error) {
      notify("Could not load the vault", error?.message ?? "Request failed", "warn");
    } finally {
      setLoading(false);
    }
  }, [notify]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const save = async (form) => {
    const { engineId, keyId, ...rest } = form;
    try {
      if (keyId) {
        await vaultApi.rotate(keyId, rest);
        notify("Key rotated", `${rest.label} is live - audit event written`);
      } else {
        await vaultApi.create({ engine: engineId, ...rest });
        notify("Key added", `${rest.label} joined the ${engineId} pool`);
      }
      await refresh();
    } catch (error) {
      notify("Save failed", describe(error), "warn");
    }
  };

  const revoke = async (key) => {
    try {
      await vaultApi.revoke(key.id);
      notify("Key revoked", `${key.label} is out of rotation`, "warn");
      await refresh();
    } catch (error) {
      notify("Revoke failed", describe(error), "warn");
    }
  };

  const purge = async (key) => {
    try {
      await vaultApi.purge(key.id);
      notify("Key purged", `${key.label} removed from the vault`, "warn");
      await refresh();
    } catch (error) {
      notify("Purge failed", describe(error), "warn");
    }
  };

  return (
    <main className="flex flex-col gap-6 px-6 pb-12 pt-7">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="mb-2 text-[28px] font-semibold tracking-tight text-ink">
            AI configuration
          </h1>
          <p className="max-w-[720px] text-sm text-slate-500">
            Central credential vault for the two engines. Keys are write-only - the plaintext is
            never returned to the browser after save, and only the last four characters are ever
            displayed again.
          </p>
        </div>
        <button
          type="button"
          onClick={refresh}
          className="flex flex-none items-center gap-2 rounded-none border border-slate-300 bg-white px-3.5 py-2 text-[12.5px] font-medium text-slate-700 transition hover:bg-slate-50"
        >
          <RefreshCw size={14} />
          Refresh
        </button>
      </div>

      {ENGINES.map((engine) => (
        <EngineSection
          key={engine.id}
          engine={engine}
          keys={keys[engine.id] ?? []}
          loading={loading}
          onAdd={(e) => setModal({ engine: e, existingKey: null })}
          onRotate={(e, key) => setModal({ engine: e, existingKey: key })}
          onRevoke={revoke}
          onPurge={purge}
        />
      ))}

      <div className="flex flex-col gap-4 rounded-none border border-ink bg-ink p-6">
        <div>
          <div className="text-[15px] font-semibold text-white">Engine assignment</div>
          <div className="mt-1 text-[12.5px] text-slate-500">
            Fixed by architecture, not configuration. There is no fallback provider.
          </div>
        </div>
        <div className="flex flex-col gap-px rounded-none border border-slate-800 bg-slate-800">
          {ENGINE_ASSIGNMENT.map((row) => (
            <div key={row.task} className="flex flex-wrap items-center gap-3 bg-[#0F1B2D] px-4 py-3">
              <span className="min-w-[116px] text-xs text-slate-400">{row.task}</span>
              <ArrowRight size={14} className="text-slate-700" />
              <span className={`text-[12.5px] font-semibold ${row.colour}`}>{row.engine}</span>
            </div>
          ))}
        </div>
        <div className="rounded-none border border-slate-800 bg-[#101C2E] px-4 py-3.5">
          <div className="text-[11px] font-semibold uppercase tracking-[0.1em] text-emerald-400">
            Isolation guarantee
          </div>
          <p className="mt-2 text-[12.5px] leading-relaxed text-slate-400">
            Images reach the vision engine and stop there; only the text it returns continues to
            the text engine. Enforced at the engine client boundary, where the text client has no
            parameter capable of carrying an image - whichever provider serves the role.
          </p>
        </div>
      </div>

      {modal && (
        <KeyModal
          engine={modal.engine}
          existingKey={modal.existingKey}
          onClose={() => setModal(null)}
          onSave={save}
        />
      )}
    </main>
  );
}

function describe(error) {
  const body = error?.body;
  if (!body) return error?.message ?? "Request failed";
  if (typeof body === "string") return body;
  if (body.detail) return String(body.detail);
  const first = Object.entries(body)[0];
  return first ? `${first[0]}: ${[].concat(first[1]).join(", ")}` : "Request failed";
}
