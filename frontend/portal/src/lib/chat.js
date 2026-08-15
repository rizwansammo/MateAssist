import { api, apiFetch, getAccessToken } from "./api.js";

const BASE_URL = import.meta.env.VITE_API_BASE_URL || "/api/v1";

/**
 * Chat client.
 *
 * Streaming uses fetch + ReadableStream rather than EventSource, for two
 * reasons EventSource cannot handle: the turn is a POST (it carries the message
 * and possibly a screenshot), and it needs an Authorization header.
 */
export const chatApi = {
  listConversations: () => apiFetch("/chat/conversations/"),
  getConversation: (id) => apiFetch(`/chat/conversations/${id}/`),
  createConversation: () => apiFetch("/chat/conversations/", { method: "POST", body: {} }),
  remove: (id) => apiFetch(`/chat/conversations/${id}/`, { method: "DELETE" }),

  send: (id, { text, image }) => {
    const form = new FormData();
    form.append("text", text ?? "");
    if (image) form.append("image", image);
    return rawPost(`/chat/conversations/${id}/send/`, form).then((r) => r.json());
  },

  /**
   * Fetch a message's screenshot as an object URL.
   *
   * Not an <img src> pointing straight at the endpoint: the access token lives
   * in memory rather than a cookie (D-031), and an image request carries no
   * Authorization header. Fetching the blob keeps the same authenticated path -
   * including the refresh-on-401 retry - as every other call.
   *
   * The caller owns the returned URL and must revokeObjectURL it, or every
   * screenshot viewed stays in memory for the life of the tab.
   */
  async attachmentUrl(conversationId, messageId) {
    const response = await rawGet(
      `/chat/conversations/${conversationId}/messages/${messageId}/attachment/`
    );
    return URL.createObjectURL(await response.blob());
  },

  escalate: (id, proposal) =>
    apiFetch(`/chat/conversations/${id}/escalate/`, { method: "POST", body: { proposal } }),

  feedback: (id, messageId, helpful) =>
    apiFetch(`/chat/conversations/${id}/feedback/`, {
      method: "POST",
      body: { message: messageId, helpful }
    }),

  /**
   * Stream a turn. Calls onEvent(name, data) for each SSE event.
   *
   * The buffer is split on the SSE record separator rather than per-read,
   * because a network read can land mid-event - splitting on chunk boundaries
   * produces truncated JSON that only shows up under load.
   */
  async stream(id, { text, image }, onEvent, signal) {
    const form = new FormData();
    form.append("text", text ?? "");
    if (image) form.append("image", image);

    const response = await rawPost(`/chat/conversations/${id}/stream/`, form, signal);
    if (!response.body) throw new Error("Streaming is not supported by this browser.");

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let separator = buffer.indexOf("\n\n");
      while (separator !== -1) {
        const record = buffer.slice(0, separator);
        buffer = buffer.slice(separator + 2);

        const nameLine = record.split("\n").find((l) => l.startsWith("event: "));
        const dataLine = record.split("\n").find((l) => l.startsWith("data: "));
        if (nameLine && dataLine) {
          try {
            onEvent(nameLine.slice(7).trim(), JSON.parse(dataLine.slice(6)));
          } catch {
            // A malformed record must not kill the stream.
          }
        }
        separator = buffer.indexOf("\n\n");
      }
    }
  }
};

/**
 * POST multipart, outside apiFetch because these carry a FormData body and, for
 * the stream, need the raw Response rather than parsed JSON.
 *
 * The refresh-on-401 retry is reimplemented here deliberately. An access token
 * lives 15 minutes; without this, a user who left the tab open over lunch got a
 * hard failure on their next message while every other request in the app
 * refreshed silently. Leaving apiFetch means giving up its behaviour, so the
 * behaviour has to be restored, not assumed.
 */
async function rawGet(path, retrying = false) {
  const token = getAccessToken();
  const response = await fetch(`${BASE_URL}${path}`, {
    credentials: "include",
    headers: token ? { Authorization: `Bearer ${token}` } : {}
  });

  if (response.status === 401 && !retrying) {
    await api.restoreSession();
    return rawGet(path, true);
  }
  if (!response.ok) throw new Error(`Could not load the attachment (${response.status})`);
  return response;
}

async function rawPost(path, body, signal, retrying = false) {
  const token = getAccessToken();
  const response = await fetch(`${BASE_URL}${path}`, {
    method: "POST",
    credentials: "include",
    signal,
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body
  });

  if (response.status === 401 && !retrying) {
    // One retry only. A second 401 means the session is genuinely gone rather
    // than merely stale, and retrying a failed refresh is an infinite loop.
    await api.restoreSession();
    return rawPost(path, body, signal, true);
  }

  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const payload = await response.json();
      detail = payload.detail || detail;
    } catch {
      /* keep the generic message */
    }
    throw new Error(detail);
  }
  return response;
}
