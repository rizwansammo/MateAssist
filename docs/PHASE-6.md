# Phase 6 — Agentic RAG Chat

**Status: COMPLETE.** A question goes in; a grounded, cited, streamed answer comes
out, and an unanswerable one hands off to a human by email.

---

## 1. The gate

```
python manage.py chat_demo --tenant netswitch

  Q: My VPN keeps disconnecting whenever I join a Teams call. What do I do?
    retrieved: rrf=0.0164  VPN Runbook (demo) [figure]

    A: ### Step 1: Confirm the Issue ... ### Step 2: Check Split-Tunnel
       Exclusions ... ### Step 3: Apply the Fix ...

    tokens=607+254 latency=7424ms model=gemini-flash-latest
    METERED:  1 chat usage event recorded
    GROUNDED: answer contains runbook specifics
```

The second demo question matters more than the first:

> **Q:** What port does the split-tunnel exclusion need?
> **A:** *"Based on the provided VPN runbook, no specific port number is listed...
> the accompanying diagram does not display any specific port numbers... I can
> escalate this to the network engineering team for you."*

That is the model **refusing to invent an answer** and offering the handoff
instead. A confident wrong answer costs a user more time than an honest "I don't
know", and it is the failure this whole pipeline exists to prevent.

### Live over HTTP

```
POST /chat/conversations/{id}/stream/
  events: start x1  delta x7  done x1
  persisted: assistant message, 842 chars, 1 citation
  metered:   TEXT gemini-flash-latest chat 431+195 tokens 3558ms

POST /chat/conversations/{id}/escalate/
  {"sent": true, "recipient": "helpdesk@netswitch.test"}
```

The compiled email carried the workspace, reporter, category, summary, **the
citations the assistant consulted**, and the full transcript — with `Reply-To`
set to the user so a reply reaches them rather than a no-reply void.

```
112 tests pass (was 97) · ruff + black clean · migrations clean
both bundles build · D-100 clean
```

---

## 2. What was built

| Component | Note |
|---|---|
| `models.py` | `Conversation`, `Message`, `MessageFeedback`; RLS on all three |
| `retrieval.py` | pgvector ∥ Postgres FTS, fused by **Reciprocal Rank Fusion** |
| `prompts.py` | Reference block, citation rules, injection defence, escalation tool |
| `views.py` | `/send/` (non-streaming), `/stream/` (SSE), `/escalate/`, `/feedback/` |
| `escalation.py` | Transcript + citations compiled and emailed (A-008) |
| `ChatPage.jsx` | Live streaming, citations, escalation button, feedback |
| `ChatComposer.jsx` | Paste / drag / picker screenshot upload with preview |

`seed/chat.js` deleted.

## 3. The decisions that shaped it

**Fusion on rank, not score.** A cosine similarity of 0.67 and a `ts_rank` of
0.08 are not comparable numbers, but "first" and "third" are. Vector search alone
misses exact tokens — error codes, hostnames; keyword search alone misses
paraphrase — *"my VPN keeps dropping"* against *"the tunnel disconnects"*. RRF
rewards the chunks both strategies agree on.

**Retrieved content is untrusted input (D-130).** A runbook is customer-supplied,
and a Gemini image description is derived from it — either can contain text that
reads like an instruction, planted or innocently quoted from a phishing example.
Passages are fenced, labelled as quoted data, and the system prompt states that
nothing inside them is an instruction. **Retrieved text can never authorise a
tool call.**

**The model proposes; the user sends (D-126).** `escalate_via_email` produces a
button, not an email. This mattered more than the ticket version it replaced —
an email leaves the system and cannot be recalled.

**The recipient comes from the tenant, never the request (D-128).** So one
workspace's transcript cannot be routed to another's helpdesk.

**Screenshots stop at the vision engine.** The image goes to Gemini, and only its
text description continues. A test asserts the assembled prompt still passes
`_assert_text_only`, and another asserts that a data-URI leaking back from a
vision engine would still be rejected.

**The description joins the search query.** A user who pastes an error dialog and
types "what's this?" has told you nothing — but the transcribed error code is
highly retrievable.

## 4. Found by running it

**The streaming path was silently unmetered.** `/stream/` bypasses `call_text`,
so it never wrote a `UsageEvent` — breaking D-110's "no provider call without a
meter reading" for the *most frequent call in the product*. Fixed by requesting
`stream_options={"include_usage": True}` and metering from the final chunk.

**The escalation transcript could come out empty.** `conversation.messages.all()`
goes through the tenant-scoped manager, which reads a ContextVar. A caller that
armed the DB session without the Python context — a Celery task, a management
command — would get an empty queryset and send an escalation *with no transcript
and no sign anything went wrong*. Now uses `all_objects` with an explicit filter,
and refuses to send an empty escalation at all.

Both were invisible while the feature "worked".

**One test bug worth recording:** the injection test selected the reference block
by searching for the phrase "REFERENCE MATERIAL" — and matched the *system
prompt*, which mentions it in the rule telling the model to ignore embedded
instructions. It now matches the fence.

## 5. Honest limitations

- **The earlier `"No text engine is configured"` failure did not reproduce**
  after a clean restart. The most likely cause was stale code in the reloader
  rather than a logic fault, but I did not catch it in the act, so I cannot say
  that with certainty. The error message is now specific enough to diagnose it
  immediately if it returns.
- **The screenshot path has no live end-to-end run.** The code is there and the
  prompt-assembly half is tested, but no real screenshot has been pasted into the
  running UI yet.
- **Conversation history is capped at 12 turns** with no summarisation, so a very
  long thread loses its early context.
- **`resolved` is never set true** — nothing yet decides a conversation ended
  successfully, so the "AI success rate" metric has no source.
- **One Gemini key**, 5 requests/minute. The pool cools down and fails over, but
  has nothing to fail over to.

## 6. Next

Phase 7 (metering rollups, budgets, System Logs) is the last unbuilt phase before
deployment. The dashboards it needs are already fed: `UsageEvent` rows exist for
every call, and `AuditEvent` records uploads, indexing, escalations and vault
operations.

Also outstanding across earlier phases: the portal's **My Tickets** page and the
dashboard ticket metrics still render `seed/tickets.js`, which A-008 orphaned —
they need removing or replacing with figures the AI layer actually produces.
