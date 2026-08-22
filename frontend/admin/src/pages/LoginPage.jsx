import { useEffect, useState } from "react";
import { AlertTriangle, ArrowRight, Building2, KeyRound, ScrollText } from "lucide-react";
import { useLocation, useNavigate } from "react-router-dom";
import { AuthShell } from "@mateassist/ui";

import { ForgotPassword } from "../components/ForgotPassword.jsx";
import { useAuth } from "../context/AuthContext.jsx";

/**
 * Platform owner sign-in (D-177).
 *
 * Same split-screen shell as the portal and the sibling products. The copy is
 * the difference: this host carries no tenant subdomain, so the server admits
 * only a PLATFORM_OWNER membership here - a tenant user's valid credentials are
 * rejected outright, and the page should not pretend otherwise.
 */

const FEATURES = [
  { Icon: Building2, text: "Every workspace on the platform, in one console." },
  { Icon: KeyRound, text: "Provider credentials sealed and never returned." },
  { Icon: ScrollText, text: "Every privileged action recorded with who and when." }
];

const FIELD =
  "w-full rounded-none border border-[#c8cdd6] bg-white px-3.5 py-3 text-sm text-[#0b1220] " +
  "outline-none transition placeholder:text-slate-300 focus:border-emerald-600";

const LABEL = "mb-1.5 block text-[13px] font-semibold text-[#3a4252]";

export default function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { login, isAuthenticated } = useAuth();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [recovering, setRecovering] = useState(false);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const redirectTo = location.state?.from ?? "/";

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
    } catch {
      setError("Invalid credentials.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AuthShell
      variant="admin"
      headline={
        <>
          Every workspace.
          <br />
          Every key.
        </>
      }
      headlineAccent="One console."
      intro="Platform administration for MateAssist: workspaces, provider credentials, usage and billing. Reachable only from this host."
      features={FEATURES}
      asideNote="Platform console - NetaMate Solutions"
    >
      {recovering ? (
        <>
          <h1 className="mb-1.5 text-[26px] font-semibold text-[#0b1220]">Reset your password</h1>
          <p className="mb-7 text-sm text-[#6b7385]">
            We will email a code to your platform owner address.
          </p>
          <ForgotPassword
            initialEmail={email}
            onCancel={() => setRecovering(false)}
            onDone={(address) => {
              setEmail(address);
              setPassword("");
              setRecovering(false);
            }}
          />
        </>
      ) : (
        <>
          <span className="mb-4 inline-block self-start border border-[#e2e5eb] bg-[#f7f8fa] px-2.5 py-1 text-[10.5px] font-semibold uppercase tracking-[0.08em] text-[#6b7385]">
            Platform administration
          </span>

          <h1 className="mb-1.5 text-[26px] font-semibold text-[#0b1220]">Sign in</h1>
          <p className="mb-7 text-sm text-[#6b7385]">
            Platform owner credentials only. Workspace accounts sign in at their own address.
          </p>

          {error && (
            <div
              role="alert"
              className="mb-5 flex gap-3 rounded-none border border-red-300 bg-red-50 px-3.5 py-2.5"
            >
              <AlertTriangle size={15} strokeWidth={2} className="mt-0.5 flex-none text-red-600" />
              <span className="text-[13px] leading-relaxed text-red-800">{error}</span>
            </div>
          )}

          <form onSubmit={onSubmit} className="flex flex-col gap-4">
            <div>
              <label htmlFor="email" className={LABEL}>
                Email
              </label>
              <input
                id="email"
                type="email"
                required
                autoComplete="username"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="you@example.com"
                className={FIELD}
              />
            </div>

            <div>
              <div className="mb-1.5 flex items-baseline justify-between">
                <label htmlFor="password" className="text-[13px] font-semibold text-[#3a4252]">
                  Password
                </label>
                <button
                  type="button"
                  onClick={() => setRecovering(true)}
                  className="text-[12.5px] font-medium text-emerald-700 underline-offset-2 hover:underline"
                >
                  Forgot?
                </button>
              </div>
              <input
                id="password"
                type="password"
                required
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                className={FIELD}
              />
            </div>

            <button
              type="submit"
              disabled={submitting}
              className="mt-2 flex h-12 items-center justify-center gap-2 rounded-none bg-emerald-600 text-[15px] font-semibold text-white transition hover:bg-emerald-700 disabled:opacity-70"
            >
              {submitting ? "Signing in..." : "Sign in"}
              {!submitting && <ArrowRight size={16} />}
            </button>
          </form>

          {/* The break-glass path, named on the page. If the mailbox itself is
              gone, every email-based recovery fails together - and an operator
              locked out at 2am should not have to remember this exists. */}
          <p className="mt-8 text-[12.5px] leading-relaxed text-[#6b7385]">
            Locked out with no access to that mailbox? Recovery runs from the server:{" "}
            <code className="border border-[#e2e5eb] bg-[#f7f8fa] px-1.5 py-px font-mono text-[11.5px] text-[#3a4252]">
              manage.py reset_platform_owner
            </code>
          </p>
        </>
      )}
    </AuthShell>
  );
}
