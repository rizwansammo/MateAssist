import { apiFetch, getAccessToken } from "./api.js";

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

  async upload(file, { title, category, onProgress } = {}) {
    const form = new FormData();
    form.append("file", file);
    if (title) form.append("title", title);
    if (category) form.append("category", category);

    // XHR rather than fetch: fetch still has no upload progress events, and a
    // runbook upload with no progress bar looks frozen.
    return new Promise((resolve, reject) => {
      const request = new XMLHttpRequest();
      request.open("POST", `${BASE_URL}/knowledge/documents/`);
      request.withCredentials = true;

      const token = getAccessToken();
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
          reject(new Error(body?.detail || `Upload failed (${request.status})`));
        }
      };
      request.onerror = () => reject(new Error("Network error during upload"));
      request.send(form);
    });
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
