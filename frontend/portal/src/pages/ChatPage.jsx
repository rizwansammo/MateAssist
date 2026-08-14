import { useCallback, useEffect, useRef, useState } from "react";
import { AlertTriangle, BookOpen, Bot, Check, Mail } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { ChatComposer } from "../components/ChatComposer.jsx";
import { usePortal } from "../context/PortalContext.jsx";
import { chatApi } from "../lib/chat.js";

/**
 * AI Support - live (Phase 6).
 *
 * D-080 still holds: there is no Device/OS/Location/Entra panel. The right-hand
 * column survives with the two things that became real - citations from actual
 * retrieval, and feedback that is persisted.
 *
 * A-008: the action button escalates by email rather than creating a ticket.
 * The model proposes; this button is the user's confirmation (D-126).
 */
export default function ChatPage() {
  const navigate = useNavigate();
  const { notify } = usePortal();

  const [conversationId, setConversationId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [streaming, setStreaming] = useState("");
  const [busy, setBusy] = useState(false);
  const [citations, setCitations] = useState([]);
  const bottomRef = useRef(null);

  const ensureConversation = useCallback(async () => {
    if (conversationId) return conversationId;
    const created = await chatApi.createConversation();
    setConversationId(created.id);
    return created.id;
  }, [conversationId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streaming]);

  const send = async ({ text, image }) => {
    setBusy(true);
    setStreaming("");
    const optimistic = { id: `local-${Date.now()}`, role: "user", text, pending: Boolean(image) };
    setMessages((prev) => [...prev, optimistic]);

    try {
      const id = await ensureConversation();
      let collected = "";

      await chatApi.stream(id, { text, image }, (event, data) => {
        if (event === "start") {
          setCitations(data.citations ?? []);
        } else if (event === "delta") {
          collected += data.text;
          setStreaming(collected);
        } else if (event === "error") {
          notify("The assistant could not answer", data.detail, "warn");
        }
      });

      // Reload from the server rather than trusting the accumulated text: the
      // persisted message carries citations, the escalation proposal and the
      // real ids that feedback and escalation need.
      const conversation = await chatApi.getConversation(id);
      setMessages(conversation.messages ?? []);
      setStreaming("");
    } catch (error) {
      notify("Message failed", error.message, "warn");
      setMessages((prev) => prev.filter((m) => m.id !== optimistic.id));
    } finally {
      setBusy(false);
    }
  };

  const escalate = async (proposal) => {
    try {
      const result = await chatApi.escalate(conversationId, proposal);
      if (result.sent) {
        notify("Sent to your IT team", `Emailed to ${result.recipient}`);
        const conversation = await chatApi.getConversation(conversationId);
        setMessages(conversation.messages ?? []);
      } else {
        notify("Could not send", result.detail, "warn");
      }
    } catch (error) {
      notify("Could not send", error.message, "warn");
    }
  };

  const rate = async (messageId, helpful) => {
    try {
      await chatApi.feedback(conversationId, messageId, helpful);
      notify("Thanks", helpful ? "Glad that helped." : "Noted - we'll use this to improve.");
    } catch (error) {
      notify("Could not record feedback", error.message, "warn");
    }
  };

  const newChat = () => {
    setConversationId(null);
    setMessages([]);
    setStreaming("");
    setCitations([]);
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
              Answers grounded in your workspace runbooks
            </div>
          </div>
          <button
            type="button"
            onClick={newChat}
            className="ml-auto flex-none whitespace-nowrap rounded-none border border-slate-300 bg-white px-3.5 py-2 text-[12.5px] font-medium text-slate-700 transition hover:bg-slate-50"
          >
            New chat
          </button>
        </div>

        <div className="flex flex-1 flex-col gap-6 bg-[#FCFDFE] px-6 pb-5 pt-7">
          {messages.length === 0 && !streaming && (
            <div className="mx-auto max-w-[520px] py-10 text-center">
              <div className="text-[15px] font-semibold text-ink">
                Ask about anything IT
              </div>
              <p className="mt-2 text-[13.5px] leading-relaxed text-slate-500">
                MateAssist answers from your team&apos;s runbooks and cites the document it used.
                Paste a screenshot of an error and it will read that too.
              </p>
            </div>
          )}

          {messages.map((message) => (
            <MessageBubble
              key={message.id}
              message={message}
              onEscalate={escalate}
              onRate={rate}
              onBrowseDocs={() => navigate("/app/knowledge")}
            />
          ))}

          {streaming && (
            <div className="flex gap-3">
              <div className="flex h-[30px] w-[30px] flex-none items-center justify-center rounded-none bg-ink">
                <Bot size={16} strokeWidth={1.8} className="text-emerald-400" />
              </div>
              <div className="max-w-[680px] rounded-none border border-hairline bg-white p-4">
                <p className="whitespace-pre-wrap text-[14.5px] leading-relaxed text-slate-800">
                  {streaming}
                  <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse bg-emerald-500 align-middle" />
                </p>
              </div>
            </div>
          )}

          {busy && !streaming && (
            <div className="flex items-center gap-3">
              <div className="flex h-[30px] w-[30px] flex-none items-center justify-center rounded-none bg-ink">
                <Bot size={16} strokeWidth={1.8} className="text-emerald-400" />
              </div>
              <div className="flex items-center gap-2.5 rounded-none border border-hairline bg-white px-4 py-3 text-[13.5px] text-slate-500">
                <span className="h-1.5 w-1.5 animate-pulse rounded-none bg-emerald-500" />
                Searching your runbooks...
              </div>
            </div>
          )}

          <div ref={bottomRef} />
        </div>

        <ChatComposer onSend={send} busy={busy} />
      </section>

      <aside className="hidden flex-col gap-6 bg-white px-5 py-6 xl:flex">
        <div>
          <div className="mb-3 text-[10.5px] font-semibold uppercase tracking-[0.14em] text-slate-500">
            Referenced runbooks
          </div>
          {citations.length === 0 ? (
            <p className="text-[12.5px] text-slate-400">
              Sources appear here once you ask a question.
            </p>
          ) : (
            <div className="flex flex-col gap-px rounded-none border border-hairline bg-hairline">
              {citations.map((citation, index) => (
                <button
                  key={`${citation.document_id}-${index}`}
                  type="button"
                  onClick={() => navigate("/app/knowledge")}
                  className="rounded-none bg-white px-3 py-3 text-left transition hover:bg-slate-50"
                >
                  <span className="block text-[13px] text-ink">{citation.title}</span>
                  <span className="mt-0.5 block text-[11.5px] text-slate-400">
                    {citation.page ? `page ${citation.page}` : "runbook"}
                    {citation.from_image ? " - from a figure" : ""}
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>
      </aside>
    </main>
  );
}

function MessageBubble({ message, onEscalate, onRate, onBrowseDocs }) {
  const isAi = message.role === "assistant";

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
        <p
          className={`whitespace-pre-wrap text-[14.5px] leading-relaxed text-pretty ${
            isAi ? "text-slate-800" : "text-slate-100"
          }`}
        >
          {message.text}
        </p>

        {message.attachment_description && (
          <div className="mt-3 rounded-none border border-slate-700 bg-ink2 p-3">
            <div className="text-[10.5px] font-semibold uppercase tracking-[0.1em] text-cyan-400">
              Screenshot read by the vision engine
            </div>
            <p className="mt-1.5 text-[12px] leading-relaxed text-slate-300">
              {message.attachment_description}
            </p>
          </div>
        )}

        {isAi && message.citations?.length > 0 && (
          <div className="mt-3.5 flex flex-wrap items-center gap-2 border-t border-hairline pt-3">
            <BookOpen size={14} strokeWidth={1.8} className="text-slate-500" />
            <span className="text-[12.5px] text-slate-500">Sources:</span>
            {message.citations.map((citation, index) => (
              <button
                key={`${citation.document_id}-${index}`}
                type="button"
                onClick={onBrowseDocs}
                className="rounded-none border border-hairline bg-slate-50 px-2 py-0.5 text-[12px] font-medium text-emerald-700"
              >
                {citation.title}
              </button>
            ))}
          </div>
        )}

        {/* A-008 / D-126: the model proposed this; the click sends it. */}
        {message.proposed_escalation && (
          <div className="mt-4 rounded-none border border-amber-200 bg-amber-50 p-3.5">
            <div className="flex gap-2.5">
              <AlertTriangle
                size={16}
                strokeWidth={2}
                className="mt-0.5 flex-none text-amber-700"
              />
              <div className="min-w-0">
                <div className="text-[13px] font-semibold text-amber-900">
                  This needs a human
                </div>
                <p className="mt-1 text-[12.5px] leading-relaxed text-amber-800">
                  {message.proposed_escalation.summary}
                </p>
              </div>
            </div>
            <button
              type="button"
              onClick={() => onEscalate(message.proposed_escalation)}
              className="mt-3 flex items-center gap-2 rounded-none bg-emerald-600 px-4 py-2.5 text-[13px] font-semibold text-white transition hover:bg-emerald-700"
            >
              <Mail size={15} />
              Email my IT team
            </button>
          </div>
        )}

        {isAi && !String(message.id).startsWith("local-") && (
          <div className="mt-3 flex items-center gap-2 border-t border-hairline pt-3">
            <span className="text-[12px] text-slate-500">Was this helpful?</span>
            <button
              type="button"
              onClick={() => onRate(message.id, true)}
              className="rounded-none border border-slate-300 bg-white px-2.5 py-1 text-[12px] font-medium text-ink transition hover:border-emerald-600 hover:text-emerald-700"
            >
              Yes
            </button>
            <button
              type="button"
              onClick={() => onRate(message.id, false)}
              className="rounded-none border border-slate-300 bg-white px-2.5 py-1 text-[12px] font-medium text-ink transition hover:border-amber-600 hover:text-amber-700"
            >
              No
            </button>
          </div>
        )}

        {message.id === "local-pending" && <Check size={0} />}
      </div>
    </div>
  );
}
