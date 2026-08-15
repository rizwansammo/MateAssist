import { useCallback, useEffect, useState } from "react";
import { Check, Copy, KeyRound, ShieldAlert, Users, X } from "lucide-react";

import { useAuth } from "../context/AuthContext.jsx";
import { usePortal } from "../context/PortalContext.jsx";
import { workspaceApi } from "../lib/workspace.js";

/**
 * The people in this workspace, and their passwords (D-159).
 *
 * Administrator-only. The list is memberships of this tenant, so it can only
 * ever contain this workspace - there is no filter here that could be widened
 * by accident.
 *
 * A reset password is shown once, in a panel the administrator has to dismiss.
 * Nothing stores it and no screen can show it again, which is the same promise
 * the credential vault makes and the reason the panel is deliberately hard to
 * miss.
 */

const ROLE_LABEL = {
  TENANT_ADMIN: "Administrator",
  AGENT: "Agent",
  END_USER: "Member"
};

export default function PeoplePage() {
  const { notify } = usePortal();
  const { user: me } = useAuth();

  const [people, setPeople] = useState([]);
  const [loading, setLoading] = useState(true);
  const [target, setTarget] = useState(null);
  const [issued, setIssued] = useState(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setPeople(await workspaceApi.users());
    } catch (error) {
      notify("Could not load your people", error.message, "warn");
    } finally {
      setLoading(false);
    }
  }, [notify]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const reset = async (person, chosenPassword) => {
    try {
      const result = await workspaceApi.resetPassword(person.id, chosenPassword);
      setTarget(null);
      setIssued({ email: result.email, password: result.password });
    } catch (error) {
      notify("Could not reset that password", describe(error), "warn");
    }
  };

  return (
    <main className="flex flex-col gap-6 px-6 pb-12 pt-7">
      <div>
        <h1 className="mb-2 text-[28px] font-semibold tracking-tight text-ink">People</h1>
        <p className="max-w-[720px] text-sm text-slate-500">
          Everyone with access to this workspace. Reset a password when someone is locked out.
        </p>
      </div>

      {issued && <IssuedPassword issued={issued} onClose={() => setIssued(null)} />}

      <section className="rounded-none border border-hairline bg-white">
        <div className="flex items-center gap-2.5 border-b border-hairline px-6 py-4">
          <Users size={16} strokeWidth={1.8} className="text-slate-500" />
          <div className="text-[15px] font-semibold text-ink">
            {loading ? "Loading..." : `${people.length} ${people.length === 1 ? "person" : "people"}`}
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-[13px]">
            <thead>
              <tr className="text-[11px] font-semibold uppercase tracking-[0.1em] text-slate-500">
                <th className="border-b border-hairline px-6 py-3">Name</th>
                <th className="border-b border-hairline px-4 py-3">Role</th>
                <th className="border-b border-hairline px-4 py-3">Last seen</th>
                <th className="border-b border-hairline px-6 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {people.map((person) => (
                <tr key={person.id}>
                  <td className="border-b border-slate-100 px-6 py-4">
                    <div className="flex items-center gap-3">
                      <div className="flex h-[30px] w-[30px] flex-none items-center justify-center rounded-none bg-teal-700 text-[11px] font-semibold text-white">
                        {person.initials}
                      </div>
                      <div className="min-w-0">
                        <div className="truncate text-[13.5px] font-medium text-ink">
                          {person.display_name}
                          {person.id === me?.id && (
                            <span className="ml-2 text-[11px] font-normal text-slate-400">you</span>
                          )}
                        </div>
                        <div className="truncate text-[12px] text-slate-500">{person.email}</div>
                      </div>
                    </div>
                  </td>
                  <td className="border-b border-slate-100 px-4 py-4 text-slate-600">
                    {ROLE_LABEL[person.role] ?? person.role}
                  </td>
                  <td className="whitespace-nowrap border-b border-slate-100 px-4 py-4 text-slate-500">
                    {person.last_seen_at
                      ? new Date(person.last_seen_at).toLocaleDateString("en-GB")
                      : "never"}
                  </td>
                  <td className="border-b border-slate-100 px-6 py-4 text-right">
                    <button
                      type="button"
                      onClick={() => setTarget(person)}
                      className="whitespace-nowrap rounded-none border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-ink transition hover:bg-slate-50"
                    >
                      Reset password
                    </button>
                  </td>
                </tr>
              ))}
              {!loading && people.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-6 py-10 text-center text-slate-500">
                    Nobody has been added to this workspace yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      {target && (
        <ResetDialog person={target} onClose={() => setTarget(null)} onConfirm={reset} />
      )}
    </main>
  );
}

function ResetDialog({ person, onClose, onConfirm }) {
  const [password, setPassword] = useState("");
  const [working, setWorking] = useState(false);

  const submit = async (event) => {
    event.preventDefault();
    setWorking(true);
    await onConfirm(person, password.trim());
    setWorking(false);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/50 p-4">
      <form
        onSubmit={submit}
        className="w-full max-w-[520px] rounded-none border border-hairline bg-white"
      >
        <div className="flex items-start justify-between border-b border-hairline px-6 py-4">
          <div>
            <div className="text-[15px] font-semibold text-ink">Reset password</div>
            <div className="mt-0.5 text-[12.5px] text-slate-500">{person.email}</div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-none border border-hairline bg-white p-1.5 text-slate-500 transition hover:bg-slate-50"
          >
            <X size={15} />
          </button>
        </div>

        <div className="px-6 py-5">
          <label
            htmlFor="new_password"
            className="mb-1.5 block text-[12px] font-semibold uppercase tracking-[0.1em] text-slate-500"
          >
            New password
          </label>
          <input
            id="new_password"
            type="text"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            placeholder="Leave blank to generate a strong one"
            className="w-full rounded-none border border-hairline bg-white px-3.5 py-2.5 font-mono text-[13.5px] text-ink outline-none transition placeholder:font-sans placeholder:text-slate-300 focus:border-emerald-600"
          />
          <p className="mt-1.5 text-[11.5px] text-slate-400">
            Generating one is safer. A password chosen while resetting several accounts tends to
            be the same one every time.
          </p>

          <div className="mt-4 flex gap-3 rounded-none border border-amber-200 bg-amber-50 p-3.5">
            <ShieldAlert size={15} className="mt-0.5 flex-none text-amber-600" />
            <div className="text-[12.5px] leading-relaxed text-amber-900">
              {person.display_name} is signed out of nothing, but their old password stops working
              immediately. Make sure you can reach them before you do this.
            </div>
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
            disabled={working}
            className="rounded-none border border-ink bg-ink px-5 py-2.5 text-[13px] font-semibold text-white transition hover:bg-slate-800 disabled:opacity-60"
          >
            {working ? "Resetting..." : "Reset password"}
          </button>
        </div>
      </form>
    </div>
  );
}

function IssuedPassword({ issued, onClose }) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(issued.password);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard access can be refused; the password is on screen to be read.
    }
  };

  return (
    <section className="rounded-none border border-emerald-300 bg-emerald-50">
      <div className="flex flex-wrap items-center gap-3 px-6 py-4">
        <KeyRound size={16} strokeWidth={1.8} className="flex-none text-emerald-700" />
        <div className="min-w-0 flex-1">
          <div className="text-[13.5px] font-semibold text-emerald-900">
            New password for {issued.email}
          </div>
          <div className="mt-0.5 text-[12px] text-emerald-800">
            Shown once. Nothing can display it again - send it to them now.
          </div>
        </div>
        <code className="rounded-none border border-emerald-300 bg-white px-3 py-2 font-mono text-[14px] tracking-wide text-ink">
          {issued.password}
        </code>
        <button
          type="button"
          onClick={copy}
          className="flex items-center gap-1.5 rounded-none border border-emerald-700 bg-emerald-700 px-3.5 py-2 text-[12.5px] font-semibold text-white transition hover:bg-emerald-800"
        >
          {copied ? <Check size={14} /> : <Copy size={14} />}
          {copied ? "Copied" : "Copy"}
        </button>
        <button
          type="button"
          onClick={onClose}
          className="rounded-none border border-emerald-300 bg-white p-2 text-emerald-800 transition hover:bg-emerald-100"
          aria-label="Dismiss"
        >
          <X size={14} />
        </button>
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
