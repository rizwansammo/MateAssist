import { useCallback, useEffect, useRef, useState } from "react";
import { AlertTriangle, Bot, Check, Mail, MessageSquare, Plus, Trash2 } from "lucide-react";
import { useNavigate, useParams } from "react-router-dom";

import { AnswerBody } from "../components/AnswerBody.jsx";
import { ChatComposer } from "../components/ChatComposer.jsx";
import { MessageAttachment } from "../components/MessageAttachment.jsx";
import { usePortal } from "../context/PortalContext.jsx";
import { chatApi } from "../lib/chat.js";

/**
 * AI Support - live (Phase 6).
 *
 * D-080 still holds: there is no Device/OS/Location/Entra panel. D-141 removed
 * the right-hand runbook rail and the per-message source chips - they named
 * internal documents the reader cannot open, and pointed at a Knowledge Base
 * that is now administrator-only. The chat is the whole surface.
 *
 * Citations are still stored on every message and still reach the platform
 * admin, so a wrong answer remains explainable. Only the display is gone.
 *
 * A-008: the action button escalates by email rather than creating a ticket.
 * The model proposes; this button is the user's confirmation (D-126).
 *
 * D-142: the open thread lives in the URL, not in component state. Before this,
 * `conversationId` reset to null on every mount - so a refresh, a back button or
 * a stray navigation silently started a new thread and orphaned the old one.
 * The conversations were never lost; there was simply no way back to them.
 */
export default function ChatPage() {
  const { notify } = usePortal();
  const navigate = useNavigate();
  const { conversationId: routeId } = useParams();
  const conversationId = routeId ? Number(routeId) : null;

  const [messages, setMessages] = useState([]);
  const [streaming, setStreaming] = useState("");
  const [busy, setBusy] = useState(false);
  // "searching" until the server signals that retrieval finished, then
  // "writing" (D-143). Retrieval takes about 50ms and the answer takes seconds,
  // so a single "Searching your runbooks..." label was untrue for almost the
  // entire wait.
  const [phase, setPhase] = useState(null);
  const [threads, setThreads] = useState([]);
  const [loadingThread, setLoadingThread] = useState(false);
  const bottomRef = useRef(null);

  // Set when THIS component navigated to a conversation it just created, so the
  // URL-change effect below knows to leave the messages alone.
  //
  // Without it, sending the first message looked broken: the message appeared,
  // then vanished for the whole wait, then reappeared with the answer. Creating
  // the conversation changes the URL, the URL effect fetches from the server,
  // and the server's copy did not yet include the message being sent - so the
  // fetch overwrote it with an empty list.
  const skipNextLoad = useRef(false);

  const loadThreads = useCallback(async () => {
    try {
      const payload = await chatApi.listConversations();
      setThreads(Array.isArray(payload) ? payload : (payload?.results ?? []));
    } catch {
      // The sidebar is navigation, not content. A failed poll must not replace
      // the conversation the user is reading with an error page.
      setThreads([]);
    }
  }, []);

  useEffect(() => {
    loadThreads();
  }, [loadThreads]);

  // Open whatever the URL points at, including on a cold load or a refresh.
  useEffect(() => {
    let live = true;
    if (!conversationId) {
      setMessages([]);
      return undefined;
    }
    // We navigated here ourselves mid-send and already hold the newer state.
    // Refetching now would replace the message the user is watching.
    if (skipNextLoad.current) {
      skipNextLoad.current = false;
      return undefined;
    }
    setLoadingThread(true);
    chatApi
      .getConversation(conversationId)
      .then((conversation) => {
        if (live) setMessages(conversation.messages ?? []);
      })
      .catch(() => {
        if (!live) return;
        // A deleted or foreign id must not strand the user on a blank page.
        notify("That conversation is no longer available", "Starting a new one.", "warn");
        navigate("/app/chat", { replace: true });
      })
      .finally(() => {
        if (live) setLoadingThread(false);
      });
    return () => {
      live = false;
    };
  }, [conversationId, navigate, notify]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streaming]);

  const send = async ({ text, image }) => {
    setBusy(true);
    setStreaming("");
    setPhase("searching");
    // The preview is created before anything is sent, so the screenshot appears
    // in the user's own bubble the instant they press send. Waiting for the
    // server meant the picture arrived after the answer did, which read as the
    // attachment having been lost.
    const previewUrl = image ? URL.createObjectURL(image) : null;
    const optimistic = {
      id: `local-${Date.now()}`,
      role: "user",
      text,
      previewUrl,
      pending: Boolean(image)
    };
    setMessages((prev) => [...prev, optimistic]);

    try {
      // A conversation created here is navigated to, so the URL matches the
      // thread from the first message rather than after a reload.
      let id = conversationId;
      if (!id) {
        const created = await chatApi.createConversation();
        id = created.id;
        skipNextLoad.current = true;
        navigate(`/app/chat/${id}`, { replace: true });
      }

      let collected = "";
      await chatApi.stream(id, { text, image }, (event, data) => {
        if (event === "start") {
          setPhase("writing");
          // The server has persisted the user's message and titled the thread
          // by this point, so the sidebar can show it now rather than after the
          // answer finishes. Waiting made a new conversation look unsaved for
          // the whole wait.
          loadThreads();
        } else if (event === "delta") {
          collected += data.text;
          setStreaming(collected);
        } else if (event === "error") {
          notify("The assistant could not answer", data.detail, "warn");
        }
      });

      // Reload from the server rather than trusting the accumulated text: the
      // persisted message carries the escalation proposal and the real ids that
      // feedback and escalation need.
      const conversation = await chatApi.getConversation(id);
      setMessages(conversation.messages ?? []);
      setStreaming("");
      loadThreads(); // the title and timestamp have just changed
    } catch (error) {
      notify("Message failed", error.message, "warn");
      setMessages((prev) => prev.filter((m) => m.id !== optimistic.id));
    } finally {
      // The persisted message serves its own image from here on, so the local
      // blob is dead weight. Not revoking it leaks every screenshot sent for as
      // long as the tab stays open.
      if (previewUrl) URL.revokeObjectURL(previewUrl);
      setBusy(false);
      setPhase(null);
    }
  };

  const removeThread = async (id, event) => {
    event.stopPropagation();
    if (!window.confirm("Delete this conversation? This cannot be undone.")) return;
    try {
      await chatApi.remove(id);
      setThreads((prev) => prev.filter((t) => t.id !== id));
      if (id === conversationId) navigate("/app/chat", { replace: true });
    } catch (error) {
      notify("Could not delete", error.message, "warn");
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
    setMessages([]);
    setStreaming("");
    navigate("/app/chat");
  };

  return (
    <main className="grid min-h-[calc(100vh-66px)] grid-cols-1 xl:grid-cols-[260px_1fr]">
      <aside className="hidden flex-col border-r border-hairline bg-white xl:flex">
        <div className="sticky top-[66px] z-10 border-b border-hairline bg-white px-4 py-4">
          <button
            type="button"
            onClick={newChat}
            className="flex w-full items-center justify-center gap-2 rounded-none bg-emerald-600 px-3.5 py-2.5 text-[13px] font-semibold text-white transition hover:bg-emerald-700"
          >
            <Plus size={15} strokeWidth={2} />
            New chat
          </button>
        </div>

        <div className="flex flex-col gap-px overflow-y-auto px-4 py-4">
          <div className="mb-1.5 text-[10.5px] font-semibold uppercase tracking-[0.14em] text-slate-500">
            Your conversations
          </div>
          {threads.length === 0 ? (
            <p className="text-[12.5px] leading-relaxed text-slate-400">
              Nothing yet. Ask a question and it will be saved here.
            </p>
          ) : (
            threads.map((thread) => {
              const active = thread.id === conversationId;
              return (
                <button
                  key={thread.id}
                  type="button"
                  onClick={() => navigate(`/app/chat/${thread.id}`)}
                  className={`group flex items-start gap-2.5 rounded-none border-l-2 px-3 py-2.5 text-left transition ${
                    active
                      ? "border-emerald-500 bg-slate-50"
                      : "border-transparent hover:bg-slate-50"
                  }`}
                >
                  <MessageSquare
                    size={14}
                    strokeWidth={1.8}
                    className="mt-0.5 flex-none text-slate-400"
                  />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[13px] text-ink">
                      {thread.title || "New conversation"}
                    </span>
                    <span className="mt-0.5 block text-[11px] text-slate-400">
                      {thread.escalated_at
                        ? "Sent to IT"
                        : `${thread.message_count} message${thread.message_count === 1 ? "" : "s"}`}
                    </span>
                  </span>
                  <span
                    role="button"
                    tabIndex={-1}
                    aria-label="Delete conversation"
                    onClick={(event) => removeThread(thread.id, event)}
                    className="flex-none p-1 text-slate-300 opacity-0 transition hover:text-red-600 group-hover:opacity-100"
                  >
                    <Trash2 size={13} strokeWidth={1.8} />
                  </span>
                </button>
              );
            })
          )}
        </div>
      </aside>

      <section className="flex min-w-0 flex-col bg-white">
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
          {/* The sidebar owns "New chat" on wide screens; this is the
              small-screen equivalent, where the sidebar is hidden. */}
          <button
            type="button"
            onClick={newChat}
            className="ml-auto flex-none whitespace-nowrap rounded-none border border-slate-300 bg-white px-3.5 py-2 text-[12.5px] font-medium text-slate-700 transition hover:bg-slate-50 xl:hidden"
          >
            New chat
          </button>
        </div>

        <div className="flex flex-1 flex-col gap-6 bg-[#FCFDFE] px-6 pb-5 pt-7">
          {loadingThread && messages.length === 0 && (
            <div className="mx-auto py-10 text-[13px] text-slate-400" role="status">
              Opening conversation...
            </div>
          )}

          {!loadingThread && messages.length === 0 && !streaming && (
            <div className="mx-auto max-w-[520px] py-10 text-center">
              <div className="text-[15px] font-semibold text-ink">
                Ask about anything IT
              </div>
              <p className="mt-2 text-[13.5px] leading-relaxed text-slate-500">
                MateAssist answers from your team&apos;s runbooks. Paste a screenshot of an
                error and it will read that too.
              </p>
            </div>
          )}

          {messages.map((message) => (
            <MessageBubble
              key={message.id}
              message={message}
              conversationId={conversationId}
              onEscalate={escalate}
              onRate={rate}
            />
          ))}

          {streaming && (
            <div className="flex gap-3">
              <div className="flex h-[30px] w-[30px] flex-none items-center justify-center rounded-none bg-ink">
                <Bot size={16} strokeWidth={1.8} className="text-emerald-400" />
              </div>
              {/* Rendered as Markdown while it streams, so the answer does not
                  visibly reflow when the persisted copy replaces it. */}
              <div className="max-w-[680px] rounded-none border border-hairline bg-white p-4">
                <AnswerBody text={streaming} />
                <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse bg-emerald-500 align-middle" />
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
                {phase === "writing" ? "Writing your answer..." : "Looking this up..."}
              </div>
            </div>
          )}

          <div ref={bottomRef} />
        </div>

        <ChatComposer onSend={send} busy={busy} />
      </section>

      {/*
        The "Referenced runbooks" rail is gone with the source chips (D-141).
        It listed documents the reader has no access to and linked to a page
        they can no longer open. The chat is now the whole width it occupied.
      */}
    </main>
  );
}

function MessageBubble({ message, conversationId, onEscalate, onRate }) {
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
        {isAi ? (
          <AnswerBody text={message.text} />
        ) : (
          // The user's own words, shown literally. Rendering their message as
          // Markdown would let a stray asterisk change what they appear to
          // have said.
          <p className="whitespace-pre-wrap text-[14.5px] leading-relaxed text-pretty text-slate-100">
            {message.text}
          </p>
        )}

        {/*
          The screenshot itself, not the vision engine's transcription of it.
          Showing the transcription was showing the reader our plumbing: they
          know what they sent, and a wall of machine-read text in place of their
          own picture reads as though the upload went wrong.

          The description is still produced and still stored - it is what the
          text engine reasons over (D-042). It simply is not the user's business.
        */}
        <MessageAttachment message={message} conversationId={conversationId} />

        {/*
          Source chips removed (D-141). They named internal runbooks to end
          users who cannot open them, and pointed at a Knowledge Base that is
          now administrator-only - a label the reader could neither verify nor
          act on.

          The citations are still stored on the message and still reach the
          platform admin, so a wrong answer stays explainable. What is gone is
          only the display.
        */}

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
