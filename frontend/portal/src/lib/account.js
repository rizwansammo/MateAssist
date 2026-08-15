import { apiFetch } from "./api.js";

/**
 * Your own account (D-158).
 *
 * No id in any path. The server reads request.user and offers no way to name a
 * different account, so this client has no way to ask for one either - the two
 * sides agree that the endpoint is about the caller and nobody else.
 */
export const accountApi = {
  get: (signal) => apiFetch("/account/", { signal }),

  /**
   * `current_password` is only required when the email changes, so the page
   * sends it only then. Demanding it for a name change would be friction with
   * no security to show for it.
   */
  save: (fields) => apiFetch("/account/", { method: "PATCH", body: fields }),

  changePassword: (currentPassword, newPassword) =>
    apiFetch("/account/password/", {
      method: "POST",
      body: { current_password: currentPassword, new_password: newPassword }
    })
};
