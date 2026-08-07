import { useState } from "react";
import { Plus } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { StatusBadge } from "../components/StatusBadge.jsx";
import { usePortal } from "../context/PortalContext.jsx";
import { TICKET_STATUSES } from "../seed/tickets.js";

const FILTERS = ["All", ...TICKET_STATUSES];

export default function TicketsPage() {
  const navigate = useNavigate();
  const { tickets, counts } = usePortal();
  const [filter, setFilter] = useState("All");

  // Phase 3 moves filtering server-side (indexed, paginated) rather than
  // slicing a fully-loaded array in the browser.
  const visible = filter === "All" ? tickets : tickets.filter((t) => t.status === filter);

  return (
    <main className="flex flex-col gap-5 px-7 pb-12 pt-8">
      <div className="flex flex-wrap items-end justify-between gap-6">
        <div>
          <h1 className="mb-2 text-[28px] font-semibold tracking-tight text-ink">My tickets</h1>
          <p className="text-sm text-slate-500">
            Everything you have raised in this workspace, including AI-created tickets.
          </p>
        </div>
        <button
          type="button"
          onClick={() => navigate("/app/chat")}
          className="flex items-center gap-2 rounded-none bg-emerald-600 px-4 py-3 text-[13.5px] font-semibold text-white transition hover:bg-emerald-700"
        >
          <Plus size={15} />
          Raise a ticket
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {FILTERS.map((label) => {
          const active = filter === label;
          return (
            <button
              key={label}
              type="button"
              onClick={() => setFilter(label)}
              aria-pressed={active}
              className={`rounded-none border px-3.5 py-2 text-[12.5px] font-medium transition ${
                active
                  ? "border-ink bg-ink text-white"
                  : "border-slate-300 bg-white text-slate-700 hover:bg-slate-50"
              }`}
            >
              {label} <span className="font-mono opacity-70">{counts[label]}</span>
            </button>
          );
        })}
      </div>

      <div className="rounded-none border border-hairline bg-white">
        <div className="overflow-x-auto">
          <table className="w-full border-collapse">
            <thead>
              <tr className="bg-slate-50 text-left text-[10.5px] font-semibold uppercase tracking-[0.12em] text-slate-500">
                <th className="border-b border-hairline px-6 py-3">Ticket ID</th>
                <th className="border-b border-hairline px-4 py-3">Subject</th>
                <th className="border-b border-hairline px-4 py-3">Category</th>
                <th className="border-b border-hairline px-4 py-3">Status</th>
                <th className="border-b border-hairline px-6 py-3">Date</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((ticket) => (
                <tr key={ticket.id} className="transition hover:bg-slate-50">
                  <td className="whitespace-nowrap border-b border-slate-100 px-6 py-4 font-mono text-[12.5px] text-ink">
                    {ticket.id}
                  </td>
                  <td className="border-b border-slate-100 px-4 py-4">
                    <div className="text-[13.5px] font-medium text-ink">{ticket.subject}</div>
                    <div className="mt-0.5 text-xs text-slate-400">{ticket.meta}</div>
                  </td>
                  <td className="border-b border-slate-100 px-4 py-4 text-[13px] text-slate-600">
                    {ticket.category}
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
        <div className="flex items-center justify-between px-6 py-3.5 text-[12.5px] text-slate-500">
          <span>
            Showing {visible.length} of {tickets.length} tickets
          </span>
        </div>
      </div>
    </main>
  );
}
