import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, Mail, Send, ShieldCheck } from "lucide-react";

import { useAdmin } from "../context/AdminContext.jsx";
import { platformApi } from "../lib/platform.js";

/**
 * How MateAssist itself sends email (D-175).
 *
 * Not a workspace's SMTP - that sends a customer's escalations from their
 * domain. This carries password reset codes and account emails, so it must
 * never route through a customer's server: recovery for the whole platform
 * cannot sit behind infrastructure a customer controls.
 *
 * Editable here rather than in the environment, because the console is where an
 * operator already is when they discover mail is broken - and fixing it should
 * not require a deploy.
 */

const FIELD =
  "w-full rounded-none border border-hairline bg-white px-3.5 py-2.5 text-[13.5px] " +
  "text-ink outline-none transition placeholder:text-slate-300 focus:border-emerald-600";

const LABEL = "mb-1.5 block text-[12px] font-semibold uppercase tracking-[0.1em] text-slate-500";

export default function PlatformMailPage() {
  const { notify } = useAdmin();

  const [form, setForm] = useState({
    smtp_host: "",
    smtp_port: 587,
    smtp_username: "",
    smtp_use_tls: true,
    from_email: "",
    from_name: "MateAssist"
  });
  const [password, setPassword] = useState("");
  const [passwordSet, setPasswordSet] = useState(false);
  const [configured, setConfigured] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [dirty, setDirty] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await platformApi.mailSettings();
      setForm({
        smtp_host: data.smtp_host ?? "",
        smtp_port: data.smtp_port ?? 587,
        smtp_username: data.smtp_username ?? "",
        smtp_use_tls: data.smtp_use_tls ?? true,
        from_email: data.from_email ?? "",
        from_name: data.from_name ?? "MateAssist"
      });
      setPasswordSet(Boolean(data.smtp_password_set));
      setConfigured(Boolean(data.is_configured));
    } catch (error) {
      notify("Could not load mail settings", error.message, "warn");
    } finally {
      setLoading(false);
    }
  }, [notify]);

  useEffect(() => {
    load();
  }, [load]);

  const set = (field) => (event) => {
    const value = event.target.type === "checkbox" ? event.target.checked : event.target.value;
    setForm((prev) => ({ ...prev, [field]: value }));
    setDirty(true);
  };

  const save = async (event) => {
    event.preventDefault();
    setSaving(true);
    try {
      // Only send the password when one was typed. An empty string clears the
      // stored credential, so sending it unconditionally would wipe a working
      // one every time somebody edited the From address.
      const payload = { ...form, smtp_port: Number(form.smtp_port) || 587 };
      if (password) payload.smtp_password = password;

      const data = await platformApi.saveMailSettings(payload);
      setPassword("");
      setPasswordSet(Boolean(data.smtp_password_set));
      setConfigured(Boolean(data.is_configured));
      setDirty(false);
      notify("Mail settings saved", "Send a test to confirm they work.");
    } catch (error) {
      notify("Could not save", describe(error), "warn");
    } finally {
      setSaving(false);
    }
  };

  const sendTest = async () => {
    setTesting(true);
    try {
      const result = await platformApi.sendMailTest();
      if (result.sent) {
        notify("Test sent", result.detail);
      } else {
        // The provider's own message: the reader is debugging their own mail
        // server, and "username and password not accepted" is the answer.
        notify("Test failed", result.detail, "warn");
      }
    } catch (error) {
      notify("Test failed", error.message, "warn");
    } finally {
      setTesting(false);
    }
  };

  return (
    <main className="flex flex-col gap-5 px-6 pb-12 pt-7">
      <div>
        <h1 className="mb-2 text-[28px] font-semibold tracking-tight text-ink">Platform mail</h1>
        <p className="max-w-[760px] text-sm text-slate-500">
          How MateAssist sends its own email &mdash; password reset codes and account
          notifications. Separate from a workspace&rsquo;s SMTP, which sends that
          customer&rsquo;s escalations.
        </p>
      </div>

      {!configured && !loading && (
        <div className="flex gap-3 rounded-none border border-amber-300 bg-amber-50 px-5 py-4">
          <AlertTriangle size={16} className="mt-0.5 flex-none text-amber-600" strokeWidth={1.8} />
          <div className="text-[12.5px] leading-relaxed text-amber-900">
            <strong className="font-semibold">MateAssist cannot send email yet.</strong> Anything
            it tries to send is written to the server log and delivered nowhere. Password
            recovery will not work until this is configured and tested.
          </div>
        </div>
      )}

      <form onSubmit={save} className="rounded-none border border-hairline bg-white">
        <div className="flex items-center gap-2.5 border-b border-hairline px-6 py-4">
          <Mail size={16} strokeWidth={1.8} className="text-slate-500" />
          <div className="flex-1">
            <div className="text-[15px] font-semibold text-ink">Outgoing mail server</div>
            <div className="mt-0.5 text-[12.5px] text-slate-500">
              A Gmail account works: generate an app password, not your normal one.
            </div>
          </div>
          {configured && (
            <span className="flex items-center gap-1.5 rounded-none border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-[11.5px] font-semibold text-emerald-700">
              <ShieldCheck size={13} />
              Configured
            </span>
          )}
        </div>

        <div className="grid gap-5 px-6 py-5 md:grid-cols-2">
          <div>
            <label htmlFor="host" className={LABEL}>
              Server
            </label>
            <input
              id="host"
              value={form.smtp_host}
              disabled={loading}
              onChange={set("smtp_host")}
              placeholder="smtp.gmail.com"
              className={FIELD}
            />
          </div>

          <div>
            <label htmlFor="port" className={LABEL}>
              Port
            </label>
            <input
              id="port"
              type="number"
              value={form.smtp_port}
              disabled={loading}
              onChange={set("smtp_port")}
              className={FIELD}
            />
            <p className="mt-1.5 text-[11.5px] text-slate-400">587 for STARTTLS, 465 for SSL.</p>
          </div>

          <div>
            <label htmlFor="username" className={LABEL}>
              Username
            </label>
            <input
              id="username"
              value={form.smtp_username}
              disabled={loading}
              onChange={set("smtp_username")}
              placeholder="you@gmail.com"
              className={FIELD}
            />
          </div>

          <div>
            <label htmlFor="password" className={LABEL}>
              App password
            </label>
            {/* Never rendered back. The API reports only whether one exists -
                a field that returned it would put a working mail credential
                into every browser session. */}
            <input
              id="password"
              type="password"
              value={password}
              disabled={loading}
              onChange={(event) => {
                setPassword(event.target.value);
                setDirty(true);
              }}
              placeholder={passwordSet ? "Stored - leave blank to keep" : "16-character app password"}
              className={FIELD}
            />
            <p className="mt-1.5 text-[11.5px] text-slate-400">
              {passwordSet
                ? "A password is stored. Leave blank to keep it."
                : "Encrypted before it is written. Never shown again."}
            </p>
          </div>

          <div>
            <label htmlFor="from_email" className={LABEL}>
              Send as
            </label>
            <input
              id="from_email"
              type="email"
              value={form.from_email}
              disabled={loading}
              onChange={set("from_email")}
              placeholder="you@gmail.com"
              className={FIELD}
            />
            <p className="mt-1.5 text-[11.5px] text-slate-400">
              Normally the same as the username.
            </p>
          </div>

          <div>
            <label htmlFor="from_name" className={LABEL}>
              Display name
            </label>
            <input
              id="from_name"
              value={form.from_name}
              disabled={loading}
              onChange={set("from_name")}
              className={FIELD}
            />
          </div>

          <div className="md:col-span-2">
            <label className="flex cursor-pointer items-center gap-2.5 text-[13px] text-ink">
              <input
                type="checkbox"
                checked={form.smtp_use_tls}
                disabled={loading}
                onChange={set("smtp_use_tls")}
                className="h-4 w-4 rounded-none accent-emerald-600"
              />
              Use STARTTLS
            </label>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3 border-t border-hairline px-6 py-4">
          <button
            type="submit"
            disabled={saving || loading || !dirty}
            className="rounded-none border border-ink bg-ink px-5 py-2.5 text-[13px] font-semibold text-white transition hover:bg-slate-800 disabled:opacity-60"
          >
            {saving ? "Saving..." : "Save settings"}
          </button>

          <button
            type="button"
            onClick={sendTest}
            disabled={testing || loading || dirty}
            className="flex items-center gap-2 rounded-none border border-slate-300 bg-white px-4 py-2.5 text-[13px] font-medium text-ink transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:text-slate-400"
          >
            <Send size={15} strokeWidth={1.8} />
            {testing ? "Sending..." : "Send a test email"}
          </button>

          <span className="text-[12px] text-slate-400">
            {dirty ? "Save your changes first, then send a test." : "Goes to your own address."}
          </span>
        </div>
      </form>

      <div className="rounded-none border border-hairline bg-slate-50 px-5 py-4 text-[12.5px] leading-relaxed text-slate-600">
        <strong className="font-semibold text-ink">If this account is ever lost,</strong> recovery
        runs from the server:{" "}
        <code className="rounded-none border border-hairline bg-white px-1.5 py-px font-mono text-[12px]">
          manage.py reset_platform_owner --email you@example.com
        </code>
        . Every other recovery path goes through email, so all of them fail together the moment
        the mailbox is the thing that is gone.
      </div>
    </main>
  );
}

function describe(error) {
  const body = error?.body;
  if (!body) return error?.message ?? "Request failed";
  if (typeof body.detail === "string") return body.detail;

  const first = Object.values(body)[0];
  return Array.isArray(first) ? first[0] : String(first ?? error.message);
}
