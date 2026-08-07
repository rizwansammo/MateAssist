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

  create: ({ engine, label, secret, weight = 1, daily_quota = null }) =>
    apiFetch("/platform/keys/", {
      method: "POST",
      body: { engine, label, secret, weight, daily_quota }
    }),

  rotate: (id, { label, secret }) =>
    apiFetch(`/platform/keys/${id}/rotate/`, { method: "POST", body: { label, secret } }),

  revoke: (id) => apiFetch(`/platform/keys/${id}/revoke/`, { method: "POST" }),
  purge: (id) => apiFetch(`/platform/keys/${id}/`, { method: "DELETE" }),

  prices: () => apiFetch("/platform/prices/")
};
