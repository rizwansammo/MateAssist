import { useState } from "react";
import { ArrowRight } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { Wordmark } from "@mateassist/ui";

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
  const [workspace, setWorkspace] = useState("netswitch");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const onSubmit = (event) => {
    event.preventDefault();
    // Phase 2: exchange credentials for a token pair, then redirect.
    navigate("/app");
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

          <form className="flex flex-col gap-5" onSubmit={onSubmit}>
            <label className="flex flex-col gap-2">
              <span className="text-[11px] font-semibold uppercase tracking-[0.1em] text-slate-700">
                Workspace / Company name
              </span>
              <div className="flex rounded-none border border-slate-300 bg-white">
                <input
                  type="text"
                  value={workspace}
                  onChange={(e) => setWorkspace(e.target.value)}
                  autoComplete="organization"
                  className="min-w-0 flex-1 rounded-none border-0 bg-transparent px-3.5 py-3 text-sm text-ink"
                />
                <span className="flex items-center rounded-none border-l border-hairline bg-slate-100 px-3.5 font-mono text-[13px] text-slate-500">
                  .mateassist.io
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
                <a href="#reset" className="text-xs">
                  Forgot?
                </a>
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

            <button
              type="submit"
              className="flex items-center justify-center gap-2.5 rounded-none bg-emerald-600 px-5 py-4 text-sm font-semibold tracking-wide text-white transition hover:bg-emerald-700"
            >
              Sign in to workspace
              <ArrowRight size={16} />
            </button>
          </form>

          <p className="mt-8 text-xs leading-relaxed text-slate-400">
            Protected by your organisation&apos;s access policy. Sessions expire after 12 hours of
            inactivity.
          </p>
        </div>
      </div>
    </div>
  );
}
