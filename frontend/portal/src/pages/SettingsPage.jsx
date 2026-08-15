import { useCallback, useEffect, useState } from "react";
import { Info, Save } from "lucide-react";

import { usePortal } from "../context/PortalContext.jsx";
import { workspaceApi } from "../lib/workspace.js";

/**
 * Workspace settings (D-151). Administrators only - the route guard bounces
 * everyone else, and the API refuses them independently.
 *
 * The instructions box is the interesting field. It is policy the runbooks
 * cannot express - which identity provider you use, whether to send people to a
 * self-service portal, what to say outside office hours - and it is injected
 * into every prompt beneath the core rules.
 */
export default function SettingsPage() {
  const { notify } = usePortal();

  const [instructions, setInstructions] = useState("");
  const [supportEmail, setSupportEmail] = useState("");
  const [limit, setLimit] = useState(4000);
  const [workspace, setWorkspace] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await workspaceApi.settings();
      setWorkspace(data);
      setInstructions(data.assistant_instructions ?? "");
      setSupportEmail(data.support_email ?? "");
      setLimit(data.assistant_instructions_limit ?? 4000);
      setDirty(false);
    } catch (error) {
      notify("Could not load settings", error.message, "warn");
    } finally {
      setLoading(false);
    }
  }, [notify]);

  useEffect(() => {
    load();
  }, [load]);

  const save = async () => {
    setSaving(true);
    try {
      const data = await workspaceApi.save({
        assistant_instructions: instructions,
        support_email: supportEmail
      });
      setWorkspace(data);
      setDirty(false);
      notify("Settings saved", "The assistant uses these from the next question onward.");
    } catch (error) {
      notify("Could not save", error.message, "warn");
    } finally {
      setSaving(false);
    }
  };

  const remaining = limit - instructions.length;
  const over = remaining < 0;

  return (
    <main className="flex flex-col gap-6 px-7 pb-12 pt-8">
      <div>
        <h1 className="mb-2 text-[28px] font-semibold tracking-tight text-ink">
          Workspace settings
        </h1>
        <p className="text-sm text-slate-500">
          {workspace ? `${workspace.name} - ${workspace.slug}` : "Loading..."}
        </p>
      </div>

      {/* ---- assistant instructions ---- */}
      <section className="rounded-none border border-hairline bg-white">
        <div className="border-b border-hairline px-6 py-4">
          <div className="text-[15px] font-semibold text-ink">Assistant instructions</div>
          <div className="mt-0.5 text-[12.5px] text-slate-500">
            Guidance the assistant follows on every question, alongside your runbooks.
          </div>
        </div>

        <div className="px-6 py-5">
          <label htmlFor="instructions" className="sr-only">
            Assistant instructions
          </label>
          <textarea
            id="instructions"
            rows={11}
            value={instructions}
            disabled={loading}
            onChange={(event) => {
              setInstructions(event.target.value);
              setDirty(true);
            }}
            placeholder={
              "We use Microsoft Entra ID, not on-premise Active Directory.\n\n" +
              "Never tell a user to reset their own password directly - always send them to " +
              "the self-service portal at portal.example.com.\n\n" +
              "Our office hours are 9-6 GMT. Outside those hours, say the L2 team will pick " +
              "it up the next working day."
            }
            className={`w-full rounded-none border bg-white p-3.5 font-mono text-[13px] leading-relaxed text-ink outline-none transition placeholder:text-slate-300 focus:border-emerald-600 ${
              over ? "border-red-400" : "border-hairline"
            }`}
          />

          <div className="mt-2 flex flex-wrap items-center gap-3">
            <span
              className={`font-mono text-[11.5px] ${over ? "text-red-600" : "text-slate-400"}`}
            >
              {instructions.length} / {limit}
            </span>
            {over && (
              <span className="text-[12px] text-red-600">
                Too long by {Math.abs(remaining)} characters.
              </span>
            )}
          </div>

          {/*
            Stated plainly in the UI rather than left as a surprise. An admin who
            believes they can turn off escalation will write it, watch it not
            happen, and conclude the product is broken.
          */}
          <div className="mt-5 flex gap-3 rounded-none border border-hairline bg-slate-50 p-4">
            <Info size={16} className="mt-0.5 flex-none text-slate-400" strokeWidth={1.8} />
            <div className="text-[12.5px] leading-relaxed text-slate-600">
              <strong className="font-semibold text-ink">What this can and cannot do.</strong> Use
              it for tools you use, local policy, and how you want the assistant to sound. It
              cannot stop the assistant answering from your runbooks, admitting when it does not
              know something, or offering to escalate &mdash; those hold for every workspace.
            </div>
          </div>
        </div>
      </section>

      {/* ---- escalation address ---- */}
      <section className="rounded-none border border-hairline bg-white">
        <div className="border-b border-hairline px-6 py-4">
          <div className="text-[15px] font-semibold text-ink">Escalation address</div>
          <div className="mt-0.5 text-[12.5px] text-slate-500">
            Where the assistant sends an issue it cannot resolve.
          </div>
        </div>
        <div className="px-6 py-5">
          <label htmlFor="support" className="sr-only">
            Escalation address
          </label>
          <input
            id="support"
            type="email"
            value={supportEmail}
            disabled={loading}
            onChange={(event) => {
              setSupportEmail(event.target.value);
              setDirty(true);
            }}
            placeholder="helpdesk@yourcompany.com"
            className="w-full max-w-[420px] rounded-none border border-hairline bg-white px-3.5 py-2.5 text-[13.5px] text-ink outline-none transition placeholder:text-slate-300 focus:border-emerald-600"
          />
          <p className="mt-2 text-[12px] text-slate-400">
            The reply goes to whoever asked, so your engineer can answer them directly.
          </p>
        </div>
      </section>

      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={save}
          disabled={saving || loading || over || !dirty}
          className="flex items-center gap-2 rounded-none bg-emerald-600 px-5 py-3 text-[13.5px] font-semibold text-white transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:bg-slate-300"
        >
          <Save size={15} strokeWidth={1.9} />
          {saving ? "Saving..." : "Save changes"}
        </button>
        {dirty && !over && <span className="text-[12.5px] text-slate-500">Unsaved changes</span>}
      </div>
    </main>
  );
}
