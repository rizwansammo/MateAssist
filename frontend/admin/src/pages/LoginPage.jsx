import { useEffect, useState } from "react";
import { AlertTriangle, ArrowRight, ShieldCheck } from "lucide-react";
import { useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "../context/AuthContext.jsx";

/**
 * Platform owner sign-in.
 *
 * Net-new: the prototype had no admin login at all. This host carries no tenant
 * subdomain, so the server admits only a PLATFORM_OWNER membership here - a
 * tenant user's valid credentials are rejected outright.
 */
export default function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { login, isAuthenticated } = useAuth();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
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
    <div className="flex min-h-screen items-center justify-center bg-ink px-6 py-14">
      <div className="w-full max-w-[400px]">
        <div className="mb-8 flex items-center gap-3">
          <div className="flex h-9 w-9 flex-none items-center justify-center rounded-none bg-emerald-500">
            <ShieldCheck size={20} strokeWidth={2} className="text-emerald-950" />
          </div>
          <span className="font-wordmark text-2xl uppercase tracking-wide text-white">
            MateAssist
          </span>
        </div>

        <div className="mb-6 inline-flex items-center gap-2 rounded-none border border-amber-700 bg-amber-950/40 px-2.5 py-1">
          <ShieldCheck size={12} className="text-amber-500" />
          <span className="text-[10px] font-semibold uppercase tracking-[0.14em] text-amber-400">
            Super Admin Mode
          </span>
        </div>

        <h1 className="mb-2 text-[26px] font-semibold tracking-tight text-white">
          Platform sign-in
        </h1>
        <p className="mb-8 text-sm text-slate-400">
          Restricted to platform owners. Workspace accounts cannot sign in here.
        </p>

        <form className="flex flex-col gap-5" onSubmit={onSubmit}>
          <label className="flex flex-col gap-2">
            <span className="text-[11px] font-semibold uppercase tracking-[0.1em] text-slate-400">
              Email
            </span>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="username"
              className="rounded-none border border-slate-800 bg-[#0F1B2D] px-3.5 py-3 text-sm text-white"
            />
          </label>

          <label className="flex flex-col gap-2">
            <span className="text-[11px] font-semibold uppercase tracking-[0.1em] text-slate-400">
              Password
            </span>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              className="rounded-none border border-slate-800 bg-[#0F1B2D] px-3.5 py-3 text-sm tracking-widest text-white"
            />
          </label>

          {error && (
            <div
              role="alert"
              className="flex gap-3 rounded-none border border-red-900 bg-red-950/40 px-4 py-3"
            >
              <AlertTriangle size={16} strokeWidth={2} className="mt-0.5 flex-none text-red-400" />
              <span className="text-[12.5px] leading-relaxed text-red-300">{error}</span>
            </div>
          )}

          <button
            type="submit"
            disabled={submitting}
            className="flex items-center justify-center gap-2.5 rounded-none bg-emerald-600 px-5 py-4 text-sm font-semibold tracking-wide text-white transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:bg-slate-700"
          >
            {submitting ? "Signing in..." : "Sign in"}
            <ArrowRight size={16} />
          </button>
        </form>
      </div>
    </div>
  );
}
