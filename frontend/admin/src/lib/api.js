/**
 * API client.
 *
 * Defaults to a relative base so dev goes through the Vite proxy and production
 * through the same origin as the SPA - which is what lets the httpOnly refresh
 * cookie (D-032) work identically in both.
 *
 * Phase 2 adds the access-token header and the 401 -> refresh -> retry
 * interceptor here. Deliberately absent for now rather than stubbed: a fake
 * auth path is worse than none, because it looks finished.
 */

const BASE_URL = import.meta.env.VITE_API_BASE_URL || "/api/v1";

export class ApiError extends Error {
  constructor(message, { status, body } = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

export async function apiFetch(path, { method = "GET", body, signal, headers = {} } = {}) {
  let response;
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      method,
      signal,
      // Send cookies so the refresh token flows once Phase 2 issues one.
      credentials: "include",
      headers: {
        Accept: "application/json",
        ...(body ? { "Content-Type": "application/json" } : {}),
        ...headers
      },
      body: body ? JSON.stringify(body) : undefined
    });
  } catch (cause) {
    // fetch only rejects on network failure; an HTTP error still resolves.
    throw new ApiError(`Network request to ${path} failed`, { status: 0, body: String(cause) });
  }

  const isJson = (response.headers.get("content-type") || "").includes("application/json");
  const payload = isJson ? await response.json().catch(() => null) : await response.text();

  if (!response.ok) {
    throw new ApiError(`${method} ${path} failed with ${response.status}`, {
      status: response.status,
      body: payload
    });
  }
  return payload;
}

export const api = {
  /**
   * Dependency health. Returns 200 when healthy or degraded and 503 when a
   * required dependency is down, so a 503 throws ApiError with the body intact.
   */
  health: (signal) => apiFetch("/health/", { signal })
};
