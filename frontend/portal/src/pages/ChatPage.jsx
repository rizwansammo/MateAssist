import { useState } from "react";
import { BookOpen, Bot, Check, Send, Terminal, Ticket } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { usePortal } from "../context/PortalContext.jsx";
import { SEED_CITATIONS, SEED_MESSAGES } from "../seed/chat.js";

function Message({ message, onCreateTicket, onOpenTicket, onBrowseDocs }) {
  const isAi = message.role === "ai";

  return (
    <div className={`flex gap-3 ${isAi ? "justify-start" : "justify-end"}`}>
      {isAi && (
        <div className="flex h-[30px] w-[30px] flex-none items-center justify-center rounded-none bg-ink">
          <Bot size={16} strokeWidth={1.8} className="text-emerald-400" />
        </div>
      )}
      <div
        className={`max-w-[680px] rounded-none border p-4 ${
          isAi ? "border-hairline bg-white" : "border-ink bg-ink"
        }`}
      >
        <div className="mb-2 flex items-center gap-2.5">
          <span
            className={`text-[11px] font-semibold uppercase tracking-[0.1em] ${
              isAi ? "text-emerald-700" : "text-emerald-400"
            }`}
          >
            {isAi ? "MateAssist" : "Rizwan Ahmed"}
          </span>
          <span className={`font-mono text-[11px] ${isAi ? "text-slate-400" : "text-slate-500"}`}>
            {message.time}
          </span>
        </div>
        <p
          className={`text-[14.5px] leading-relaxed text-pretty ${
            isAi ? "text-slate-800" : "text-slate-100"
          }`}
        >
          {message.text}
        </p>

        {message.steps && (
          <ol className="mt-3.5 flex list-none flex-col gap-2.5 p-0">
            {message.steps.map((step, index) => (
              <li key={step} className="flex gap-3 text-sm leading-relaxed text-slate-800">
                <span className="flex h-5 w-5 flex-none items-center justify-center rounded-none bg-ink font-mono text-[11px] font-semibold text-emerald-400">
                  {index + 1}
                </span>
                <span>{step}</span>
              </li>
            ))}
          </ol>
        )}

        {message.code && (
          <div className="mt-4 rounded-none border border-ink bg-ink">
            <div className="flex items-center gap-2 border-b border-slate-800 px-3 py-2">
              <Terminal size={14} className="text-emerald-400" />
              <span className="text-[11px] font-semibold uppercase tracking-[0.1em] text-slate-400">
                {message.codeLabel}
              </span>
            </div>
            <pre className="overflow-x-auto px-4 py-3.5 font-mono text-[12.5px] leading-relaxed text-slate-200">
              {message.code}
            </pre>
          </div>
        )}

        {message.source && (
          <div className="mt-3.5 flex items-center gap-2.5 border-t border-hairline pt-3">
            <BookOpen size={14} strokeWidth={1.8} className="text-slate-500" />
            <span className="text-[12.5px] text-slate-500">Source:</span>
            {/* Phase 6 makes this a real link to the cited Knowledge Base document. */}
            <button
              type="button"
              onClick={onBrowseDocs}
              className="rounded-none text-[12.5px] font-medium text-emerald-700"
            >
              {message.source}
            </button>
          </div>
        )}

        {/*
          D-122: DeepSeek's create_ticket tool call renders this button - it never
          executes on its own. The user's click is what creates the ticket.
          Human-in-the-loop on the only mutating tool.
        */}
        {message.hasAction && (
          <div className="mt-4 flex flex-wrap items-center gap-2.5">
            <button
              type="button"
              onClick={onCreateTicket}
              className="flex items-center gap-2 rounded-none bg-emerald-600 px-4 py-2.5 text-[13px] font-semibold text-white transition hover:bg-emerald-700"
            >
              <Ticket size={15} />
              Create Ticket
            </button>
            <button
              type="button"
              onClick={onBrowseDocs}
              className="rounded-none border border-slate-300 bg-white px-4 py-2.5 text-[13px] font-medium text-slate-700 transition hover:bg-slate-50"
            >
              Search docs instead
            </button>
          </div>
        )}

        {message.ticketRef && (
          <div className="mt-3.5 flex flex-wrap items-center gap-3 rounded-none border border-emerald-200 bg-emerald-50 px-4 py-3">
            <Check size={17} strokeWidth={2.5} className="text-emerald-700" />
            <div>
              <div className="text-[13.5px] font-semibold text-emerald-800">
                Ticket {message.ticketRef} - Assigned to Daniel Koch
              </div>
              <div className="mt-0.5 text-[12.5px] text-emerald-700">
                Priority: High - Identity &amp; Access queue - SLA 4h
              </div>
            </div>
            <button
              type="button"
              onClick={onOpenTicket}
              className="ml-auto whitespace-nowrap rounded-none border border-emerald-600 bg-white px-3.5 py-2 text-[12.5px] font-semibold text-emerald-700 transition hover:bg-emerald-100"
            >
              Open ticket
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

export default function ChatPage() {
  const navigate = useNavigate();
  const { createTicket } = usePortal();
  const [messages, setMessages] = useState(SEED_MESSAGES);
  const [draft, setDraft] = useState("");

  const onCreateTicket = () => {
    const ticket = createTicket();
    setMessages((prev) =>
      prev
        .map((m) => (m.hasAction ? { ...m, hasAction: false } : m))
        .concat([
          {
            role: "ai",
            time: "09:12",
            text:
              "Done. I've raised a ticket with your device details, this conversation and the runbooks I checked attached.",
            ticketRef: ticket.id
          }
        ])
    );
  };

  const send = () => {
    if (!draft.trim()) return;
    // Phase 6: POST the turn and stream the reply over SSE.
    setMessages((prev) => prev.concat([{ role: "user", time: "09:14", text: draft.trim() }]));
    setDraft("");
  };

  return (
    <main className="grid min-h-[calc(100vh-66px)] grid-cols-1 xl:grid-cols-[1fr_300px]">
      <section className="flex min-w-0 flex-col border-r border-hairline bg-white">
        <div className="sticky top-[66px] z-10 flex items-center gap-3 border-b border-hairline bg-white px-6 py-4">
          <div className="flex h-[34px] w-[34px] flex-none items-center justify-center rounded-none bg-ink">
            <Bot size={18} strokeWidth={1.8} className="text-emerald-400" />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2.5">
              <span className="font-wordmark text-[15px] uppercase tracking-wide text-ink">
                MateAssist
              </span>
              <span className="inline-flex flex-none items-center gap-1.5 rounded-none border border-emerald-200 bg-emerald-50 px-1.5 py-0.5 text-[10.5px] font-semibold uppercase tracking-wider text-emerald-700">
                <span className="h-1 w-1 rounded-none bg-emerald-600" />
                Online
              </span>
            </div>
            <div className="mt-0.5 truncate text-xs text-slate-500">
              Grounded on your workspace runbooks
            </div>
          </div>
          <div className="ml-auto flex flex-none gap-2">
            <button
              type="button"
              onClick={() => {
                setMessages(SEED_MESSAGES);
                setDraft("");
              }}
              className="flex-none whitespace-nowrap rounded-none border border-slate-300 bg-white px-3.5 py-2 text-[12.5px] font-medium text-slate-700 transition hover:bg-slate-50"
            >
              New chat
            </button>
          </div>
        </div>

        <div className="flex flex-1 flex-col gap-6 bg-[#FCFDFE] px-6 pb-5 pt-7">
          {messages.map((message, index) => (
            <Message
              // Seeded messages have no ids yet; Phase 6 keys on the persisted
              // Message primary key.
              key={`${message.role}-${index}`}
              message={message}
              onCreateTicket={onCreateTicket}
              onOpenTicket={() => navigate("/app/tickets")}
              onBrowseDocs={() => navigate("/app/knowledge")}
            />
          ))}
        </div>

        <div className="sticky bottom-0 border-t border-hairline bg-white px-6 pb-5 pt-4">
          {/*
            Phase 6 (D-091) replaces this with the real composer: clipboard
            paste-screenshot, drag-and-drop, file picker and a thumbnail preview
            with remove-before-send. Attached images go to Gemini for description
            and NEVER to DeepSeek (D-041/D-042).
          */}
          <div className="flex rounded-none border border-slate-300 bg-white">
            <input
              type="text"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && send()}
              placeholder="Describe your issue - MateAssist replies with steps from your company runbooks"
              className="min-w-0 flex-1 rounded-none border-0 bg-transparent px-4 py-3.5 text-sm text-ink"
            />
            <button
              type="button"
              onClick={send}
              className="flex flex-none items-center gap-2 rounded-none bg-ink px-5 text-[13px] font-semibold text-white transition hover:bg-emerald-600"
            >
              Send
              <Send size={15} />
            </button>
          </div>
        </div>
      </section>

      {/*
        D-080: the "Conversation context" block (Device / OS / Location / Entra
        status) is deleted, and no MDM or Entra integration is scoped. The two
        panels below survive because both become real: citations from RAG
        retrieval, and feedback persisted as MessageFeedback (Phase 6).
      */}
      <aside className="hidden flex-col gap-6 bg-white px-5 py-6 xl:flex">
        <div>
          <div className="mb-3 text-[10.5px] font-semibold uppercase tracking-[0.14em] text-slate-500">
            Referenced articles
          </div>
          <div className="flex flex-col gap-px rounded-none border border-hairline bg-hairline">
            {SEED_CITATIONS.map((title) => (
              <button
                key={title}
                type="button"
                onClick={() => navigate("/app/knowledge")}
                className="rounded-none bg-white px-3 py-3 text-left text-[13px] text-ink transition hover:bg-slate-50"
              >
                {title}
              </button>
            ))}
          </div>
        </div>

        <div className="rounded-none border border-hairline bg-slate-50 p-3.5">
          <div className="text-[13px] font-semibold text-ink">Was this helpful?</div>
          <p className="mb-3 mt-1.5 text-[12.5px] leading-relaxed text-slate-500">
            Feedback trains MateAssist on your workspace only.
          </p>
          <div className="flex gap-2">
            <button
              type="button"
              className="flex-1 rounded-none border border-slate-300 bg-white py-2 text-[12.5px] font-medium text-ink transition hover:border-emerald-600 hover:text-emerald-700"
            >
              Yes
            </button>
            <button
              type="button"
              className="flex-1 rounded-none border border-slate-300 bg-white py-2 text-[12.5px] font-medium text-ink transition hover:border-amber-600 hover:text-amber-700"
            >
              No
            </button>
          </div>
        </div>
      </aside>
    </main>
  );
}
