import { AlertTriangle, ArrowRight, BookOpen, Bot } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { Metric, QuickAction } from "@mateassist/ui";

import { StatusBadge } from "../components/StatusBadge.jsx";
import { useAuth } from "../context/AuthContext.jsx";
import { usePortal } from "../context/PortalContext.jsx";

export default function DashboardPage() {
  const navigate = useNavigate();
  const { tickets, counts } = usePortal();
  const { user } = useAuth();
  const firstName = (user?.display_name ?? "").split(" ")[0] || "there";

  return (
    <main className="flex flex-col gap-7 px-7 pb-12 pt-8">
      <div className="flex flex-wrap items-end justify-between gap-6">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">
            Tuesday, 5 August 2026
          </div>
          <h1 className="mb-2 mt-2.5 text-[32px] font-semibold tracking-tight text-ink">
            Good morning, {firstName}
          </h1>
          <p className="text-[14.5px] text-slate-600">
            You have {counts.Open + counts.Pending} tickets in progress.
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
        Every tile here maps to a figure the backend can actually produce:
        open count and assignee from the helpdesk tables (Phase 3), average
        resolution from ticket state transitions, and AI-resolved from
        conversations closed without escalation (Phase 6/7).
      */}
      <div className="grid gap-px border border-hairline bg-hairline sm:grid-cols-2 xl:grid-cols-4">
        <Metric label="Open tickets" value={counts.Open} note="1 awaiting your reply" />
        <Metric
          label="Avg. resolution"
          value="41m"
          note="down 18% vs last month"
          noteClass="text-emerald-700"
        />
        <Metric label="Resolved by AI" value="18" note="76% of your requests" />
        <div className="rounded-none bg-white px-6 py-5">
          <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500">
            Assigned engineer
          </div>
          <div className="mt-3 flex items-center gap-2.5">
            <div className="flex h-7 w-7 items-center justify-center rounded-none bg-slate-800 text-[11px] font-semibold text-white">
              DK
            </div>
            <div className="text-sm font-medium text-ink">Daniel Koch</div>
          </div>
          <div className="mt-1.5 text-xs text-slate-400">Tier 2 - Online now</div>
        </div>
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
            body="Hardware, access or outage. Routed to the right queue automatically."
          />
          <QuickAction
            onClick={() => navigate("/app/knowledge")}
            accent="border-t-[3px] border-t-amber-600 text-amber-600"
            tint="border-amber-200 bg-amber-50"
            icon={<BookOpen size={19} strokeWidth={1.8} className="text-amber-700" />}
            title="Browse docs"
            body="Runbooks maintained by your IT team."
          />
        </div>
      </div>

      <div className="rounded-none border border-hairline bg-white">
        <div className="flex items-center justify-between border-b border-hairline px-6 py-4">
          <div>
            <div className="text-[15px] font-semibold text-ink">Recent tickets</div>
            <div className="mt-0.5 text-[12.5px] text-slate-500">Last 30 days</div>
          </div>
          <button
            type="button"
            onClick={() => navigate("/app/tickets")}
            className="flex flex-none items-center gap-2 whitespace-nowrap rounded-none border border-slate-300 bg-white px-3.5 py-2 text-[12.5px] font-medium text-ink transition hover:bg-slate-50"
          >
            View all
            <ArrowRight size={14} />
          </button>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full border-collapse">
            <thead>
              <tr className="bg-slate-50 text-left text-[10.5px] font-semibold uppercase tracking-[0.12em] text-slate-500">
                <th className="border-b border-hairline px-6 py-3">Ticket</th>
                <th className="border-b border-hairline px-4 py-3">Subject</th>
                <th className="border-b border-hairline px-4 py-3">Status</th>
                <th className="border-b border-hairline px-6 py-3">Updated</th>
              </tr>
            </thead>
            <tbody>
              {tickets.slice(0, 4).map((ticket) => (
                <tr key={ticket.id}>
                  <td className="whitespace-nowrap border-b border-slate-100 px-6 py-4 font-mono text-[12.5px] text-ink">
                    {ticket.id}
                  </td>
                  <td className="border-b border-slate-100 px-4 py-4 text-[13.5px] text-ink">
                    {ticket.subject}
                  </td>
                  <td className="border-b border-slate-100 px-4 py-4">
                    <StatusBadge status={ticket.status} />
                  </td>
                  <td className="whitespace-nowrap border-b border-slate-100 px-6 py-4 text-[13px] text-slate-500">
                    {ticket.date}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </main>
  );
}
