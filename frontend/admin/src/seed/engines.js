// TEMPORARY - key rows deleted by Phase 4 (credential vault API).
// The ENGINES definition below is NOT seed data: it is the D-040/D-041 contract
// expressed for the UI, and it survives Phase 4.

/**
 * The two engines, and only two.
 *
 * Groq and OpenAI are gone entirely (D-044/D-085) - not disabled, not hidden
 * behind a flag. There is no fallback provider in v1.
 *
 * `receives` is rendered in the UI on purpose. The separation is the product's
 * central safety property, so an operator looking at the key vault should be
 * able to read what each engine is permitted to see.
 */
export const ENGINES = [
  {
    id: "text",
    section: "Text & Reasoning Engine",
    provider: "DeepSeek",
    purpose: "Intent classification, RAG answering, ticket drafting, tool calling.",
    receives: "Text only - text chunks, image descriptions, conversation history.",
    neverReceives: "Images. TextEngine has no parameter capable of carrying one.",
    models: ["deepseek-chat", "deepseek-reasoner"],
    accent: "border-t-emerald-600",
    tone: "ok",
    keyPlaceholder: "sk-..."
  },
  {
    id: "vision",
    section: "Vision & OCR Engine",
    provider: "Gemini",
    purpose: "Image description and OCR during runbook ingestion and chat screenshots.",
    receives: "Images. Returns text, and is called for nothing else.",
    neverReceives: "Chat history, retrieved chunks, or any reasoning workload.",
    models: ["gemini-2.5-flash"],
    accent: "border-t-cyan-600",
    tone: "info",
    keyPlaceholder: "AIzaSy..."
  }
];

export const SEED_KEYS = {
  text: [
    { id: "dk1", label: "deepseek-primary", last4: "9f2a", status: "Active", requests: "8,412", lastUsed: "12 seconds ago", added: "14 Mar 2026", quota: "unlimited" },
    { id: "dk2", label: "deepseek-secondary", last4: "1c77", status: "Active", requests: "6,180", lastUsed: "41 seconds ago", added: "2 Apr 2026", quota: "unlimited" },
    { id: "dk3", label: "deepseek-legacy", last4: "04be", status: "Revoked", requests: "0", lastUsed: "12 Jul 2026", added: "6 Nov 2025", quota: "-" }
  ],
  vision: [
    { id: "gk1", label: "gemini-pool-01", last4: "syD3", status: "Active", requests: "1,204", lastUsed: "3 seconds ago", added: "14 Mar 2026", quota: "1,500 req/day" },
    { id: "gk2", label: "gemini-pool-02", last4: "syQ8", status: "Active", requests: "1,187", lastUsed: "1 minute ago", added: "14 Mar 2026", quota: "1,500 req/day" },
    { id: "gk3", label: "gemini-pool-03", last4: "syM1", status: "Rate-limited", requests: "1,500", lastUsed: "8 minutes ago", added: "2 Sep 2025", quota: "1,500 req/day" }
  ]
};

export const KEY_STATUS_TONE = {
  Active: "ok",
  "Rate-limited": "warn",
  Revoked: "off"
};

/**
 * D-045: with two engines holding fixed, non-overlapping roles there is nothing
 * to route, so this is a read-only statement of the contract rather than the
 * prototype's policy toggles. Only tenantCaps survived (D-086), and it lives on
 * the billing page where it belongs.
 */
export const ENGINE_ASSIGNMENT = [
  { task: "Intent classify", engine: "DeepSeek", model: "deepseek-chat", colour: "text-emerald-300" },
  { task: "Runbook RAG", engine: "DeepSeek", model: "deepseek-chat", colour: "text-emerald-300" },
  { task: "Ticket drafting", engine: "DeepSeek", model: "deepseek-chat", colour: "text-emerald-300" },
  { task: "Image / OCR", engine: "Gemini", model: "gemini-2.5-flash", colour: "text-cyan-300" }
];
