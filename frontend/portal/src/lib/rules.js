import { apiFetch } from "./api.js";

/**
 * Workspace assistant rules (D-167).
 *
 * One row per rule, replacing the single instructions textarea. Reordering is
 * one request carrying the whole list rather than a move-up/move-down endpoint:
 * dragging three rules would otherwise be three round trips, and a failure
 * halfway through would leave an order nobody chose.
 */
export const rulesApi = {
  list: (signal) => apiFetch("/workspace/rules/", { signal }),

  create: (text) => apiFetch("/workspace/rules/", { method: "POST", body: { text } }),

  update: (id, fields) =>
    apiFetch(`/workspace/rules/${id}/`, { method: "PATCH", body: fields }),

  remove: (id) => apiFetch(`/workspace/rules/${id}/`, { method: "DELETE" }),

  reorder: (ids) =>
    apiFetch("/workspace/rules/reorder/", { method: "POST", body: { ids } })
};
