/**
 * API client with transparent token refresh.
 *
 * The access token lives in a module variable, never localStorage (D-031): XSS
 * that can read localStorage would harvest a long-lived credential, whereas an
 * in-memory token dies with the tab. The refresh token is an httpOnly cookie
 * this code cannot read at all - it rides along because of `credentials`.
 */

const BASE_URL = import.meta.env.VITE_API_BASE_URL || "/api/v1";

let accessToken = null;
let refreshPromise = null;
const subscribers = new Set();

export function setAccessToken(token) {
  accessToken = token;
}

export function getAccessToken() {
  return accessToken;
}

/** Notified when the session ends so the UI can bounce to /login. */
export function onSessionExpired(handler) {
  subscribers.add(handler);
  return () => subscribers.delete(handler);
}

function announceExpiry() {
  accessToken = null;
  subscribers.forEach((handler) => handler());
}

export class ApiError extends Error {
  constructor(message, { status, body } = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

async function rawFetch(path, { method = "GET", body, signal, headers = {} } = {}) {
  return fetch(`${BASE_URL}${path}`, {
    method,
    signal,
    credentials: "include",
    headers: {
      Accept: "application/json",
      ...(body ? { "Content-Type": "application/json" } : {}),
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      ...headers
    },
    body: body ? JSON.stringify(body) : undefined
  });
}

/**
 * Refresh at most once concurrently. Without this, five parallel requests each
 * hitting 401 would fire five refreshes - and since rotation blacklists the
 * presented token, four of them would invalidate the session they were trying
 * to save.
 */
function refreshSession() {
  if (!refreshPromise) {
    refreshPromise = rawFetch("/auth/refresh/", { method: "POST" })
      .then(async (response) => {
        if (!response.ok) throw new ApiError("Session expired", { status: response.status });
        const session = await response.json();
        accessToken = session.access;
        return session;
      })
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
}

export async function apiFetch(path, options = {}) {
  const isAuthCall = path.startsWith("/auth/");

  let response;
  try {
    response = await rawFetch(path, options);
  } catch (cause) {
    throw new ApiError(`Network request to ${path} failed`, { status: 0, body: String(cause) });
  }

  // One retry, and never for the auth endpoints themselves - refreshing a
  // failed refresh is an infinite loop.
  if (response.status === 401 && !isAuthCall) {
    try {
      await refreshSession();
      response = await rawFetch(path, options);
    } catch {
      announceExpiry();
      throw new ApiError("Session expired", { status: 401 });
    }
  }

  const isJson = (response.headers.get("content-type") || "").includes("application/json");
  const payload = isJson ? await response.json().catch(() => null) : await response.text();

  if (!response.ok) {
    throw new ApiError(`${options.method || "GET"} ${path} failed with ${response.status}`, {
      status: response.status,
      body: payload
    });
  }
  return payload;
}

export const api = {
  health: (signal) => apiFetch("/health/", { signal }),
  /**
   * Password recovery (D-176). Both calls are unauthenticated by necessity -
   * the person cannot sign in, which is the problem being solved.
   */
  requestPasswordReset: (email) =>
    apiFetch("/auth/password-reset/", { method: "POST", body: { email } }),

  confirmPasswordReset: (email, code, newPassword) =>
    apiFetch("/auth/password-reset/confirm/", {
      method: "POST",
      body: { email, code, new_password: newPassword }
    }),

  login: (email, password) =>
    apiFetch("/auth/login/", { method: "POST", body: { email, password } }),
  logout: () => apiFetch("/auth/logout/", { method: "POST" }),
  me: () => apiFetch("/auth/me/"),
  restoreSession: refreshSession
};
