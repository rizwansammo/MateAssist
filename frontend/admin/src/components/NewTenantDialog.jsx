import { useState } from "react";
import { Building2, Check, Copy, X } from "lucide-react";

import { useAdmin } from "../context/AdminContext.jsx";
import { platformApi } from "../lib/platform.js";

/**
 * Create a workspace and its first administrator (D-173).
 *
 * This button used to show a toast saying provisioning "arrives with the
 * subscription flow" - so onboarding a customer meant a management command over
 * SSH, and a second customer was blocked on someone with server access being
 * awake.
 *
 * Both objects are created in one request and one transaction. A workspace with
 * no administrator cannot be signed into and appears in nobody's list, so a
 * half-finished create leaves a row only the database knows about.
 */

const FIELD =
  "w-full rounded-none border border-hairline bg-white px-3.5 py-2.5 text-[13.5px] " +
  "text-ink outline-none transition placeholder:text-slate-300 focus:border-emerald-600";

const LABEL = "mb-1.5 block text-[12px] font-semibold uppercase tracking-[0.1em] text-slate-500";

export function NewTenantDialog({ onClose, onCreated }) {
  const { notify } = useAdmin();
  const [form, setForm] = useState({
    name: "",
    admin_email: "",
    admin_name: "",
    admin_password: "",
    plan: "GROWTH",
    support_email: ""
  });
  const [saving, setSaving] = useState(false);
  const [created, setCreated] = useState(null);
  const [copied, setCopied] = useState(false);

  const set = (field) => (event) => setForm({ ...form, [field]: event.target.value });

  const submit = async (event) => {
    event.preventDefault();
    setSaving(true);
    try {
      const result = await platformApi.createTenant({ ...form, name: form.name.trim() });
      setCreated(result);
      onCreated?.();
    } catch (error) {
      notify("Could not create that workspace", describe(error), "warn");
    } finally {
      setSaving(false);
    }
  };

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(
        `${created.subdomain}\n${created.owner_email}\n${created.owner_password}`
      );
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard access can be refused; everything is on screen to read.
    }
  };

  // Created: the panel becomes the one and only sight of the password.
  if (created) {
    return (
      <Shell onClose={onClose} title="Workspace created" subtitle={created.name}>
        <div className="grid gap-4 px-6 py-5">
          <div className="border border-emerald-200 bg-emerald-50 p-4">
            <div className="text-[13px] font-semibold text-emerald-900">
              Send these to the administrator now
            </div>
            <div className="mt-0.5 text-[12px] text-emerald-800">
              The password is shown once. Nothing can display it again.
            </div>

            <dl className="mt-3 grid gap-2 font-mono text-[13px]">
              {[
                ["Sign in at", created.subdomain],
                ["Email", created.owner_email],
                ["Password", created.owner_password]
              ].map(([label, value]) => (
                <div key={label} className="flex flex-wrap items-baseline gap-2">
                  <dt className="w-[80px] flex-none font-sans text-[11.5px] uppercase tracking-wider text-emerald-700">
                    {label}
                  </dt>
                  <dd className="min-w-0 break-all border border-emerald-200 bg-white px-2 py-1 text-ink">
                    {value}
                  </dd>
                </div>
              ))}
            </dl>

            <button
              type="button"
              onClick={copy}
              className="mt-3 flex items-center gap-1.5 rounded-none border border-emerald-700 bg-emerald-700 px-3.5 py-2 text-[12.5px] font-semibold text-white transition hover:bg-emerald-800"
            >
              {copied ? <Check size={14} /> : <Copy size={14} />}
              {copied ? "Copied" : "Copy all three"}
            </button>
          </div>
        </div>

        <div className="flex justify-end border-t border-hairline px-6 py-4">
          <button
            type="button"
            onClick={onClose}
            className="rounded-none border border-ink bg-ink px-5 py-2.5 text-[13px] font-semibold text-white transition hover:bg-slate-800"
          >
            Done
          </button>
        </div>
      </Shell>
    );
  }

  return (
    <Shell
      onClose={onClose}
      title="New workspace"
      subtitle="Creates the workspace and its first administrator."
      onSubmit={submit}
    >
      <div className="grid gap-5 px-6 py-5">
        <div>
          <label htmlFor="t_name" className={LABEL}>
            Company name
          </label>
          <input
            id="t_name"
            required
            value={form.name}
            onChange={set("name")}
            placeholder="Acme Industries"
            className={FIELD}
          />
          {/* The subdomain is derived server-side and de-duplicated, so two
              customers called Acme both get a working address. */}
          <p className="mt-1.5 text-[11.5px] text-slate-400">
            Their sign-in address is derived from this.
          </p>
        </div>

        <div className="grid gap-5 sm:grid-cols-2">
          <div>
            <label htmlFor="t_admin_email" className={LABEL}>
              Administrator email
            </label>
            <input
              id="t_admin_email"
              type="email"
              required
              value={form.admin_email}
              onChange={set("admin_email")}
              placeholder="it@acme.com"
              className={FIELD}
            />
          </div>
          <div>
            <label htmlFor="t_admin_name" className={LABEL}>
              Administrator name
            </label>
            <input
              id="t_admin_name"
              value={form.admin_name}
              onChange={set("admin_name")}
              className={FIELD}
            />
          </div>
        </div>

        <div className="grid gap-5 sm:grid-cols-2">
          <div>
            <label htmlFor="t_plan" className={LABEL}>
              Plan
            </label>
            <select id="t_plan" value={form.plan} onChange={set("plan")} className={FIELD}>
              <option value="GROWTH">Growth</option>
              <option value="PRO">Pro</option>
              <option value="ENTERPRISE">Enterprise</option>
            </select>
          </div>
          <div>
            <label htmlFor="t_password" className={LABEL}>
              Password
            </label>
            <input
              id="t_password"
              type="text"
              value={form.admin_password}
              onChange={set("admin_password")}
              placeholder="Leave blank to generate"
              className={`${FIELD} font-mono`}
            />
          </div>
        </div>

        <div>
          <label htmlFor="t_support" className={LABEL}>
            Helpdesk email
          </label>
          <input
            id="t_support"
            type="email"
            value={form.support_email}
            onChange={set("support_email")}
            placeholder="helpdesk@acme.com"
            className={FIELD}
          />
          <p className="mt-1.5 text-[11.5px] text-slate-400">
            Where escalations go. Their administrator can change it later.
          </p>
        </div>
      </div>

      <div className="flex justify-end gap-3 border-t border-hairline px-6 py-4">
        <button
          type="button"
          onClick={onClose}
          className="rounded-none border border-slate-300 bg-white px-4 py-2.5 text-[13px] font-medium text-slate-700 transition hover:bg-slate-50"
        >
          Cancel
        </button>
        <button
          type="submit"
          disabled={saving || !form.name.trim() || !form.admin_email.trim()}
          className="rounded-none border border-ink bg-ink px-5 py-2.5 text-[13px] font-semibold text-white transition hover:bg-slate-800 disabled:opacity-60"
        >
          {saving ? "Creating..." : "Create workspace"}
        </button>
      </div>
    </Shell>
  );
}

function Shell({ title, subtitle, onClose, onSubmit, children }) {
  const Tag = onSubmit ? "form" : "div";
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/50 p-4">
      <Tag
        onSubmit={onSubmit}
        className="max-h-[90vh] w-full max-w-[560px] overflow-y-auto rounded-none border border-hairline bg-white"
      >
        <div className="flex items-start justify-between border-b border-hairline px-6 py-4">
          <div className="flex items-center gap-2.5">
            <Building2 size={16} strokeWidth={1.8} className="text-slate-500" />
            <div>
              <div className="text-[15px] font-semibold text-ink">{title}</div>
              <div className="mt-0.5 text-[12.5px] text-slate-500">{subtitle}</div>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-none border border-hairline bg-white p-1.5 text-slate-500 transition hover:bg-slate-50"
          >
            <X size={15} />
          </button>
        </div>
        {children}
      </Tag>
    </div>
  );
}

function describe(error) {
  const body = error?.body;
  if (!body) return error?.message ?? "Request failed";
  if (typeof body.detail === "string") return body.detail;

  const first = Object.values(body)[0];
  return Array.isArray(first) ? first[0] : String(first ?? error.message);
}
