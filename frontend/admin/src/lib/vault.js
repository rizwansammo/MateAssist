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

  revoke: (id) => apiFetch(`/platform/keys/${id}/revoke/`, { method: "POST" }),
  purge: (id) => apiFetch(`/platform/keys/${id}/`, { method: "DELETE" }),

  prices: () => apiFetch("/platform/prices/")
};
