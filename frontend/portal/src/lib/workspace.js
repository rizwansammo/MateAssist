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

  save: ({ assistant_instructions, support_email }) =>
    apiFetch("/workspace/settings/", {
      method: "PATCH",
      body: { assistant_instructions, support_email }
    })
};
