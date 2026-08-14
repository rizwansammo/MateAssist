import { apiFetch, getAccessToken } from "./api.js";

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

async function rawPost(path, body, signal) {
  const token = getAccessToken();
  const response = await fetch(`${BASE_URL}${path}`, {
    method: "POST",
    credentials: "include",
    signal,
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body
  });
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
