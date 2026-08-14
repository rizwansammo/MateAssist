/**
 * The engine contract, expressed for the UI.
 *
 * Configuration, not data - which is why this lives in lib/ and the seed/
 * directory no longer exists (Phase 7B). Nothing here is a stand-in for a
 * backend response: the key pool reads the live vault API, and these are the
 * labels and provider options the operator UI renders around it.
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
    // A-010 deleted the `provider` and `models` fields from these objects when
    // the vendor became configuration. The page kept reading `engine.models`,
    // and `undefined.join()` crashed the whole route - so /ai rendered blank
    // from A-010 until D-137. `role` replaces both: it describes the job, which
    // is fixed, rather than the vendor, which is not.
    role: "Serves every text workload. Whichever provider fills it.",
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
    role: "Serves every image workload. Whichever provider fills it.",
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
// Which ROLE handles which task. Not which model - that was the old shape, and
// it rotted: this list still claimed `gemini-2.5-flash` months after A-009
// found that model dead, and `deepseek-chat` was never actually running.
//
// A hardcoded model name in the UI is a fact with no source. The role mapping
// is fixed by architecture, so it cannot go stale (D-137). The model actually
// serving a role is shown against its key, where it comes from the database.
export const ENGINE_ASSIGNMENT = [
  { task: "Intent classify", engine: "Text & Reasoning", colour: "text-emerald-300" },
  { task: "Runbook RAG", engine: "Text & Reasoning", colour: "text-emerald-300" },
  { task: "Escalation draft", engine: "Text & Reasoning", colour: "text-emerald-300" },
  { task: "Image / OCR", engine: "Vision & OCR", colour: "text-cyan-300" }
];
