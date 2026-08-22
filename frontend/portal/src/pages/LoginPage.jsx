import { useEffect, useState } from "react";
import { AlertTriangle, ArrowRight, BookOpen, Camera, ShieldCheck } from "lucide-react";
import { useLocation, useNavigate } from "react-router-dom";
import { AuthShell } from "@mateassist/ui";

import { ForgotPassword } from "../components/ForgotPassword.jsx";
import { useAuth } from "../context/AuthContext.jsx";
import { baseDomain } from "../lib/domain.js";

/**
 * Sign-in for a workspace (D-177).
 *
 * Split-screen shell shared with the platform console and matching MateDesk and
 * MateConnect, so all three products read as siblings.
 *
 * No "create an account" link. Accounts are created by a workspace
 * administrator, and an employee who cannot sign in needs their admin, not a
 * sign-up form - so the page says exactly that instead of offering a dead end.
 */

const FEATURES = [
  { Icon: BookOpen, text: "Answers grounded in your own runbooks." },
  { Icon: Camera, text: "Paste a screenshot instead of describing the error." },
  { Icon: ShieldCheck, text: "Your workspace's data is isolated from every other." }
];

const FIELD =
  "w-full rounded-none border border-[#c8cdd6] bg-white px-3.5 py-3 text-sm text-[#0b1220] " +
  "outline-none transition placeholder:text-slate-300 focus:border-emerald-600";

const LABEL = "mb-1.5 block text-[13px] font-semibold text-[#3a4252]";

export default function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { login, isAuthenticated } = useAuth();

  // Read from the Host header server-side (D-021), so this reflects where you
  // already are rather than choosing where to go.
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
    <AuthShell
      variant="portal"
      headline={
        <>
          Your IT desk,
          <br />
          answered
        </>
      }
      headlineAccent="before it's a ticket."
      intro="Sign in to ask about anything IT. MateAssist walks you through the fix from your company's runbooks, and gets a human involved only when it has to."
      features={FEATURES}
    >
      {recovering ? (
        <>
          <h1 className="mb-1.5 text-[26px] font-semibold text-[#0b1220]">Reset your password</h1>
          <p className="mb-7 text-sm text-[#6b7385]">
            We will email you a code to set a new one.
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
          <h1 className="mb-1.5 text-[26px] font-semibold text-[#0b1220]">Sign in</h1>
          <p className="mb-7 text-sm text-[#6b7385]">
            Use the work email your IT team set you up with.
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
              <span className={LABEL}>Workspace</span>
              {/* Read-only: the subdomain already decided this. An editable box
                  would imply you can sign in somewhere you are not. */}
              <div className="flex rounded-none border border-[#e2e5eb] bg-[#f7f8fa]">
                <span className="min-w-0 flex-1 truncate px-3.5 py-3 font-mono text-[13px] text-[#3a4252]">
                  {workspace}
                </span>
                <span className="flex items-center border-l border-[#e2e5eb] px-3.5 font-mono text-[13px] text-[#6b7385]">
                  .{baseDomain()}
                </span>
              </div>
            </div>

            <div>
              <label htmlFor="email" className={LABEL}>
                Work email
              </label>
              <input
                id="email"
                type="email"
                required
                autoComplete="username"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="you@company.com"
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

          {/* Where a sibling product offers "create a workspace", MateAssist
              points at the person who can actually help. */}
          <p className="mt-8 text-[12.5px] leading-relaxed text-[#6b7385]">
            No account yet? MateAssist accounts are created by your IT
            administrator &mdash; ask them to add you.
          </p>
        </>
      )}
    </AuthShell>
  );
}
