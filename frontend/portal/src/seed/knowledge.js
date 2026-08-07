// TEMPORARY - deleted by Phase 5 (ingestion pipeline). See seed/README.md.
//
// Shape mirrors what the Phase 5 API will return. Note what is ABSENT and must
// stay absent: read time, view counts (D-082) and the Popular/Updated/Policy
// tag badges (D-083). Article rows now carry real document metadata - file
// type, size, page and chunk counts, indexing status (D-083) - because those
// are facts the ingestion pipeline actually produces.

export const SEED_CATEGORIES = [
  { name: "Network Issues", abbr: "NET", count: 12, updated: "2 days ago", tint: "bg-cyan-50 text-cyan-700" },
  { name: "Hardware", abbr: "HW", count: 9, updated: "1 week ago", tint: "bg-amber-50 text-amber-700" },
  { name: "Software", abbr: "SW", count: 17, updated: "yesterday", tint: "bg-emerald-50 text-emerald-700" },
  { name: "Access & Security", abbr: "SEC", count: 7, updated: "4 days ago", tint: "bg-slate-100 text-slate-700" }
];

export const SEED_DOCUMENTS = [
  { title: "How to set up the Netswitch VPN (GlobalProtect)", category: "Network Issues", fileType: "PDF", pages: 6, chunks: 24, status: "INDEXED", updated: "2 days ago" },
  { title: "Wi-Fi keeps dropping on the 5 GHz band", category: "Network Issues", fileType: "DOCX", pages: 3, chunks: 11, status: "INDEXED", updated: "2 days ago" },
  { title: "Printer troubleshooting: HP LaserJet M479", category: "Hardware", fileType: "PDF", pages: 9, chunks: 38, status: "INDEXED", updated: "1 week ago" },
  { title: "Request a laptop replacement or upgrade", category: "Hardware", fileType: "MD", pages: 1, chunks: 4, status: "INDEXED", updated: "1 week ago" },
  { title: "Reset your Microsoft 365 password", category: "Software", fileType: "PDF", pages: 4, chunks: 16, status: "INDEXED", updated: "yesterday" },
  { title: "Clear browser and DNS cache", category: "Software", fileType: "MD", pages: 2, chunks: 7, status: "INDEXED", updated: "yesterday" },
  { title: "Install approved software from Company Portal", category: "Software", fileType: "DOCX", pages: 5, chunks: 19, status: "INDEXING", updated: "just now" },
  { title: "Enrol a new device in MFA", category: "Access & Security", fileType: "PDF", pages: 4, chunks: 15, status: "INDEXED", updated: "4 days ago" },
  { title: "Request access to a shared drive", category: "Access & Security", fileType: "MD", pages: 1, chunks: 3, status: "INDEXED", updated: "4 days ago" }
];

/** Document.status is a real ingestion state, not a marketing label (D-083). */
export const DOCUMENT_STATUS_TONE = {
  INDEXED: "ok",
  INDEXING: "info",
  FAILED: "warn"
};
