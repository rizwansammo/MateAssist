import { useCallback, useEffect, useState } from "react";
import { Info, Mail, Save } from "lucide-react";

import { AssistantRules } from "../components/AssistantRules.jsx";
import { usePortal } from "../context/PortalContext.jsx";
import { workspaceApi } from "../lib/workspace.js";

/**
 * Workspace settings (D-151). Administrators only - the route guard bounces
 * everyone else, and the API refuses them independently.
 *
 * Assistant rules moved into their own component (D-167). What remains here is
 * the workspace's mail configuration and escalation address.
 *
 * The rules were the interesting field. They are policy the runbooks
 * cannot express - which identity provider you use, whether to send people to a
 * self-service portal, what to say outside office hours - and it is injected
 * into every prompt beneath the core rules.
 */
export default function SettingsPage() {
  const { notify } = usePortal();

  const [supportEmail, setSupportEmail] = useState("");
  const [smtp, setSmtp] = useState({
    smtp_host: "",
    smtp_port: 587,
    smtp_username: "",
    smtp_use_tls: true,
    smtp_from_email: ""
  });
  // Held separately from `smtp` because it is only sent when non-empty: an
  // empty string clears the stored credential, so an admin editing the From
  // address must not silently wipe their password by not retyping it.
  const [smtpPassword, setSmtpPassword] = useState("");
  const [passwordSet, setPasswordSet] = useState(false);
  const [testing, setTesting] = useState(false);
  const [workspace, setWorkspace] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await workspaceApi.settings();
      setWorkspace(data);
      setSupportEmail(data.support_email ?? "");
      setSmtp({
        smtp_host: data.smtp_host ?? "",
        smtp_port: data.smtp_port ?? 587,
        smtp_username: data.smtp_username ?? "",
        smtp_use_tls: data.smtp_use_tls ?? true,
        smtp_from_email: data.smtp_from_email ?? ""
      });
      setPasswordSet(Boolean(data.smtp_password_set));
      setSmtpPassword("");
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
      const fields = {
        support_email: supportEmail,
        ...smtp
      };
      // Only send the password when one was actually typed - see the note in
      // workspace.js.
      if (smtpPassword) fields.smtp_password = smtpPassword;

      const data = await workspaceApi.save(fields);
      setWorkspace(data);
      setPasswordSet(Boolean(data.smtp_password_set));
      setSmtpPassword("");
      setDirty(false);
      notify("Settings saved", "The assistant uses these from the next question onward.");
    } catch (error) {
      notify("Could not save", error.message, "warn");
    } finally {
      setSaving(false);
    }
  };

  const setSmtpField = (field, value) => {
    setSmtp((prev) => ({ ...prev, [field]: value }));
    setDirty(true);
  };

  const sendTest = async () => {
    setTesting(true);
    try {
      const result = await workspaceApi.sendTest(supportEmail);
      if (result.sent) {
        notify("Test sent", result.detail);
      } else {
        // The provider's own message is useful here, unlike in the chat: the
        // reader is an administrator debugging their own mail server, and
        // "authentication failed" is the entire answer.
        notify("Test failed", result.detail, "warn");
      }
    } catch (error) {
      notify("Test failed", error.message, "warn");
    } finally {
      setTesting(false);
    }
  };


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

      <AssistantRules />

      {/* ---- outbound mail (D-154) ---- */}
      <section className="rounded-none border border-hairline bg-white">
        <div className="border-b border-hairline px-6 py-4">
          <div className="text-[15px] font-semibold text-ink">Outgoing mail server</div>
          <div className="mt-0.5 text-[12.5px] text-slate-500">
            Escalations are sent from your own mail server, so they arrive as your domain.
          </div>
        </div>

        <div className="grid gap-5 px-6 py-5 md:grid-cols-2">
          <div>
            <label htmlFor="smtp_host" className="mb-1.5 block text-[12px] font-semibold uppercase tracking-[0.1em] text-slate-500">
              Server
            </label>
            <input
              id="smtp_host"
              value={smtp.smtp_host}
              disabled={loading}
              onChange={(event) => setSmtpField("smtp_host", event.target.value)}
              placeholder="smtp.office365.com"
              className="w-full rounded-none border border-hairline bg-white px-3.5 py-2.5 text-[13.5px] text-ink outline-none transition placeholder:text-slate-300 focus:border-emerald-600"
            />
          </div>

          <div>
            <label htmlFor="smtp_port" className="mb-1.5 block text-[12px] font-semibold uppercase tracking-[0.1em] text-slate-500">
              Port
            </label>
            <input
              id="smtp_port"
              type="number"
              value={smtp.smtp_port}
              disabled={loading}
              onChange={(event) => setSmtpField("smtp_port", Number(event.target.value))}
              className="w-full rounded-none border border-hairline bg-white px-3.5 py-2.5 text-[13.5px] text-ink outline-none transition placeholder:text-slate-300 focus:border-emerald-600"
            />
            <p className="mt-1.5 text-[11.5px] text-slate-400">587 for STARTTLS, 465 for SSL.</p>
          </div>

          <div>
            <label htmlFor="smtp_username" className="mb-1.5 block text-[12px] font-semibold uppercase tracking-[0.1em] text-slate-500">
              Username
            </label>
            <input
              id="smtp_username"
              value={smtp.smtp_username}
              disabled={loading}
              onChange={(event) => setSmtpField("smtp_username", event.target.value)}
              placeholder="postmaster@yourcompany.com"
              className="w-full rounded-none border border-hairline bg-white px-3.5 py-2.5 text-[13.5px] text-ink outline-none transition placeholder:text-slate-300 focus:border-emerald-600"
            />
          </div>

          <div>
            <label htmlFor="smtp_password" className="mb-1.5 block text-[12px] font-semibold uppercase tracking-[0.1em] text-slate-500">
              Password
            </label>
            {/* Never rendered back. The API reports only whether one exists,
                because a field that returned it would put a working mail
                credential into every browser session. */}
            <input
              id="smtp_password"
              type="password"
              value={smtpPassword}
              disabled={loading}
              onChange={(event) => {
                setSmtpPassword(event.target.value);
                setDirty(true);
              }}
              placeholder={passwordSet ? "Stored - leave blank to keep" : "App password or SMTP key"}
              className="w-full rounded-none border border-hairline bg-white px-3.5 py-2.5 text-[13.5px] text-ink outline-none transition placeholder:text-slate-300 focus:border-emerald-600"
            />
            <p className="mt-1.5 text-[11.5px] text-slate-400">
              {passwordSet
                ? "A password is stored. Leave blank to keep it."
                : "Encrypted before it is written. Never shown again."}
            </p>
          </div>

          <div>
            <label htmlFor="smtp_from" className="mb-1.5 block text-[12px] font-semibold uppercase tracking-[0.1em] text-slate-500">
              Send as
            </label>
            <input
              id="smtp_from"
              type="email"
              value={smtp.smtp_from_email}
              disabled={loading}
              onChange={(event) => setSmtpField("smtp_from_email", event.target.value)}
              placeholder="mateassist@yourcompany.com"
              className="w-full rounded-none border border-hairline bg-white px-3.5 py-2.5 text-[13.5px] text-ink outline-none transition placeholder:text-slate-300 focus:border-emerald-600"
            />
            <p className="mt-1.5 text-[11.5px] text-slate-400">
              Must be an address this server is allowed to send as.
            </p>
          </div>

          <div className="flex items-end">
            <label className="flex cursor-pointer items-center gap-2.5 text-[13px] text-ink">
              <input
                type="checkbox"
                checked={smtp.smtp_use_tls}
                disabled={loading}
                onChange={(event) => setSmtpField("smtp_use_tls", event.target.checked)}
                className="h-4 w-4 rounded-none accent-emerald-600"
              />
              Use STARTTLS
            </label>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3 border-t border-hairline px-6 py-4">
          <button
            type="button"
            onClick={sendTest}
            disabled={testing || loading || dirty}
            className="flex items-center gap-2 rounded-none border border-slate-300 bg-white px-4 py-2.5 text-[13px] font-medium text-ink transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:text-slate-400"
          >
            <Mail size={15} strokeWidth={1.8} />
            {testing ? "Sending..." : "Send a test email"}
          </button>
          <span className="text-[12px] text-slate-400">
            {dirty
              ? "Save your changes first, then send a test."
              : "Goes to your escalation address, using the settings above."}
          </span>
        </div>

        <div className="mx-6 mb-5 flex gap-3 rounded-none border border-hairline bg-slate-50 p-4">
          <Info size={16} className="mt-0.5 flex-none text-slate-400" strokeWidth={1.8} />
          <div className="text-[12.5px] leading-relaxed text-slate-600">
            Leave this blank and escalations still work &mdash; they go out through MateAssist
            instead. Using your own server matters for delivery: a message that says it is from
            your domain but arrives from ours is likely to be treated as spam.
          </div>
        </div>
      </section>

      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={save}
          disabled={saving || loading || !dirty}
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
