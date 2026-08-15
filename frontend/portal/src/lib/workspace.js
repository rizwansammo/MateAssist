import { apiFetch } from "./api.js";

/**
 * Workspace settings, owned by the tenant's own administrator (D-151).
 *
 * Deliberately narrow. Plan, region and suspension are commercial state owned
 * by the platform - a workspace must not be able to upgrade its own plan or
 * unsuspend itself, so those fields are not here and the API has no serializer
 * field for them either.
 */
export const workspaceApi = {
  settings: (signal) => apiFetch("/workspace/settings/", { signal }),

  /**
   * `smtp_password` is omitted unless the admin typed a new one. Sending an
   * empty string means "clear it", so passing the field unconditionally would
   * wipe a working credential every time someone edited the From address.
   */
  save: (fields) => apiFetch("/workspace/settings/", { method: "PATCH", body: fields }),

  sendTest: (to) => apiFetch("/workspace/mail-test/", { method: "POST", body: { to } })
};
