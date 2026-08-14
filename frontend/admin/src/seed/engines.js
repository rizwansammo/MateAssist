/**
 * The engine contract, expressed for the UI.
 *
 * NOT seed data - this survives every phase. `SEED_KEYS` is gone: the key pool
 * tables now read the live vault API (Phase 4).
 *
 * Groq and OpenAI are absent entirely (D-044/D-085). There is no fallback
 * provider in v1.
 *
 * `receives` / `neverReceives` are rendered in the operator UI on purpose. The
 * separation is the product's central safety property, so someone standing in
 * the credential vault should be able to read what each engine may see.
 */
export const ENGINES = [
  {
    id: "TEXT",
    section: "Text & Reasoning Engine",
    purpose: "Intent classification, RAG answering, escalation drafting, tool calling.",
    receives: "Text only - text chunks, image descriptions, conversation history.",
    neverReceives: "Images. TextEngine has no parameter capable of carrying one.",
    accent: "border-t-emerald-600",
    tone: "ok",
    keyPlaceholder: "sk-... / AQ...."
  },
  {
    id: "VISION",
    section: "Vision & OCR Engine",
    purpose: "Image description and OCR during runbook ingestion and chat screenshots.",
    receives: "Images. Returns text, and is called for nothing else.",
    neverReceives: "Chat history, retrieved chunks, or any reasoning workload.",
    accent: "border-t-cyan-600",
    tone: "info",
    keyPlaceholder: "AQ.... / sk-..."
  }
];

/**
 * A-010: the engine is a ROLE, the provider is who serves it.
 *
 * Swapping a provider never touches the engine contract - a TEXT key still
 * cannot carry an image, whoever is behind it.
 *
 * Most vendors speak the OpenAI protocol, so one adapter covers DeepSeek,
 * OpenAI, Groq, OpenRouter, Together, Mistral and Ollama.
 */
export const PROVIDERS = [
  {
    id: "DEEPSEEK",
    label: "DeepSeek",
    roles: ["TEXT"],
    defaultBaseUrl: "https://api.deepseek.com",
    defaultModel: "deepseek-chat",
    needsBaseUrl: false
  },
  {
    id: "GEMINI",
    label: "Google Gemini",
    roles: ["TEXT", "VISION"],
    defaultBaseUrl: "https://generativelanguage.googleapis.com/v1beta/openai/",
    defaultModel: "gemini-flash-latest",
    defaultVisionModel: "gemini-3.6-flash",
    needsBaseUrl: false
  },
  {
    id: "OPENAI_COMPATIBLE",
    label: "OpenAI-compatible endpoint",
    hint: "OpenAI, Groq, OpenRouter, Together, Mistral, Ollama...",
    roles: ["TEXT", "VISION"],
    defaultBaseUrl: "",
    defaultModel: "",
    needsBaseUrl: true
  }
];

export function providersFor(engineId) {
  return PROVIDERS.filter((p) => p.roles.includes(engineId));
}

export const KEY_STATUS_TONE = {
  ACTIVE: "ok",
  RATE_LIMITED: "warn",
  REVOKED: "off"
};

export const KEY_STATUS_LABEL = {
  ACTIVE: "Active",
  RATE_LIMITED: "Rate-limited",
  REVOKED: "Revoked"
};

/**
 * D-045: with two engines in fixed, non-overlapping roles there is nothing to
 * route. This is a read-only statement of the contract, not a policy panel.
 */
export const ENGINE_ASSIGNMENT = [
  { task: "Intent classify", model: "deepseek-chat", colour: "text-emerald-300" },
  { task: "Runbook RAG", model: "deepseek-chat", colour: "text-emerald-300" },
  { task: "Escalation draft", model: "deepseek-chat", colour: "text-emerald-300" },
  { task: "Image / OCR", model: "gemini-2.5-flash", colour: "text-cyan-300" }
];
