import { useEffect, useState } from "react";
import { KeyRound, Mail, ShieldCheck, User } from "lucide-react";

import { useAuth } from "../context/AuthContext.jsx";
import { usePortal } from "../context/PortalContext.jsx";
import { accountApi } from "../lib/account.js";

/**
 * Your own account: name, email, password (D-158).
 *
 * Until this page existed a user could not see their own email address
 * anywhere in the product, let alone correct it - and the only control that
 * looked like an account menu signed them out.
 *
 * Email changes are applied as typed, with no confirmation link, by decision.
 * The guard is the current password: a session left open on a shared machine
 * must not be enough to move somebody's login identity to another address.
 */

const FIELD =
  "w-full rounded-none border border-hairline bg-white px-3.5 py-2.5 text-[13.5px] " +
  "text-ink outline-none transition placeholder:text-slate-300 focus:border-emerald-600";

const LABEL = "mb-1.5 block text-[12px] font-semibold uppercase tracking-[0.1em] text-slate-500";

export default function AccountPage() {
  const { notify } = usePortal();
  const { refresh } = useAuth();

  const [profile, setProfile] = useState({ full_name: "", job_title: "", email: "" });
  const [originalEmail, setOriginalEmail] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const [passwords, setPasswords] = useState({ current: "", next: "", repeat: "" });
  const [changing, setChanging] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    accountApi
      .get(controller.signal)
      .then((data) => {
        setProfile({
          full_name: data.full_name ?? "",
          job_title: data.job_title ?? "",
          email: data.email ?? ""
        });
        setOriginalEmail(data.email ?? "");
      })
      .catch((error) => {
        if (error.name !== "AbortError") notify("Could not load your account", error.message, "warn");
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, [notify]);

  const emailChanged = profile.email.trim().toLowerCase() !== originalEmail.toLowerCase();

  const saveProfile = async (event) => {
    event.preventDefault();
    setSaving(true);
    try {
      const payload = { full_name: profile.full_name, job_title: profile.job_title };
      if (emailChanged) {
        payload.email = profile.email.trim();
        payload.current_password = confirmPassword;
      }

      const updated = await accountApi.save(payload);
      setOriginalEmail(updated.email);
      setConfirmPassword("");
      notify(
        "Account updated",
        emailChanged ? `You now sign in as ${updated.email}` : "Your details are saved"
      );
      // The header shows the name and initials, so it has to be told.
      await refresh?.();
    } catch (error) {
      notify("Could not save", describe(error), "warn");
    } finally {
      setSaving(false);
    }
  };

  const changePassword = async (event) => {
    event.preventDefault();
    if (passwords.next !== passwords.repeat) {
      // Caught here rather than at the server: the server has no idea the user
      // typed it twice, and a mismatch is a typo rather than a rejection.
      notify("Those do not match", "The new password and its confirmation differ.", "warn");
      return;
    }

    setChanging(true);
    try {
      await accountApi.changePassword(passwords.current, passwords.next);
      setPasswords({ current: "", next: "", repeat: "" });
      notify("Password changed", "Use it the next time you sign in.");
    } catch (error) {
      notify("Could not change your password", describe(error), "warn");
    } finally {
      setChanging(false);
    }
  };

  return (
    <main className="flex flex-col gap-6 px-6 pb-12 pt-7">
      <div>
        <h1 className="mb-2 text-[28px] font-semibold tracking-tight text-ink">Your account</h1>
        <p className="max-w-[720px] text-sm text-slate-500">
          Your name and email as your IT team sees them. Replies to an escalation you raise come
          back to the address below.
        </p>
      </div>

      {/* ---- profile ---- */}
      <form onSubmit={saveProfile} className="rounded-none border border-hairline bg-white">
        <div className="flex items-center gap-2.5 border-b border-hairline px-6 py-4">
          <User size={16} strokeWidth={1.8} className="text-slate-500" />
          <div className="text-[15px] font-semibold text-ink">Profile</div>
        </div>

        <div className="grid gap-5 px-6 py-5 md:grid-cols-2">
          <div>
            <label htmlFor="full_name" className={LABEL}>
              Full name
            </label>
            <input
              id="full_name"
              value={profile.full_name}
              disabled={loading}
              onChange={(e) => setProfile({ ...profile, full_name: e.target.value })}
              placeholder="Rizwan Ahmed"
              className={FIELD}
            />
          </div>

          <div>
            <label htmlFor="job_title" className={LABEL}>
              Job title
            </label>
            <input
              id="job_title"
              value={profile.job_title}
              disabled={loading}
              onChange={(e) => setProfile({ ...profile, job_title: e.target.value })}
              placeholder="Operations"
              className={FIELD}
            />
          </div>

          <div className="md:col-span-2">
            <label htmlFor="email" className={LABEL}>
              Email address
            </label>
            <input
              id="email"
              type="email"
              value={profile.email}
              disabled={loading}
              onChange={(e) => setProfile({ ...profile, email: e.target.value })}
              className={FIELD}
            />
            <p className="mt-1.5 text-[11.5px] text-slate-400">
              This is how you sign in, and where replies to your escalations are sent.
            </p>
          </div>

          {/* Only once the address has actually changed. Asking for a password
              on a page the user opened to fix a typo in their job title reads
              as the product not trusting them. */}
          {emailChanged && (
            <div className="md:col-span-2">
              <div className="flex gap-3 border border-amber-200 bg-amber-50 p-3.5">
                <ShieldCheck size={15} className="mt-0.5 flex-none text-amber-600" />
                <div className="min-w-0 flex-1">
                  <div className="text-[12.5px] leading-relaxed text-amber-900">
                    You are changing the address you sign in with. Confirm with your current
                    password.
                  </div>
                  <input
                    type="password"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    placeholder="Current password"
                    className={`${FIELD} mt-2.5 border-amber-300`}
                  />
                </div>
              </div>
            </div>
          )}
        </div>

        <div className="flex items-center gap-3 border-t border-hairline px-6 py-4">
          <button
            type="submit"
            disabled={saving || loading || (emailChanged && !confirmPassword)}
            className="rounded-none border border-ink bg-ink px-5 py-2.5 text-[13px] font-semibold text-white transition hover:bg-slate-800 disabled:opacity-60"
          >
            {saving ? "Saving..." : "Save changes"}
          </button>
          <span className="text-[12px] text-slate-400">
            <Mail size={12} className="mr-1 inline" />
            Signed in as {originalEmail || "..."}
          </span>
        </div>
      </form>

      {/* ---- password ---- */}
      <form onSubmit={changePassword} className="rounded-none border border-hairline bg-white">
        <div className="flex items-center gap-2.5 border-b border-hairline px-6 py-4">
          <KeyRound size={16} strokeWidth={1.8} className="text-slate-500" />
          <div className="text-[15px] font-semibold text-ink">Password</div>
        </div>

        <div className="grid gap-5 px-6 py-5 md:grid-cols-3">
          <div>
            <label htmlFor="pw_current" className={LABEL}>
              Current password
            </label>
            <input
              id="pw_current"
              type="password"
              value={passwords.current}
              onChange={(e) => setPasswords({ ...passwords, current: e.target.value })}
              className={FIELD}
            />
          </div>
          <div>
            <label htmlFor="pw_next" className={LABEL}>
              New password
            </label>
            <input
              id="pw_next"
              type="password"
              value={passwords.next}
              onChange={(e) => setPasswords({ ...passwords, next: e.target.value })}
              className={FIELD}
            />
          </div>
          <div>
            <label htmlFor="pw_repeat" className={LABEL}>
              Repeat new password
            </label>
            <input
              id="pw_repeat"
              type="password"
              value={passwords.repeat}
              onChange={(e) => setPasswords({ ...passwords, repeat: e.target.value })}
              className={FIELD}
            />
          </div>
        </div>

        <div className="flex items-center gap-3 border-t border-hairline px-6 py-4">
          <button
            type="submit"
            disabled={changing || !passwords.current || !passwords.next}
            className="rounded-none border border-ink bg-white px-5 py-2.5 text-[13px] font-semibold text-ink transition hover:bg-slate-50 disabled:opacity-60"
          >
            {changing ? "Changing..." : "Change password"}
          </button>
          <span className="text-[12px] text-slate-400">
            You stay signed in on this device.
          </span>
        </div>
      </form>
    </main>
  );
}

/** Field errors arrive keyed by field; a toast needs one readable line. */
function describe(error) {
  const body = error?.body;
  if (!body) return error?.message ?? "Request failed";
  if (typeof body.detail === "string") return body.detail;

  const first = Object.values(body)[0];
  return Array.isArray(first) ? first[0] : String(first ?? error.message);
}
