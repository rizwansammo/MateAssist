import { apiFetch } from "./api.js";

/**
 * Credential vault client.
 *
 * Note what is absent: there is no `get secret` call, because the API has no
 * endpoint that returns one (D-072). Keys are written and never read back -
 * only `last4` ever comes down the wire.
 */
export const vaultApi = {
  list: (engine) => apiFetch(`/platform/keys/${engine ? `?engine=${engine}` : ""}`),
  poolStatus: () => apiFetch("/platform/keys/pool_status/"),

  // `provider`, `base_url` and `model` are forwarded deliberately (D-149).
  //
  // They were missing here until deployment. A-010 made the vendor a per-key
  // choice and added all three to the API, but this client still destructured
  // the pre-A-010 field list - so whatever the operator selected in the dialog
  // was dropped on the floor, the serializer fell back to its default of
  // OPENAI_COMPATIBLE, and saving a Gemini key failed with "a base URL is
  // required for a generic OpenAI-compatible endpoint".
  //
  // Nothing was wrong with the form or the API. The bug lived entirely in the
  // gap between them, which is why neither side's tests could see it.
  create: ({ engine, provider, base_url, model, label, secret, weight = 1, daily_quota = null }) =>
    apiFetch("/platform/keys/", {
      method: "POST",
      body: { engine, provider, base_url, model, label, secret, weight, daily_quota }
    }),

  // Rotation may also change the provider behind a role - swapping a key from
  // Gemini to DeepSeek is a configuration change, not a new engine (A-010).
  rotate: (id, { provider, base_url, model, label, secret }) =>
    apiFetch(`/platform/keys/${id}/rotate/`, {
      method: "POST",
      body: { provider, base_url, model, label, secret }
    }),

  // Change configuration without re-entering the credential (D-155).
  //
  // Distinct from rotate on purpose. Correcting a model id and replacing a
  // credential are different acts with different risk, and providers retire
  // model names often enough that "delete the key and type the secret again"
  // was the wrong price to pay for a one-word fix.
  reconfigure: (id, fields) =>
    apiFetch(`/platform/keys/${id}/`, { method: "PATCH", body: fields }),

  // One real provider call. A saved key proves nothing on its own: the
  // credential can be valid while the model id is retired, and the first sign
  // of trouble is otherwise a user's failed request.
  check: (id) => apiFetch(`/platform/keys/${id}/check/`, { method: "POST" }),

  revoke: (id) => apiFetch(`/platform/keys/${id}/revoke/`, { method: "POST" }),
  purge: (id) => apiFetch(`/platform/keys/${id}/`, { method: "DELETE" }),

  prices: () => apiFetch("/platform/prices/"),

  // ---- billing (D-160) ----
  //
  // Separate from `prices`, which is what the platform PAYS providers. These
  // are what workspaces are CHARGED. Two endpoints because they are two
  // different numbers, and the gap between them is the margin.
  billingRates: () => apiFetch("/platform/billing-rates/"),
  saveBillingRate: (rate) =>
    apiFetch("/platform/billing-rates/", { method: "POST", body: rate }),
  deleteBillingRate: (id) =>
    apiFetch(`/platform/billing-rates/${id}/`, { method: "DELETE" }),

  /** Derived, never stored - always recomputed from the usage events. */
  statements: (month) => apiFetch(`/platform/statements/?month=${month}`)
};
