# Phase 8 — The assistant is the interface

**Status: COMPLETE.** Citations appear only when earned, one runbook can no
longer be answered from another's, the runbook library is administrator-only,
and a conversation survives a refresh. Recorded as A-014 (D-138 to D-143).

---

## 1. The gate

```
205 tests pass (was 190) · ruff clean · black clean
both bundles build · D-100 radius lint clean
gating_demo -> 12/12 cases · exit 0
```

```
Gates: ground >= 0.53  cite >= 0.54

  OK  Hi                            top=0.500  grounded=0  sources=-
  OK  Hello?                        top=0.524  grounded=0  sources=-
  OK  globalprotect wont connect    top=0.736  grounded=1  sources=VPN Runbook (demo)

Document focus (no blending)
  OK  globalprotect wont connect
        retrieved: AnyConnect VPN Runbook, VPN Runbook (demo)
        shown    : VPN Runbook (demo)
```

Retrieval *did* surface the wrong runbook. It never reached the model.

## 2. What was built

| | |
|---|---|
| `retrieval.Hit.similarity` | The real cosine score, previously computed and discarded |
| `retrieval.focus()` | Drop the losing document before the prompt exists |
| `retrieval.gate()` | Two thresholds: ground, then cite |
| `retrieval_probe` | Measures where small talk and real questions separate |
| `seed_runbooks` | Four markdown runbooks, no provider calls |
| `gating_demo` | The phase gate |
| Knowledge API | Administrator-only, reads included |
| Chat UI | Thread sidebar, URL-addressed conversations, two-phase label |

## 3. The decisions

**The score being thresholded had to exist first.** RRF ranks; its top hit
scores `1/(60+1)` regardless of match quality. Gating on it would have run
cleanly and done nothing — a feature that looks implemented.

**Thresholds were measured.** Small talk 0.452–0.524, real questions
0.557–0.743, on the actual corpus. Anyone offering a threshold without that
measurement is guessing.

**Two levels, because the mistakes differ.** Below GROUND the model never sees
the runbook — a wrong answer. Below CITE the answer is identical and a chip
disappears. Borderline questions keep their grounding.

**Blending is prevented by absence, not instruction.** A prompt rule is a
request. Removing the losing document is a guarantee.

**Ambiguity is kept ambiguous.** Within the margin, both documents survive and
the model is told not to merge them. Forcing a winner on a coin-flip discards
the right answer half the time.

**Browsing removed, grounding untouched.** The assistant still reads every
runbook. Only direct access is gone — which is the assistant's whole purpose.

**Citations stored, not shown.** Invisible, free, and the only way to explain a
wrong answer later.

## 4. Found by building it

**The measurement contradicted itself, then agreed.** The first probe reported
*no clean separation* — `"outlook is being weird again"` scored 0.490, below the
best greeting. The corpus was a single VPN runbook; Outlook was not in it, so
the low score was correct and gating it out was the honest outcome.

I changed the probe to **name** the overlapping questions rather than pronounce
pass/fail, because only a human can tell "not in the corpus" from "badly
phrased". After ingesting an Outlook runbook the same question scored **0.684**.
A binary verdict would have told me to abandon a working approach.

**The gap shrinks as the corpus grows.** 0.055 with one document, 0.033 with
five. Greetings creep upward because more text means more chance something
resembles "Hi". This is the number to watch, and it is flagged in settings.

**The knowledge exposure was wider than the menu.** Hiding the Knowledge Base
link would have left `/knowledge/documents/{id}/chunks/` returning full runbook
text to any member. Locking it also broke four things that had to be fixed:
the dashboard's document-count tile, the header search, the "Browse docs" card
and the route itself.

**One test of mine had to go.** A test asserting "retrieval still works after
the lockdown" loaded a 130MB embedding model and hit the network — to prove
something the change cannot affect, since retrieval is raw SQL scoped by RLS and
never touches a DRF permission. Replaced with a cheap assertion that the corpus
is intact; the end-to-end claim is `gating_demo`'s job.

## 5. Honest limitations

- **The thresholds are fitted to five documents.** They will need re-measuring
  against a real corpus, and the shrinking gap suggests a fixed threshold has a
  ceiling. `retrieval_probe` is the tool; the settings comment says so.
- **`focus()` assumes one document answers the question.** True for IT support,
  false for a question genuinely spanning two systems. The margin softens this
  but does not remove it.
- **`Conversation.resolved` is still never set true**, so the portal's
  "Resolved" tile will read zero until something decides a thread ended well.
  Carried since Phase 6.
- **None of the new UI has been opened in a browser.** Endpoints are tested,
  bundles build, but the sidebar, resume and thinking label are unexercised by a
  human.
- **The identity answer is still unconfirmed live** — the free-tier quota has
  been exhausted since Phase 7C.
- **The screenshot paste path still has no live browser run**, carried from
  Phase 6.

## 6. Next — deployment

Target: `mateassist.site` on the VPS at `169.58.114.252`, deployed to
`/opt/MateAssist` via GHCR and CI/CD. Other applications under `/opt` are not to
be touched; their compose and nginx files are reference only.
