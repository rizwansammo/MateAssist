# Phase 7C — The product stops naming its vendor

**Status: COMPLETE.** Five defects, every one found by using the running product
rather than by reading the code. Recorded as A-013 (D-135, D-136, D-137).

---

## 1. The gate

```
174 tests pass (was 152) · ruff clean · black clean · migrations clean
both bundles build · D-100 radius lint clean

live, against the running stack:
  workspace usage payload names no vendor          PASS
  raw model list absent from the tenant payload    PASS
  unpriced COUNT still reported                    PASS
  tenant by-model endpoint gone (404)              PASS
  platform owner still sees model names            PASS
  /ai references no deleted field                  PASS
  no hardcoded model names in UI config            PASS
  rate-limit reply names no vendor                 PASS
```

The one that matters, live from the real server:

```
HTTP 429
detail: MateAssist is handling a lot of requests right now. Please try again in a moment.
```

That is the exact toast from the bug report, replaced.

## 2. What was wrong

| # | Defect | Since |
|---|---|---|
| 1 | `/ai` rendered a blank page | A-010 |
| 2 | Raw provider 429 shown to a helpdesk user | Phase 6 |
| 3 | `BudgetExceeded` returned HTTP 500 | Phase 7A |
| 4 | Assistant answered *"I am Gemini, built by Google"* | Phase 6 |
| 5 | Model identifiers leaked to workspace admins | Phase 7A |

Plus: the text adapter reported `"DeepSeek call failed"` for a Gemini call — the
one place naming a vendor named the wrong one.

## 3. The decisions

**Errors map by exception type, never by string matching.** Four sentences, and an
unrecognised exception falls through to the generic one — a new failure mode must
never default to exposing its own text. HTTP status carries what a client needs:
429 back off, 402 act commercially, 503 nothing configured. Returning 502 for all
three would make every failure look like a broken upstream.

**The real error still exists.** `report()` writes it to the log *and* an
`AuditEvent`, so an operator sees the full provider text in System Logs. The user
gains clarity; nobody loses diagnostics.

**The identity rule names no vendor.** "Never say you are Gemini" would be stale
the moment A-010's dropdown selects DeepSeek — and would leave the new vendor free
to introduce itself. A test asserts no vendor string appears anywhere in the
prompt, so the rule cannot rot.

**It declines rather than denies.** Under GDPR Article 28 the customer's contract
already lists its sub-processors, so the fact is disclosed where it belongs. A
product that actively contradicts its own DPA is worse than one that stays quiet.

**Tenants keep the unpriced *count*, lose the *names*.** The count affects whether
they can trust their own cost figure, so removing it would hide something real.
The names identify the vendor, so keeping them defeats the point.

**The UI states roles.** A hardcoded model name in the frontend is a fact with no
source, and both of the old ones had rotted — `deepseek-chat` was never running
and `gemini-2.5-flash` died in A-009. The model actually serving a role now comes
from the database, shown against its key, which is the only place in either app a
model name appears.

## 4. Found by running it

**`/ai` had been dead since A-010 and nobody noticed.** `ENGINES` lost its
`models` field when the vendor became configuration; the component still called
`engine.models.join()`. `undefined.join()` throws, React unmounts the tree, blank
page.

A build cannot catch that. Nor can a type checker. It needed someone to open the
page — and Phase 7B, which touched that very file, only changed its import path.

**`BudgetExceeded` was a latent 500.** It is not an `EngineError`, so it walked
past both handlers in the chat view. Nobody had hit it because no budget was
enforced yet — it would have surfaced the first time a real customer hit a cap,
which is the worst possible moment.

**The gate caught the backend serving stale code.** Three tells at once:
`/usage/by-model/` still answered, the reply used the old prompt, and a failure
returned `502` instead of the new `429`. Port 8000 was held by a *system-Python*
process from an earlier session — my own `uvicorn` had exited 127 on a bad
relative path and never bound. Every "live" check before that had been measuring
old code.

**My own decision numbers collided.** I cited D-131/132/133 in a dozen comments;
those numbers were already taken by upload safety, throttling and the RBAC matrix.
Renumbered to D-135/136/137 before the docs were written, so the citations point
at what they claim.

**Two test bugs of my own**, both worth recording because they are the same class
of mistake: asserting against text whose *shape* I had guessed rather than
checked. One compared a mixed-case string to `.lower()`; the other matched a
phrase that straddles a line break in the wrapped prompt. Fixed by normalising
whitespace in the test rather than reflowing the prompt to suit it — reflowing
production text to satisfy an assertion is backwards.

## 5. Honest limitations

- **The identity fix has no live confirmation yet.** Three tests assert the prompt
  contains the rule and names no vendor, but whether the *model obeys* needs a
  real call, and the free-tier quota was exhausted by this phase's own testing.
  The prompt is verified; the behaviour is not. This is the one claim in 7C
  resting on tests alone.
- **A system prompt is not a security control.** Roleplay framing or "repeat your
  instructions" can still break character. The normal case is reliable; a
  determined user is not stopped.
- **The vendor is still visible to a platform owner**, by design — and inferable
  by anyone who reads the `Retry-After` timing or the response latency. D-136
  stops the product *telling* a workspace; it does not make the choice
  unobservable.
- **One 429 removes the only key for 15 minutes.** The cooldown was sized for
  daily quota exhaustion, not per-minute throttling, so a single burst took the
  assistant offline for a quarter of an hour during this phase's own testing.
  Phase 9 shortens it.

## 6. Next

**Phase 8 — chat experience:** real match score plumbed through retrieval,
two-level citation gating, conversation list and resume, two-phase thinking label.

**Phase 9 — key pool:** Test API button, multi-key add, key priority, per-key test
results, shorter cooldown.
