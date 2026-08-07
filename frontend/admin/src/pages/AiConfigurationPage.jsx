import { useState } from "react";
import { ArrowRight, Lock, Plus, ShieldCheck } from "lucide-react";
import { Pill } from "@mateassist/ui";

import { KeyModal } from "../components/KeyModal.jsx";
import { useAdmin } from "../context/AdminContext.jsx";
import { ENGINES, ENGINE_ASSIGNMENT, KEY_STATUS_TONE } from "../seed/engines.js";

/**
 * AI Configuration - restructured to the two-section specification (D-092).
 *
 * One dedicated section for the Text & Reasoning Engine (DeepSeek) and one for
 * the Vision & OCR Engine (Gemini). The prototype's Groq and OpenAI cards, the
 * tri-provider routing panel and the orchestration policy toggles are gone
 * entirely (D-044, D-085, D-086) - removed, not hidden behind a flag.
 */

function EngineSection({ engine, keys, stats, onAdd, onRotate, onRevoke }) {
  return (
    <section className={`rounded-none border border-hairline border-t-[3px] ${engine.accent} bg-white`}>
      <div className="flex flex-wrap items-start justify-between gap-4 border-b border-hairline px-6 py-5">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-3">
            <h2 className="text-[18px] font-semibold tracking-tight text-ink">{engine.section}</h2>
            <Pill tone={engine.tone} dot={false}>
              {engine.provider}
            </Pill>
          </div>
          <p className="mt-2 max-w-[560px] text-[13px] leading-relaxed text-slate-500">
            {engine.purpose}
          </p>
          <div className="mt-2 font-mono text-xs text-slate-500">{engine.models.join("  |  ")}</div>
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

      {/*
        The engine contract, stated in the operator-facing UI. This separation is
        the product's central safety property (D-042/D-043), so someone standing
        in the key vault should be able to read what each engine may see.
      */}
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
          {stats.active}/{stats.pool} keys healthy
        </span>
        {stats.limited > 0 && (
          <Pill tone="warn">{stats.limited} rate-limited</Pill>
        )}
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[820px] border-collapse">
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
                  <div className="text-[13.5px] font-medium text-ink">{key.label}</div>
                  <div className="mt-0.5 text-[11.5px] text-slate-400">
                    Added {key.added} - quota {key.quota}
                  </div>
                </td>
                <td className="border-b border-slate-100 px-4 py-4">
                  {/*
                    Only the last four characters exist client-side. There is no
                    endpoint that returns the plaintext (D-072).
                  */}
                  <div className="inline-flex items-center gap-2.5 rounded-none border border-hairline bg-slate-50 px-2.5 py-1.5">
                    <Lock size={13} className="text-slate-500" />
                    <span className="font-mono text-[12.5px] tracking-wide text-slate-700">
                      {"•".repeat(11)}
                      {key.last4}
                    </span>
                  </div>
                </td>
                <td className="border-b border-slate-100 px-4 py-4">
                  <Pill tone={KEY_STATUS_TONE[key.status] ?? "off"}>{key.status}</Pill>
                </td>
                <td className="border-b border-slate-100 px-4 py-4 text-right font-mono text-[13px] text-ink">
                  {key.requests}
                </td>
                <td className="whitespace-nowrap border-b border-slate-100 px-4 py-4 text-[13px] text-slate-500">
                  {key.lastUsed}
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
                      onClick={() => onRevoke(engine.id, key)}
                      className="whitespace-nowrap rounded-none border border-red-200 bg-white px-3 py-1.5 text-xs font-medium text-red-700 transition hover:bg-red-50"
                    >
                      {key.status === "Revoked" ? "Purge" : "Revoke"}
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {keys.length === 0 && (
              <tr>
                <td colSpan={6} className="px-6 py-10 text-center text-[13.5px] text-slate-500">
                  No {engine.provider} keys configured - this engine cannot serve requests.
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
  const { keys, keyStats, saveKey, revokeKey } = useAdmin();
  const [modal, setModal] = useState(null);

  return (
    <main className="flex flex-col gap-6 px-6 pb-12 pt-7">
      <div>
        <h1 className="mb-2 text-[28px] font-semibold tracking-tight text-ink">AI configuration</h1>
        <p className="max-w-[720px] text-sm text-slate-500">
          Central credential vault for the two engines. Keys are write-only - the plaintext is
          never returned to the browser after save, and only the last four characters are
          displayed again.
        </p>
      </div>

      {ENGINES.map((engine) => (
        <EngineSection
          key={engine.id}
          engine={engine}
          keys={keys[engine.id] ?? []}
          stats={keyStats(engine.id)}
          onAdd={(e) => setModal({ engine: e, existingKey: null })}
          onRotate={(e, key) => setModal({ engine: e, existingKey: key })}
          onRevoke={revokeKey}
        />
      ))}

      {/*
        D-045: routing is deterministic, not policy-driven. Two engines with
        fixed, non-overlapping roles leave nothing to route, so this replaces the
        prototype's "Effective routing" panel and its Groq/OpenAI toggles with a
        read-only statement of the contract.
      */}
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
              <span className={`font-mono text-[12.5px] font-semibold ${row.colour}`}>
                {row.model}
              </span>
            </div>
          ))}
        </div>
        <div className="rounded-none border border-slate-800 bg-[#101C2E] px-4 py-3.5">
          <div className="text-[11px] font-semibold uppercase tracking-[0.1em] text-emerald-400">
            Isolation guarantee
          </div>
          <p className="mt-2 text-[12.5px] leading-relaxed text-slate-400">
            Images reach Gemini and stop there; only the text it returns continues to DeepSeek.
            Enforced at the engine client boundary, where the text client has no parameter capable
            of carrying an image.
          </p>
        </div>
      </div>

      {modal && (
        <KeyModal
          engine={modal.engine}
          existingKey={modal.existingKey}
          onClose={() => setModal(null)}
          onSave={saveKey}
        />
      )}
    </main>
  );
}
