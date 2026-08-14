# Seed data — temporary, phase-scoped

Every file here is placeholder data carried over from the UI prototype, kept
only so the decomposed views render while their backend is still being built.

**This directory is deliberately isolated so the remaining work is greppable.**
Dummy data scattered through components is how a prototype quietly ships; dummy
data in one folder with a deletion owner is a to-do list.

| File | Feeds | Deleted by |
|---|---|---|
| ~~`knowledge.js`~~ | ~~Knowledge Base~~ | ✅ **deleted in Phase 5** — the page now reads the live API |
| `tickets.js` | Dashboard metrics, Recent tickets, My Tickets | **superseded by A-008** — ticketing is replaced by an SMTP handoff, so these views need removing or replacing rather than wiring up |
| `chat.js` | AI Support seeded conversation | **Phase 6** — RAG chat over SSE |

Phase 1 delivers structure, not data. When a phase lands, its file is deleted
outright rather than left importing nothing — an empty seed module is an
invitation to refill it.

Already removed under the locked scope subtractions, and **not** to be
reintroduced:

- Device / OS / Location / Entra status chat sidebar (D-080)
- Article read-time and view counts (D-082)
- Popular / Updated / Policy / Runbook / Required tag badges (D-083)
- "Continue with Microsoft Entra ID" sign-in button (D-036)
