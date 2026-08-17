import { useEffect, useState } from "react";
import { AlertTriangle, ArrowRight } from "lucide-react";
import { useLocation, useNavigate } from "react-router-dom";
import { Wordmark } from "@mateassist/ui";
import { ForgotPassword } from "../components/ForgotPassword.jsx";
import { baseDomain } from "../lib/domain.js";

import { useAuth } from "../context/AuthContext.jsx";

/**
 * Sign-in.
 *
 * Phase 1 delivers the form; Phase 2 wires it to POST /api/v1/auth/login/ and
 * the httpOnly refresh cookie (D-030..D-036). The prototype's hardcoded
 * password in a defaultValue is gone, and so is the "Continue with Microsoft
 * Entra ID" button - SSO is out of scope for v1 (D-036), and a button that
 * looks real but does nothing is worse than no button.
 */
export default function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { login, status, isAuthenticated } = useAuth();

  // The workspace is read from the Host header server-side (D-021), so this
  // field reflects where you already are rather than choosing where to go.
  const workspace = window.location.hostname.split(".")[0];
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [recovering, setRecovering] = useState(false);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const redirectTo = location.state?.from ?? "/app";

  useEffect(() => {
    if (isAuthenticated) navigate(redirectTo, { replace: true });
  }, [isAuthenticated, navigate, redirectTo]);

  const onSubmit = async (event) => {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await login(email, password);
      navigate(redirectTo, { replace: true });
    } catch (cause) {
      // The server answers every failure identically so the form cannot be used
      // to enumerate accounts; the UI must not undo that by being more helpful.
      setError(
        cause?.status === 403
          ? "This workspace is suspended. Contact your administrator."
          : "Invalid credentials."
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="grid min-h-screen grid-cols-1 bg-white lg:grid-cols-[1.05fr_0.95fr]">
      <div className="relative hidden flex-col justify-between overflow-hidden bg-ink px-16 py-14 lg:flex">
        <div
          className="absolute inset-0 opacity-70"
          style={{
            backgroundImage:
              "linear-gradient(#131E30 1px, transparent 1px), linear-gradient(90deg, #131E30 1px, transparent 1px)",
            backgroundSize: "48px 48px"
          }}
        />
        <div className="relative">
          <Wordmark size="text-[27px]" mark="h-10 w-10" icon={22} />
        </div>
        <div className="relative flex max-w-[460px] flex-col gap-7">
          <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-emerald-400">
            Agentic IT Operations
          </div>
          <h1 className="text-[44px] font-semibold leading-[1.08] tracking-tight text-white text-pretty">
            Your IT desk, resolved before it becomes a ticket.
          </h1>
          <p className="text-[15px] leading-relaxed text-slate-400 text-pretty">
            MateAssist triages requests, walks you through fixes from your company runbooks, and
            escalates to a human engineer only when it has to.
          </p>
          {/*
            Static brand copy, NOT metrics. This panel renders before
            authentication, where no tenant context exists, so it is
            structurally incapable of showing live figures. Recorded in
            DECISIONS.md section 8 so it is never filed as a data bug.
          */}
          <div className="grid grid-cols-3 gap-px border border-slate-800 bg-slate-800">
            {[
              ["76%", "Self-served"],
              ["41m", "Avg. resolve"],
              ["24/7", "Coverage"]
            ].map(([value, label]) => (
              <div key={label} className="bg-ink3 px-4 py-4">
                <div className="text-[22px] font-semibold text-white">{value}</div>
                <div className="mt-1.5 text-[11px] uppercase tracking-[0.08em] text-slate-500">
                  {label}
                </div>
              </div>
            ))}
          </div>
        </div>
        <div className="relative text-xs tracking-wide text-slate-600">
          Data isolated per workspace
        </div>
      </div>

      <div className="flex items-center justify-center px-6 py-14 sm:px-12">
        <div className="w-full max-w-[400px]">
          <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">
            Sign in
          </div>
          <h2 className="mb-2 mt-3 text-[28px] font-semibold tracking-tight text-ink">
            Welcome back
          </h2>
          <p className="mb-8 text-sm text-slate-500">Enter your workspace to continue.</p>

          {recovering ? (
            <ForgotPassword
              initialEmail={email}
              onCancel={() => setRecovering(false)}
              onDone={(address) => {
                setEmail(address);
                setPassword("");
                setRecovering(false);
              }}
            />
          ) : (
          <form className="flex flex-col gap-5" onSubmit={onSubmit}>
            <label className="flex flex-col gap-2">
              <span className="text-[11px] font-semibold uppercase tracking-[0.1em] text-slate-700">
                Workspace / Company name
              </span>
              <div className="flex rounded-none border border-slate-300 bg-slate-50">
                <input
                  type="text"
                  value={workspace}
                  readOnly
                  aria-readonly="true"
                  className="min-w-0 flex-1 rounded-none border-0 bg-transparent px-3.5 py-3 text-sm text-slate-600"
                />
                <span className="flex items-center rounded-none border-l border-hairline bg-slate-100 px-3.5 font-mono text-[13px] text-slate-500">
                  .{baseDomain()}
                </span>
              </div>
            </label>

            <label className="flex flex-col gap-2">
              <span className="text-[11px] font-semibold uppercase tracking-[0.1em] text-slate-700">
                Work email
              </span>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="username"
                placeholder="you@company.com"
                className="rounded-none border border-slate-300 bg-white px-3.5 py-3 text-sm text-ink"
              />
            </label>

            <label className="flex flex-col gap-2">
              <div className="flex items-baseline justify-between">
                <span className="text-[11px] font-semibold uppercase tracking-[0.1em] text-slate-700">
                  Password
                </span>
                {/* A real flow now (D-176). This was an anchor to "#reset",
                    which went nowhere - so a locked-out user's only recovery
                    was contacting whoever runs the server. */}
                <button
                  type="button"
                  onClick={() => setRecovering(true)}
                  className="text-xs text-emerald-700 underline-offset-2 hover:underline"
                >
                  Forgot?
                </button>
              </div>
              <input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                className="rounded-none border border-slate-300 bg-white px-3.5 py-3 text-sm tracking-widest text-ink"
              />
            </label>

            <label className="flex cursor-pointer items-center gap-2.5 text-[13px] text-slate-600">
              <input
                type="checkbox"
                defaultChecked
                className="h-[15px] w-[15px] rounded-none accent-emerald-600"
              />
              Keep me signed in on this device
            </label>

            {error && (
              <div
                role="alert"
                className="flex gap-3 rounded-none border border-red-200 bg-red-50 px-4 py-3"
              >
                <AlertTriangle size={16} strokeWidth={2} className="mt-0.5 flex-none text-red-700" />
                <span className="text-[12.5px] leading-relaxed text-red-800">{error}</span>
              </div>
            )}

            <button
              type="submit"
              disabled={submitting || status === "restoring"}
              className="flex items-center justify-center gap-2.5 rounded-none bg-emerald-600 px-5 py-4 text-sm font-semibold tracking-wide text-white transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:bg-slate-400"
            >
              {submitting ? "Signing in..." : "Sign in to workspace"}
              <ArrowRight size={16} />
            </button>
          </form>
          )}

          <p className="mt-8 text-xs leading-relaxed text-slate-400">
            Protected by your organisation&apos;s access policy. Sessions expire after 12 hours of
            inactivity.
          </p>
        </div>
      </div>
    </div>
  );
}
