import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, FileText, Image, RefreshCw, Search, Trash2 } from "lucide-react";
import { Pill } from "@mateassist/ui";

import { RunbookUpload } from "../components/RunbookUpload.jsx";
import { useAuth } from "../context/AuthContext.jsx";
import { usePortal } from "../context/PortalContext.jsx";
import {
  IN_PROGRESS_STATUSES,
  STATUS_LABEL,
  STATUS_TONE,
  knowledgeApi
} from "../lib/knowledge.js";

/**
 * Knowledge base - live (Phase 5).
 *
 * Scope subtractions still hold: no read time, no view counts (D-082), and the
 * badge is Document.status, a real ingestion state, not a marketing label
 * (D-083). Rows show what the pipeline actually produced.
 */
export default function KnowledgeBasePage() {
  const { role } = useAuth();
  const { notify } = usePortal();
  const isTenantAdmin = role === "TENANT_ADMIN";

  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [expanded, setExpanded] = useState(null);
  const [detail, setDetail] = useState({ chunks: [], assets: [] });
  const pollRef = useRef(null);

  const load = useCallback(async () => {
    try {
      const response = await knowledgeApi.listDocuments();
      setDocuments(Array.isArray(response) ? response : (response?.results ?? []));
    } catch (error) {
      notify("Could not load runbooks", error?.message ?? "Request failed", "warn");
    } finally {
      setLoading(false);
    }
  }, [notify]);

  useEffect(() => {
    load();
  }, [load]);

  // Ingestion is asynchronous - parse, then a vision call per figure, then
  // embedding - so a document can sit in a transient state for a while. Poll
  // only while something is actually moving, and stop as soon as it settles.
  const hasWorkInFlight = useMemo(
    () => documents.some((d) => IN_PROGRESS_STATUSES.includes(d.status)),
    [documents]
  );

  useEffect(() => {
    if (!hasWorkInFlight) {
      clearInterval(pollRef.current);
      return undefined;
    }
    pollRef.current = setInterval(load, 3000);
    return () => clearInterval(pollRef.current);
  }, [hasWorkInFlight, load]);

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return documents;
    return documents.filter((d) => d.title.toLowerCase().includes(needle));
  }, [documents, query]);

  const openDetail = async (document) => {
    if (expanded === document.id) {
      setExpanded(null);
      return;
    }
    setExpanded(document.id);
    setDetail({ chunks: [], assets: [] });
    try {
      const [chunks, assets] = await Promise.all([
        knowledgeApi.chunks(document.id),
        knowledgeApi.assets(document.id)
      ]);
      setDetail({ chunks: chunks ?? [], assets: assets ?? [] });
    } catch (error) {
      notify("Could not load details", error?.message ?? "Request failed", "warn");
    }
  };

  const reindex = async (document) => {
    try {
      await knowledgeApi.reindex(document.id);
      notify("Re-indexing", `${document.title} was queued`);
      load();
    } catch (error) {
      notify("Re-index failed", error?.message ?? "Request failed", "warn");
    }
  };

  const remove = async (document) => {
    try {
      await knowledgeApi.remove(document.id);
      notify("Runbook removed", document.title, "warn");
      load();
    } catch (error) {
      notify("Delete failed", error?.message ?? "Request failed", "warn");
    }
  };

  return (
    <main className="flex flex-col gap-7 px-7 pb-12 pt-8">
      <div className="rounded-none border border-hairline bg-ink px-8 py-9">
        <h1 className="mb-2.5 text-[28px] font-semibold tracking-tight text-white">
          Knowledge base
        </h1>
        <p className="mb-5 max-w-[620px] text-[14.5px] text-slate-400 text-pretty">
          Runbooks maintained by your IT team. MateAssist answers from these same documents, so
          anything here is grounded truth.
        </p>
        <div className="flex max-w-[620px] rounded-none border border-slate-800 bg-ink2">
          <div className="flex items-center px-3.5">
            <Search size={17} className="text-emerald-400" />
          </div>
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search runbooks by title"
            aria-label="Search runbooks"
            className="min-w-0 flex-1 rounded-none border-0 bg-transparent px-1 py-3.5 text-[14.5px] text-white placeholder:text-slate-500"
          />
        </div>
      </div>

      {isTenantAdmin && (
        <div>
          <div className="mb-3.5 text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">
            Add runbooks
          </div>
          <RunbookUpload
            onUploaded={(document) => {
              notify("Upload accepted", `${document.title} is being indexed`);
              load();
            }}
            onError={(message) => notify("Upload failed", message, "warn")}
          />
        </div>
      )}

      <div className="rounded-none border border-hairline bg-white">
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-hairline px-6 py-4">
          <div>
            <div className="text-[15px] font-semibold text-ink">Recently updated</div>
            <div className="mt-0.5 text-[12.5px] text-slate-500">
              {loading ? "Loading..." : `${visible.length} document${visible.length === 1 ? "" : "s"}`}
            </div>
          </div>
          <button
            type="button"
            onClick={load}
            className="flex flex-none items-center gap-2 rounded-none border border-slate-300 bg-white px-3.5 py-2 text-[12.5px] font-medium text-slate-700 transition hover:bg-slate-50"
          >
            <RefreshCw size={14} />
            Refresh
          </button>
        </div>

        <div className="flex flex-col">
          {visible.map((document) => (
            <div key={document.id} className="border-b border-slate-100">
              <button
                type="button"
                onClick={() => openDetail(document)}
                className="flex w-full items-center gap-4 rounded-none px-6 py-4 text-left transition hover:bg-slate-50"
              >
                <span className="flex h-[30px] w-[30px] flex-none items-center justify-center rounded-none border border-hairline bg-slate-50">
                  <FileText size={15} strokeWidth={1.8} className="text-slate-600" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-medium text-ink">{document.title}</span>
                  {/* Real pipeline output only - no read time, no view counts. */}
                  <span className="mt-1 block text-[12.5px] text-slate-500">
                    {document.file_type}
                    {document.page_count ? ` - ${document.page_count} pages` : ""}
                    {document.image_count ? ` - ${document.image_count} figures` : ""}
                    {document.chunk_count ? ` - ${document.chunk_count} chunks` : ""}
                    {document.category_name ? ` - ${document.category_name}` : ""}
                  </span>
                </span>
                <Pill tone={STATUS_TONE[document.status] ?? "off"} dot={false}>
                  {STATUS_LABEL[document.status] ?? document.status}
                </Pill>
              </button>

              {document.status === "FAILED" && document.error && (
                <div className="flex gap-3 border-t border-slate-100 bg-amber-50 px-6 py-3">
                  <AlertTriangle
                    size={15}
                    strokeWidth={2}
                    className="mt-0.5 flex-none text-amber-700"
                  />
                  <span className="text-[12.5px] leading-relaxed text-amber-800">
                    {document.error}
                  </span>
                </div>
              )}

              {expanded === document.id && (
                <div className="border-t border-slate-100 bg-slate-50 px-6 py-4">
                  {isTenantAdmin && (
                    <div className="mb-4 flex flex-wrap gap-2">
                      <button
                        type="button"
                        onClick={() => reindex(document)}
                        className="flex items-center gap-2 rounded-none border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 transition hover:bg-slate-50"
                      >
                        <RefreshCw size={13} />
                        Re-index
                      </button>
                      <button
                        type="button"
                        onClick={() => remove(document)}
                        className="flex items-center gap-2 rounded-none border border-red-200 bg-white px-3 py-1.5 text-xs font-medium text-red-700 transition hover:bg-red-50"
                      >
                        <Trash2 size={13} />
                        Delete
                      </button>
                    </div>
                  )}

                  {/* Provenance: what the vision engine saw, and where. This is
                      how a bad description gets traced rather than guessed at. */}
                  {detail.assets.length > 0 && (
                    <div className="mb-4">
                      <div className="mb-2 text-[10.5px] font-semibold uppercase tracking-[0.14em] text-slate-500">
                        Figures read from this document
                      </div>
                      <div className="flex flex-col gap-2">
                        {detail.assets.map((asset) => (
                          <div
                            key={asset.id}
                            className="flex gap-3 rounded-none border border-hairline bg-white px-3 py-2.5"
                          >
                            <Image
                              size={14}
                              strokeWidth={1.8}
                              className="mt-0.5 flex-none text-slate-500"
                            />
                            <div className="min-w-0">
                              <div className="text-[11.5px] text-slate-400">
                                {asset.page ? `page ${asset.page} - ` : ""}
                                {asset.width}x{asset.height} - {asset.describe_status}
                              </div>
                              <p className="mt-1 text-[12.5px] leading-relaxed text-slate-700">
                                {asset.description_text || asset.describe_error || "—"}
                              </p>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  <div className="mb-2 text-[10.5px] font-semibold uppercase tracking-[0.14em] text-slate-500">
                    Indexed passages
                  </div>
                  <div className="flex flex-col gap-2">
                    {detail.chunks.map((chunk) => (
                      <div
                        key={chunk.id}
                        className="rounded-none border border-hairline bg-white px-3 py-2.5"
                      >
                        <div className="mb-1 flex items-center gap-2 text-[11px] text-slate-400">
                          <span className="font-mono">#{chunk.ordinal}</span>
                          <span>{chunk.token_count} tokens</span>
                          {chunk.from_image && (
                            <span className="rounded-none border border-cyan-200 bg-cyan-50 px-1.5 text-[10px] font-semibold uppercase tracking-wider text-cyan-700">
                              includes a figure
                            </span>
                          )}
                        </div>
                        <p className="whitespace-pre-wrap text-[12.5px] leading-relaxed text-slate-700">
                          {chunk.text.slice(0, 600)}
                          {chunk.text.length > 600 ? "..." : ""}
                        </p>
                      </div>
                    ))}
                    {detail.chunks.length === 0 && (
                      <p className="text-[12.5px] text-slate-500">
                        No passages yet - the document is still being indexed.
                      </p>
                    )}
                  </div>
                </div>
              )}
            </div>
          ))}

          {!loading && visible.length === 0 && (
            <div className="px-6 py-11 text-center">
              <div className="text-[15px] font-semibold text-ink">
                {query ? "No runbook matches that search" : "No runbooks yet"}
              </div>
              <p className="mt-2 text-[13.5px] text-slate-500">
                {isTenantAdmin
                  ? "Upload a PDF, Word or Markdown runbook above to get started."
                  : "Your IT team has not published any runbooks yet."}
              </p>
            </div>
          )}
        </div>
      </div>
    </main>
  );
}
