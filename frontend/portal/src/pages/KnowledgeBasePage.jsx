import { useMemo, useState } from "react";
import { ChevronRight, FileText, Search } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { Pill } from "@mateassist/ui";

import { DOCUMENT_STATUS_TONE, SEED_CATEGORIES, SEED_DOCUMENTS } from "../seed/knowledge.js";

/**
 * Knowledge Base.
 *
 * Scope subtractions applied here, and they are not to be reintroduced:
 *   D-082  no "4 min read", no "612 views this month" - nothing tracked those
 *   D-083  no Popular/Updated/Policy/Runbook badges; the badge is now
 *          Document.status (INDEXED / INDEXING / FAILED), a real ingestion state
 *   D-084  header is "Recently updated", ordered by real updated_at, not
 *          "Most read this month"
 *
 * Each row instead shows metadata the Phase 5 pipeline genuinely produces:
 * file type, page count and chunk count.
 */
export default function KnowledgeBasePage() {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("");

  const documents = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return SEED_DOCUMENTS.filter((doc) => {
      if (category && doc.category !== category) return false;
      if (!needle) return true;
      return `${doc.title} ${doc.category}`.toLowerCase().includes(needle);
    });
  }, [query, category]);

  const heading = category || (query.trim() ? "Search results" : "Recently updated");

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
            placeholder="Search runbooks - e.g. VPN, printer, password"
            aria-label="Search runbooks"
            className="min-w-0 flex-1 rounded-none border-0 bg-transparent px-1 py-3.5 text-[14.5px] text-white placeholder:text-slate-500"
          />
        </div>
        {/* Phase 6 upgrades this to hybrid retrieval (pgvector + FTS, fused by RRF). */}
      </div>

      <div>
        <div className="mb-3.5 text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">
          Categories
        </div>
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {SEED_CATEGORIES.map((cat) => (
            <button
              key={cat.name}
              type="button"
              onClick={() => setCategory(category === cat.name ? "" : cat.name)}
              aria-pressed={category === cat.name}
              className={`flex flex-col gap-3.5 rounded-none border bg-white p-5 text-left transition hover:shadow-[0_0_0_1px_#0B1220] ${
                category === cat.name ? "border-ink" : "border-hairline"
              }`}
            >
              <div
                className={`flex h-9 w-9 items-center justify-center rounded-none font-mono text-[13px] font-semibold ${cat.tint}`}
              >
                {cat.abbr}
              </div>
              <div>
                <div className="text-[15px] font-semibold text-ink">{cat.name}</div>
                <div className="mt-1 text-[12.5px] text-slate-500">
                  {cat.count} documents - updated {cat.updated}
                </div>
              </div>
            </button>
          ))}
        </div>
      </div>

      <div className="rounded-none border border-hairline bg-white">
        <div className="flex items-center justify-between gap-4 border-b border-hairline px-6 py-4">
          <div>
            <div className="text-[15px] font-semibold text-ink">{heading}</div>
            <div className="mt-0.5 text-[12.5px] text-slate-500">
              {documents.length} documents
            </div>
          </div>
          {(category || query.trim()) && (
            <button
              type="button"
              onClick={() => {
                setCategory("");
                setQuery("");
              }}
              className="flex-none whitespace-nowrap rounded-none border border-slate-300 bg-white px-3.5 py-2 text-[12.5px] font-medium text-slate-700 transition hover:bg-slate-50"
            >
              Clear filters
            </button>
          )}
        </div>

        <div className="flex flex-col">
          {documents.map((doc) => (
            <button
              key={doc.title}
              type="button"
              className="flex items-center gap-4 rounded-none border-b border-slate-100 px-6 py-4 text-left transition hover:bg-slate-50"
            >
              <span className="flex h-[30px] w-[30px] flex-none items-center justify-center rounded-none border border-hairline bg-slate-50">
                <FileText size={15} strokeWidth={1.8} className="text-slate-600" />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block text-sm font-medium text-ink">{doc.title}</span>
                <span className="mt-1 block text-[12.5px] text-slate-500">
                  {doc.category} - {doc.fileType} - {doc.pages} pages - {doc.chunks} chunks
                </span>
              </span>
              <span className="hidden flex-none sm:block">
                <Pill tone={DOCUMENT_STATUS_TONE[doc.status] ?? "off"} dot={false}>
                  {doc.status}
                </Pill>
              </span>
              <ChevronRight size={16} className="flex-none text-slate-400" />
            </button>
          ))}

          {documents.length === 0 && (
            <div className="px-6 py-11 text-center">
              <div className="text-[15px] font-semibold text-ink">
                No runbook matches that search
              </div>
              <p className="mb-4 mt-2 text-[13.5px] text-slate-500">
                Ask MateAssist instead - it can reason across your runbooks and past tickets.
              </p>
              <button
                type="button"
                onClick={() => navigate("/app/chat")}
                className="rounded-none bg-emerald-600 px-[18px] py-2.5 text-[13px] font-semibold text-white transition hover:bg-emerald-700"
              >
                Ask the AI assistant
              </button>
            </div>
          )}
        </div>
      </div>
    </main>
  );
}
