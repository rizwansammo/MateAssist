import { useState } from "react";
import { ArrowLeft, KeyRound, MailCheck } from "lucide-react";

import { api } from "../lib/api.js";

/**
 * Recovering an account you cannot sign in to (D-176).
 *
 * Two steps in one panel: ask for a code, then use it. Kept on the sign-in page
 * rather than a separate route so the person never leaves the origin they
 * started on - and so nothing has to be re-typed if they lose the tab.
 *
 * The reply is the same whether or not the address exists, deliberately. This
 * screen must not become a way to test who is a customer, so it says "if that
 * address has an account" and moves to step two regardless.
 *
 * Shared by both surfaces: a locked-out platform owner and a locked-out end
 * user have the identical problem, and one flow means one set of protections.
 */

export function ForgotPassword({ initialEmail = "", onDone, onCancel, tone = "light" }) {
  const [step, setStep] = useState("request");
  const [email, setEmail] = useState(initialEmail);
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const dark = tone === "dark";
  const field = `w-full rounded-none border px-3.5 py-3 text-sm outline-none transition ${
    dark
      ? "border-slate-700 bg-[#0F1B2D] text-slate-100 placeholder:text-slate-600 focus:border-emerald-500"
      : "border-slate-300 bg-white text-ink placeholder:text-slate-300 focus:border-emerald-600"
  }`;
  const label = `mb-2 block text-[11px] font-semibold uppercase tracking-[0.1em] ${
    dark ? "text-slate-400" : "text-slate-700"
  }`;

  const requestCode = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const result = await api.requestPasswordReset(email.trim());
      setNotice(result.detail);
      setStep("confirm");
    } catch (cause) {
      setError(cause?.message ?? "Could not send a code.");
    } finally {
      setBusy(false);
    }
  };

  const confirm = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api.confirmPasswordReset(email.trim(), code.trim(), password);
      onDone?.(email.trim());
    } catch (cause) {
      setError(describe(cause));
    } finally {
      setBusy(false);
    }
  };

  if (step === "confirm") {
    return (
      <form onSubmit={confirm} className="flex flex-col gap-5">
        <div
          className={`flex gap-3 rounded-none border p-4 ${
            dark ? "border-emerald-800 bg-[#0C1F1A]" : "border-emerald-200 bg-emerald-50"
          }`}
        >
          <MailCheck
            size={16}
            className={`mt-0.5 flex-none ${dark ? "text-emerald-400" : "text-emerald-700"}`}
          />
          <p className={`text-[12.5px] leading-relaxed ${dark ? "text-emerald-200" : "text-emerald-900"}`}>
            {notice} It expires in 15 minutes and can be used once.
          </p>
        </div>

        <label>
          <span className={label}>Code from the email</span>
          <input
            value={code}
            onChange={(event) => setCode(event.target.value)}
            required
            inputMode="numeric"
            autoComplete="one-time-code"
            placeholder="123456"
            className={`${field} font-mono text-lg tracking-[0.3em]`}
          />
        </label>

        <label>
          <span className={label}>New password</span>
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
            autoComplete="new-password"
            className={field}
          />
        </label>

        {error && (
          <p className={`text-[12.5px] ${dark ? "text-red-400" : "text-red-600"}`}>{error}</p>
        )}

        {/* Said plainly: this is the one thing people are surprised by, and
            being surprised by it looks like a bug rather than a safeguard. */}
        <p className={`text-[11.5px] leading-relaxed ${dark ? "text-slate-500" : "text-slate-400"}`}>
          Changing your password signs you out everywhere else.
        </p>

        <button
          type="submit"
          disabled={busy || !code.trim() || !password}
          className="flex items-center justify-center gap-2 rounded-none bg-emerald-600 px-4 py-3 text-sm font-semibold text-white transition hover:bg-emerald-700 disabled:opacity-60"
        >
          <KeyRound size={15} />
          {busy ? "Setting..." : "Set new password"}
        </button>

        <button
          type="button"
          onClick={() => setStep("request")}
          className={`flex items-center justify-center gap-1.5 text-[12.5px] ${
            dark ? "text-slate-400 hover:text-slate-200" : "text-slate-500 hover:text-ink"
          }`}
        >
          <ArrowLeft size={13} />
          Use a different address
        </button>
      </form>
    );
  }

  return (
    <form onSubmit={requestCode} className="flex flex-col gap-5">
      <p className={`text-[13px] leading-relaxed ${dark ? "text-slate-400" : "text-slate-500"}`}>
        Enter the address you sign in with and we will send a six-digit code.
      </p>

      <label>
        <span className={label}>Email address</span>
        <input
          type="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          required
          autoComplete="username"
          placeholder="you@company.com"
          className={field}
        />
      </label>

      {error && <p className={`text-[12.5px] ${dark ? "text-red-400" : "text-red-600"}`}>{error}</p>}

      <button
        type="submit"
        disabled={busy || !email.trim()}
        className="rounded-none bg-emerald-600 px-4 py-3 text-sm font-semibold text-white transition hover:bg-emerald-700 disabled:opacity-60"
      >
        {busy ? "Sending..." : "Send me a code"}
      </button>

      <button
        type="button"
        onClick={onCancel}
        className={`flex items-center justify-center gap-1.5 text-[12.5px] ${
          dark ? "text-slate-400 hover:text-slate-200" : "text-slate-500 hover:text-ink"
        }`}
      >
        <ArrowLeft size={13} />
        Back to sign in
      </button>
    </form>
  );
}

function describe(error) {
  const body = error?.body;
  if (body && typeof body.detail === "string") return body.detail;
  return error?.message ?? "That did not work.";
}
