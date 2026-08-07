// TEMPORARY - tenants deleted by Phase 2, billing and logs by Phase 7.
// See seed/README.md.

export const SEED_TENANTS = [
  { name: "Netswitch", slug: "netswitch", subdomain: "netswitch.mateassist.io", plan: "Enterprise", users: 412, documents: 45, kbSize: "12 MB", status: "Active", region: "eu-central-1", since: "Mar 2025" },
  { name: "Apptriangle", slug: "apptriangle", subdomain: "apptriangle.mateassist.io", plan: "Pro", users: 168, documents: 62, kbSize: "24 MB", status: "Active", region: "ap-south-1", since: "Jun 2025" },
  { name: "FinanceCorp", slug: "financecorp", subdomain: "financecorp.mateassist.io", plan: "Enterprise", users: 507, documents: 128, kbSize: "61 MB", status: "Active", region: "us-east-1", since: "Nov 2024" },
  { name: "Meridian Legal", slug: "meridian", subdomain: "meridian.mateassist.io", plan: "Pro", users: 94, documents: 37, kbSize: "9 MB", status: "Active", region: "eu-west-2", since: "Jan 2026" },
  { name: "Harbor Logistics", slug: "harbor", subdomain: "harbor.mateassist.io", plan: "Growth", users: 61, documents: 18, kbSize: "4 MB", status: "Suspended", region: "us-east-1", since: "Aug 2025" },
  { name: "Vantage Health", slug: "vantage", subdomain: "vantage.mateassist.io", plan: "Enterprise", users: 342, documents: 204, kbSize: "148 MB", status: "Active", region: "eu-central-1", since: "Feb 2025" }
];

export const PLAN_STYLE = {
  Enterprise: "border-ink bg-ink text-white",
  Pro: "border-cyan-200 bg-cyan-50 text-cyan-700",
  Growth: "border-slate-300 bg-slate-50 text-slate-600"
};

/**
 * Status Centre rows, rebuilt against dependencies that actually exist.
 * The prototype's Groq, OpenAI fallback and ITSM connector rows are gone
 * (D-085/D-087). Phase 7 drives this from the real /api/v1/health aggregate.
 */
export const SEED_HEALTH = [
  { name: "DeepSeek text engine", detail: "deepseek-chat - reasoning and RAG", metric: "p95 1.1s", state: "Operational", tone: "ok" },
  { name: "Gemini vision engine", detail: "gemini-2.5-flash - 1 key cooling down", metric: "p95 1.4s", state: "Degraded", tone: "warn" },
  { name: "PostgreSQL + pgvector", detail: "HNSW index across tenant namespaces", metric: "p95 62ms", state: "Operational", tone: "ok" },
  { name: "Redis / Celery queue", detail: "ingestion and rollup workers", metric: "0 backlog", state: "Operational", tone: "ok" },
  { name: "Object storage", detail: "runbook bucket, versioned", metric: "p95 40ms", state: "Operational", tone: "ok" }
];

export const SEED_USAGE = [
  { name: "FinanceCorp", slug: "financecorp", plan: "Enterprise", tokens: "48.6M", cost: "$41.20", margin: "94.1%", pct: "100%", tone: "ok" },
  { name: "Apptriangle", slug: "apptriangle", plan: "Pro", tokens: "36.1M", cost: "$32.85", margin: "61.4%", pct: "74%", tone: "warn" },
  { name: "Vantage Health", slug: "vantage", plan: "Enterprise", tokens: "31.4M", cost: "$24.10", margin: "95.2%", pct: "62%", tone: "ok" },
  { name: "Netswitch", slug: "netswitch", plan: "Enterprise", tokens: "28.9M", cost: "$18.40", margin: "96.3%", pct: "56%", tone: "ok" },
  { name: "Meridian Legal", slug: "meridian", plan: "Pro", tokens: "22.7M", cost: "$19.95", margin: "58.9%", pct: "44%", tone: "warn" },
  { name: "Harbor Logistics", slug: "harbor", plan: "Growth", tokens: "6.2M", cost: "$6.00", margin: "72.0%", pct: "13%", tone: "ok" }
];

/** Two providers only. Cost per provider comes from ModelPrice rows (D-111). */
export const SEED_PROVIDER_SPEND = [
  { name: "DeepSeek (text)", cost: "$96.40", pct: "68%", bar: "bg-emerald-600", tokens: "173.2M", share: "94%" },
  { name: "Gemini (vision)", cost: "$46.10", pct: "32%", bar: "bg-cyan-600", tokens: "11.0M", share: "6%" }
];

export const SEED_LOGS = [
  { time: "09:41:02", level: "warn", tenant: "platform", message: "vault.pool key=gemini-pool-03 status=429 cooldown=00:14:00 rerouted=gemini-pool-02" },
  { time: "09:40:55", level: "info", tenant: "netswitch", message: "agent.resolve intent=cache_clear engine=deepseek model=deepseek-chat tokens=1,842 latency=1.21s resolved=true" },
  { time: "09:40:12", level: "info", tenant: "netswitch", message: "ticket.transition id=IT-10942 from=Open to=Pending actor=d.koch" },
  { time: "09:39:47", level: "info", tenant: "financecorp", message: "agent.escalate ticket=FC-88214 reason=identity_verification queue=tier2" },
  { time: "09:38:30", level: "auth", tenant: "platform", message: "vault.rotate actor=a.siddiqui engine=text key=deepseek-primary result=ok" },
  { time: "09:37:58", level: "info", tenant: "apptriangle", message: "rag.index documents=12 images=41 chunks=486 duration=8.4s" },
  { time: "09:37:12", level: "info", tenant: "apptriangle", message: "vision.describe engine=gemini images=41 tokens=12,880 cost_usd=0.014" },
  { time: "09:36:41", level: "warn", tenant: "apptriangle", message: "budget.tenant usage=81% allowance=45M tokens action=notify_owner" },
  { time: "09:35:03", level: "auth", tenant: "harbor", message: "tenant.suspend actor=a.siddiqui reason=payment_failed sessions_revoked=61" },
  { time: "09:31:44", level: "error", tenant: "meridian", message: "rag.retrieve error=embedding_timeout retry=1 fallback=keyword_search" }
];

export const LOG_LEVEL_STYLE = {
  info: "border-slate-800 text-slate-400",
  warn: "border-amber-900 text-amber-400",
  error: "border-red-900 text-red-400",
  auth: "border-teal-900 text-teal-300"
};
