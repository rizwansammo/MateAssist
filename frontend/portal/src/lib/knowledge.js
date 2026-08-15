import { api, apiFetch, getAccessToken } from "./api.js";

const BASE_URL = import.meta.env.VITE_API_BASE_URL || "/api/v1";

/**
 * Knowledge base client.
 *
 * Upload bypasses apiFetch because it sends multipart/form-data: setting a
 * Content-Type header manually would omit the multipart boundary the browser
 * generates, and the request would fail in a way that looks like a server bug.
 */
export const knowledgeApi = {
  listDocuments: (params = {}) => {
    const query = new URLSearchParams(params).toString();
    return apiFetch(`/knowledge/documents/${query ? `?${query}` : ""}`);
  },

  listCategories: () => apiFetch("/knowledge/categories/"),

  reindex: (id) => apiFetch(`/knowledge/documents/${id}/reindex/`, { method: "POST" }),

  remove: (id) => apiFetch(`/knowledge/documents/${id}/`, { method: "DELETE" }),

  chunks: (id) => apiFetch(`/knowledge/documents/${id}/chunks/`),

  /** What Gemini said about each figure, and where it sat in the document. */
  assets: (id) => apiFetch(`/knowledge/documents/${id}/assets/`),

  /**
   * Upload a runbook.
   *
   * XHR rather than fetch: fetch still has no upload progress events, and a
   * multi-megabyte runbook with no progress bar looks frozen.
   *
   * The cost of leaving `apiFetch` is that this path does not inherit its
   * refresh-on-401 retry, and that was a real bug: an access token lives 15
   * minutes, so an upload attempted later in a session failed with the raw
   * "Given token not valid for any token type" while every other request in the
   * app silently refreshed and carried on. The retry is reimplemented here
   * rather than the progress bar being given up.
   */
  async upload(file, { title, category, onProgress } = {}) {
    const attempt = (token) =>
      new Promise((resolve, reject) => {
        const form = new FormData();
        form.append("file", file);
        if (title) form.append("title", title);
        if (category) form.append("category", category);

        const request = new XMLHttpRequest();
        request.open("POST", `${BASE_URL}/knowledge/documents/`);
        request.withCredentials = true;
        if (token) request.setRequestHeader("Authorization", `Bearer ${token}`);

        request.upload.onprogress = (event) => {
          if (event.lengthComputable && onProgress) {
            onProgress(Math.round((event.loaded / event.total) * 100));
          }
        };

        request.onload = () => {
          let body = null;
          try {
            body = JSON.parse(request.responseText);
          } catch {
            body = null;
          }
          if (request.status >= 200 && request.status < 300) {
            resolve(body);
          } else {
            const error = new Error(body?.detail || `Upload failed (${request.status})`);
            error.status = request.status;
            reject(error);
          }
        };
        request.onerror = () => reject(new Error("Network error during upload"));
        request.send(form);
      });

    try {
      return await attempt(getAccessToken());
    } catch (error) {
      if (error.status !== 401) throw error;
      // One retry, exactly as apiFetch does. A second 401 means the session is
      // genuinely gone rather than merely stale.
      await api.restoreSession();
      return attempt(getAccessToken());
    }
  }
};

export const ACCEPTED_EXTENSIONS = [".pdf", ".docx", ".md"];

/** Ingestion is asynchronous, so these states are transient and worth polling. */
export const IN_PROGRESS_STATUSES = ["UPLOADED", "PARSING", "DESCRIBING", "EMBEDDING"];

export const STATUS_TONE = {
  UPLOADED: "info",
  PARSING: "info",
  DESCRIBING: "info",
  EMBEDDING: "info",
  INDEXED: "ok",
  FAILED: "warn"
};

export const STATUS_LABEL = {
  UPLOADED: "Queued",
  PARSING: "Parsing",
  DESCRIBING: "Reading images",
  EMBEDDING: "Embedding",
  INDEXED: "Indexed",
  FAILED: "Failed"
};
