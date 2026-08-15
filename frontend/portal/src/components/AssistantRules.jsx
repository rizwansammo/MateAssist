import { useCallback, useEffect, useState } from "react";
import { ChevronDown, ChevronUp, Info, Plus, Trash2 } from "lucide-react";

import { usePortal } from "../context/PortalContext.jsx";
import { rulesApi } from "../lib/rules.js";

/**
 * Workspace instructions, one rule per row (D-167).
 *
 * This replaces a single 4000-character textarea. Same text reaches the model -
 * the rules are joined into one block before the prompt is built - so the
 * change is entirely about whether a person will write them.
 *
 * A blank box that size reads as homework. "Add a rule" asks for one sentence,
 * and someone who writes one usually writes three.
 *
 * The budget meter is not decoration. Every enabled rule rides in EVERY
 * question, so a long list is a permanent per-answer cost and pushes runbook
 * content further down the prompt. A textarea could only show a total; a list
 * can show what each rule costs, which is the number that changes behaviour.
 */

const LIMIT = 4000;
const RULE_LIMIT = 500;

const PLACEHOLDERS = [
  "We use Microsoft Entra ID, not on-premise Active Directory.",
  "Never tell a user to reset their own password - send them to portal.example.com.",
  "Office hours are 9-6 GMT. Outside those, say the L2 team picks it up next working day."
];

export function AssistantRules() {
  const { notify } = usePortal();
  const [rules, setRules] = useState([]);
  const [loading, setLoading] = useState(true);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      const payload = await rulesApi.list();
      setRules(Array.isArray(payload) ? payload : (payload?.results ?? []));
    } catch (error) {
      notify("Could not load your rules", error.message, "warn");
    } finally {
      setLoading(false);
    }
  }, [notify]);

  useEffect(() => {
    load();
  }, [load]);

  const used = rules.filter((rule) => rule.enabled).reduce((sum, r) => sum + r.text.length, 0);
  const remaining = LIMIT - used;

  const add = async (event) => {
    event.preventDefault();
    const text = draft.trim();
    if (!text) return;

    setSaving(true);
    try {
      const created = await rulesApi.create(text);
      setRules((prev) => [...prev, created]);
      setDraft("");
    } catch (error) {
      notify("Could not add that rule", describe(error), "warn");
    } finally {
      setSaving(false);
    }
  };

  const patch = async (rule, fields) => {
    // Optimistic: a toggle that waits for a round trip feels broken, and the
    // reload on failure puts the truth back.
    setRules((prev) => prev.map((r) => (r.id === rule.id ? { ...r, ...fields } : r)));
    try {
      await rulesApi.update(rule.id, fields);
    } catch (error) {
      notify("Could not save that change", describe(error), "warn");
      load();
    }
  };

  const remove = async (rule) => {
    if (!window.confirm("Delete this rule? To keep the wording, turn it off instead.")) return;
    setRules((prev) => prev.filter((r) => r.id !== rule.id));
    try {
      await rulesApi.remove(rule.id);
    } catch (error) {
      notify("Could not delete that rule", describe(error), "warn");
      load();
    }
  };

  const move = async (index, direction) => {
    const next = [...rules];
    const target = index + direction;
    if (target < 0 || target >= next.length) return;
    [next[index], next[target]] = [next[target], next[index]];
    setRules(next);

    try {
      await rulesApi.reorder(next.map((rule) => rule.id));
    } catch (error) {
      notify("Could not reorder", describe(error), "warn");
      load();
    }
  };

  return (
    <section className="rounded-none border border-hairline bg-white">
      <div className="flex flex-wrap items-center gap-3 border-b border-hairline px-6 py-4">
        <div className="flex-1">
          <div className="text-[15px] font-semibold text-ink">Assistant rules</div>
          <div className="mt-0.5 text-[12.5px] text-slate-500">
            Guidance the assistant follows on every question, alongside your runbooks. Read top
            to bottom.
          </div>
        </div>
        <div className="text-right">
          <div
            className={`font-mono text-[13px] ${remaining < 0 ? "text-red-600" : "text-slate-500"}`}
          >
            {used} / {LIMIT}
          </div>
          <div className="text-[11px] text-slate-400">
            {rules.filter((r) => r.enabled).length} active
          </div>
        </div>
      </div>

      <div className="flex flex-col">
        {loading && <div className="px-6 py-8 text-[13px] text-slate-400">Loading rules...</div>}

        {!loading && rules.length === 0 && (
          <div className="px-6 py-8 text-[13px] leading-relaxed text-slate-500">
            No rules yet. Add things a runbook cannot say &mdash; the tools you actually use,
            local policy, how you want the assistant to sound.
          </div>
        )}

        {rules.map((rule, index) => (
          <div
            key={rule.id}
            className={`flex items-start gap-3 border-b border-slate-100 px-6 py-3.5 ${
              rule.enabled ? "" : "bg-slate-50"
            }`}
          >
            <div className="flex flex-none flex-col pt-0.5">
              <button
                type="button"
                aria-label="Move up"
                disabled={index === 0}
                onClick={() => move(index, -1)}
                className="rounded-none p-0.5 text-slate-300 transition hover:text-ink disabled:opacity-30"
              >
                <ChevronUp size={14} />
              </button>
              <button
                type="button"
                aria-label="Move down"
                disabled={index === rules.length - 1}
                onClick={() => move(index, 1)}
                className="rounded-none p-0.5 text-slate-300 transition hover:text-ink disabled:opacity-30"
              >
                <ChevronDown size={14} />
              </button>
            </div>

            <textarea
              rows={Math.min(4, Math.max(1, Math.ceil(rule.text.length / 90)))}
              value={rule.text}
              maxLength={RULE_LIMIT}
              onChange={(event) =>
                setRules((prev) =>
                  prev.map((r) => (r.id === rule.id ? { ...r, text: event.target.value } : r))
                )
              }
              // Saved on blur, not on every keystroke: one request per rule
              // edited rather than one per character typed.
              onBlur={(event) => {
                const text = event.target.value.trim();
                if (text && text !== rule.text) patch(rule, { text });
              }}
              className={`min-w-0 flex-1 resize-none rounded-none border border-transparent bg-transparent px-2 py-1 text-[13.5px] leading-relaxed outline-none transition focus:border-hairline focus:bg-white ${
                rule.enabled ? "text-ink" : "text-slate-400 line-through decoration-slate-300"
              }`}
            />

            <label
              className="flex flex-none cursor-pointer items-center gap-2 pt-1 text-[11.5px] text-slate-500"
              title="Turn off without losing the wording"
            >
              <input
                type="checkbox"
                checked={rule.enabled}
                onChange={(event) => patch(rule, { enabled: event.target.checked })}
                className="h-3.5 w-3.5 rounded-none accent-emerald-600"
              />
              On
            </label>

            <button
              type="button"
              aria-label="Delete rule"
              onClick={() => remove(rule)}
              className="flex-none rounded-none p-1 text-slate-300 transition hover:text-red-600"
            >
              <Trash2 size={14} />
            </button>
          </div>
        ))}
      </div>

      <form onSubmit={add} className="flex items-start gap-3 px-6 py-4">
        <textarea
          rows={2}
          value={draft}
          maxLength={RULE_LIMIT}
          onChange={(event) => setDraft(event.target.value)}
          placeholder={PLACEHOLDERS[rules.length % PLACEHOLDERS.length]}
          className="min-w-0 flex-1 resize-none rounded-none border border-hairline bg-white px-3.5 py-2.5 text-[13.5px] leading-relaxed text-ink outline-none transition placeholder:text-slate-300 focus:border-emerald-600"
        />
        <button
          type="submit"
          disabled={saving || !draft.trim()}
          className="flex flex-none items-center gap-1.5 rounded-none border border-ink bg-ink px-4 py-2.5 text-[13px] font-semibold text-white transition hover:bg-slate-800 disabled:opacity-40"
        >
          <Plus size={14} />
          {saving ? "Adding..." : "Add rule"}
        </button>
      </form>

      {/*
        Stated plainly rather than left as a surprise. An admin who believes they
        can turn off escalation will write it, watch it not happen, and conclude
        the product is broken.
      */}
      <div className="mx-6 mb-5 flex gap-3 rounded-none border border-hairline bg-slate-50 p-4">
        <Info size={16} className="mt-0.5 flex-none text-slate-400" strokeWidth={1.8} />
        <div className="text-[12.5px] leading-relaxed text-slate-600">
          <strong className="font-semibold text-ink">What these can and cannot do.</strong> Use
          them for tools you use, local policy, and how you want the assistant to sound. They
          cannot stop it answering from your runbooks, admitting when it does not know
          something, or offering to escalate &mdash; those hold for every workspace. Every
          active rule is sent with every question, so shorter is cheaper.
        </div>
      </div>
    </section>
  );
}

function describe(error) {
  const body = error?.body;
  if (!body) return error?.message ?? "Request failed";
  if (typeof body.detail === "string") return body.detail;

  const first = Object.values(body)[0];
  return Array.isArray(first) ? first[0] : String(first ?? error.message);
}
