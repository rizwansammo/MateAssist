import { AlertTriangle, ArrowRight, BookOpen, Bot } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { Metric, Pill, QuickAction } from "@mateassist/ui";

import { useAuth } from "../context/AuthContext.jsx";
import { usePortal } from "../context/PortalContext.jsx";

function greeting(hour) {
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

/** Open / Escalated / Resolved, derived from the fields the backend sets. */
function state(conversation) {
  if (conversation.escalated_at) return { label: "Escalated", tone: "warn" };
  if (conversation.resolved) return { label: "Resolved", tone: "ok" };
  return { label: "Open", tone: "info" };
}

function when(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric"
  });
}

export default function DashboardPage() {
  const navigate = useNavigate();
  const { conversations, counts, loading, error, refresh } = usePortal();
  const { user, role } = useAuth();
  const isAdmin = role === "TENANT_ADMIN";
  const firstName = (user?.display_name ?? "").split(" ")[0] || "there";

  const now = new Date();

  return (
    <main className="flex flex-col gap-7 px-7 pb-12 pt-8">
      <div className="flex flex-wrap items-end justify-between gap-6">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">
            {now.toLocaleDateString("en-GB", {
              weekday: "long",
              day: "numeric",
              month: "long",
              year: "numeric"
            })}
          </div>
          <h1 className="mb-2 mt-2.5 text-[32px] font-semibold tracking-tight text-ink">
            {greeting(now.getHours())}, {firstName}
          </h1>
          <p className="text-[14.5px] text-slate-600">
            {loading
              ? "Loading your requests..."
              : counts.all === 0
                ? "You have not asked the assistant anything yet."
                : `${counts.open} open request${counts.open === 1 ? "" : "s"} of ${counts.all}.`}
          </p>
        </div>
        <button
          type="button"
          onClick={() => navigate("/app/chat")}
          className="flex flex-none items-center gap-2.5 whitespace-nowrap rounded-none bg-emerald-600 px-[18px] py-3 text-[13.5px] font-semibold text-white transition hover:bg-emerald-700"
        >
          <Bot size={16} strokeWidth={1.8} />
          New request
        </button>
      </div>

      {/*
        Every tile maps to a figure the backend actually produces. The
        prototype's "avg. resolution", "assigned engineer" and read-time metrics
        are gone: there is no ticket table behind them (A-008) and no engineer
        assignment model, so they could only ever have been invented.
      */}
      <div className="grid gap-px border border-hairline bg-hairline sm:grid-cols-2 xl:grid-cols-4">
        <Metric
          label="Open requests"
          value={loading ? "--" : counts.open}
          note="Not yet escalated or resolved"
        />
        <Metric
          label="Handed to a human"
          value={loading ? "--" : counts.escalated}
          note="Emailed to your IT team"
          noteClass={counts.escalated ? "text-amber-700" : "text-slate-400"}
        />
        <Metric
          label="Total conversations"
          value={loading ? "--" : counts.all}
          note="Across this workspace account"
        />
        {/*
          Was "Runbooks available", counted by calling the knowledge API. That
          endpoint is administrator-only now (D-140), so for an end user the tile
          would have shown "--" forever after a failed request. Replaced with a
          figure they own.
        */}
        <Metric
          label="Resolved"
          value={loading ? "--" : counts.resolved}
          note="Closed without needing a human"
          noteClass={counts.resolved ? "text-emerald-700" : "text-slate-400"}
        />
      </div>

      <div>
        <div className="mb-3.5 text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">
          Quick actions
        </div>
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          <QuickAction
            onClick={() => navigate("/app/chat")}
            accent="border-t-[3px] border-t-emerald-600 text-emerald-600"
            tint="border-emerald-200 bg-emerald-50"
            icon={<Bot size={19} strokeWidth={1.8} className="text-emerald-700" />}
            title="Ask AI Assistant"
            body="Describe your issue in plain English."
          />
          <QuickAction
            onClick={() => navigate("/app/chat")}
            accent="border-t-[3px] border-t-cyan-600 text-cyan-600"
            tint="border-cyan-200 bg-cyan-50"
            icon={<AlertTriangle size={19} strokeWidth={1.8} className="text-cyan-700" />}
            title="Report an issue"
            body="Paste a screenshot. The assistant reads it and answers from your runbooks."
          />
          {/* Administrators only (D-140): an end user bounced off this route
              would be a dead card. They reach the runbooks by asking. */}
          {isAdmin && (
            <QuickAction
              onClick={() => navigate("/app/knowledge")}
              accent="border-t-[3px] border-t-amber-600 text-amber-600"
              tint="border-amber-200 bg-amber-50"
              icon={<BookOpen size={19} strokeWidth={1.8} className="text-amber-700" />}
              title="Manage runbooks"
              body="Upload and re-index the documents the assistant answers from."
            />
          )}
        </div>
      </div>

      <div className="rounded-none border border-hairline bg-white">
        <div className="flex items-center justify-between border-b border-hairline px-6 py-4">
          <div>
            <div className="text-[15px] font-semibold text-ink">Recent conversations</div>
            <div className="mt-0.5 text-[12.5px] text-slate-500">Your requests, newest first</div>
          </div>
          <button
            type="button"
            onClick={() => navigate("/app/chat")}
            className="flex flex-none items-center gap-2 whitespace-nowrap rounded-none border border-slate-300 bg-white px-3.5 py-2 text-[12.5px] font-medium text-ink transition hover:bg-slate-50"
          >
            Open assistant
            <ArrowRight size={14} />
          </button>
        </div>

        {loading ? (
          <div className="flex flex-col gap-2.5 px-6 py-6" role="status" aria-live="polite">
            <span className="sr-only">Loading conversations</span>
            {[0, 1, 2].map((row) => (
              <div
                key={row}
                className="h-3 animate-pulse rounded-none bg-slate-100"
                style={{ width: `${90 - row * 15}%` }}
              />
            ))}
          </div>
        ) : error ? (
          <div className="px-6 py-10 text-center">
            <div className="text-sm font-semibold text-ink">Could not load your conversations</div>
            <div className="mt-1.5 text-[12.5px] text-slate-500">
              {error.status === 0 ? "The service is unreachable." : error.message}
            </div>
            <button
              type="button"
              onClick={refresh}
              className="mt-4 rounded-none border border-slate-300 bg-white px-4 py-2 text-[12.5px] font-semibold text-ink transition hover:bg-slate-50"
            >
              Try again
            </button>
          </div>
        ) : conversations.length === 0 ? (
          <div className="px-6 py-10 text-center">
            <div className="text-sm font-semibold text-ink">Nothing here yet</div>
            <div className="mt-1.5 text-[12.5px] text-slate-500">
              Ask the assistant a question and it will appear here.
            </div>
            <button
              type="button"
              onClick={() => navigate("/app/chat")}
              className="mt-4 rounded-none bg-emerald-600 px-4 py-2 text-[12.5px] font-semibold text-white transition hover:bg-emerald-700"
            >
              Start a conversation
            </button>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse">
              <thead>
                <tr className="bg-slate-50 text-left text-[10.5px] font-semibold uppercase tracking-[0.12em] text-slate-500">
                  <th className="border-b border-hairline px-6 py-3">Subject</th>
                  <th className="border-b border-hairline px-4 py-3">State</th>
                  <th className="border-b border-hairline px-6 py-3">Updated</th>
                </tr>
              </thead>
              <tbody>
                {conversations.slice(0, 5).map((conversation) => {
                  const badge = state(conversation);
                  return (
                    <tr
                      key={conversation.id}
                      onClick={() => navigate(`/app/chat/${conversation.id}`)}
                      className="cursor-pointer transition hover:bg-slate-50"
                    >
                      <td className="border-b border-slate-100 px-6 py-4 text-[13.5px] text-ink">
                        {conversation.title || "Untitled request"}
                      </td>
                      <td className="border-b border-slate-100 px-4 py-4">
                        <Pill tone={badge.tone}>{badge.label}</Pill>
                      </td>
                      <td className="whitespace-nowrap border-b border-slate-100 px-6 py-4 text-[13px] text-slate-500">
                        {when(conversation.updated_at)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </main>
  );
}
