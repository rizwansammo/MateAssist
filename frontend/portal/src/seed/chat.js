// TEMPORARY - deleted by Phase 6 (RAG chat over SSE). See seed/README.md.
//
// The Phase 6 turn is: retrieve (pgvector + FTS, fused by RRF) -> DeepSeek with
// citations -> stream over SSE. A create_ticket tool call renders the action
// button but NEVER executes on its own; the user's click executes it (D-122).

const CACHE_CODE = `ipconfig /flushdns
ipconfig /registerdns

# verify the cache is empty
ipconfig /displaydns | findstr /c:"Record Name"`;

export const SEED_MESSAGES = [
  {
    role: "ai",
    time: "09:02",
    text:
      "Morning, Rizwan. I'm MateAssist - I can resolve issues from Netswitch's runbooks, action licence and access requests, and open a ticket with an engineer when something needs hands-on work."
  },
  { role: "user", time: "09:04", text: "How do I clear my cache?" },
  {
    role: "ai",
    time: "09:04",
    text:
      "Netswitch devices need both the browser cache and the DNS resolver cache cleared - stale DNS is the usual cause of intranet pages failing to load. Here's the full sequence for Windows 11:",
    steps: [
      'In Edge, press Ctrl + Shift + Delete, set the range to "All time", tick Cached images and files, then select Clear now.',
      "Open Terminal as administrator (Win + X -> Terminal (Admin)).",
      "Run the two commands below to flush the DNS resolver and re-register your adapter.",
      "Reopen intranet.netswitch.net - if it still fails, reconnect the VPN once."
    ],
    codeLabel: "Windows Terminal (Admin)",
    code: CACHE_CODE,
    source: "KB-0142 - Clear browser and DNS cache"
  },
  { role: "user", time: "09:11", text: "My office 365 password is not working." },
  {
    role: "ai",
    time: "09:11",
    text:
      "Your password expired on 3 August and self-service reset is blocked because your MFA phone was replaced last week. That needs an identity engineer to verify you - I couldn't find a fix you can run yourself. Would you like me to create a support ticket for you?",
    hasAction: true
  }
];

/** Citations resolve to real Knowledge Base documents from Phase 6 onward. */
export const SEED_CITATIONS = [
  "Clear browser & DNS cache",
  "Reset your Microsoft 365 password",
  "Enrol a new device in MFA"
];
