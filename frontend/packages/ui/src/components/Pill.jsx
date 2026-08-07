/**
 * Tone-coded status pill.
 *
 * The prototypes had two near-identical implementations - StatusBadge (portal,
 * keyed by ticket status) and Pill (admin, keyed by tone). This is the single
 * primitive; TONE is the vocabulary, and callers map their domain to it.
 */

export const TONE = {
  ok: "border-emerald-200 bg-emerald-50 text-emerald-700",
  warn: "border-amber-200 bg-amber-50 text-amber-700",
  info: "border-cyan-200 bg-cyan-50 text-cyan-700",
  off: "border-hairline bg-slate-50 text-slate-500"
};

export const TONE_DOT = {
  ok: "bg-emerald-600",
  warn: "bg-amber-600",
  info: "bg-cyan-600",
  off: "bg-slate-400"
};

export function Pill({ tone = "ok", children, dot = true, className = "" }) {
  return (
    <span
      className={`inline-flex items-center gap-2 whitespace-nowrap rounded-none border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wider ${TONE[tone]} ${className}`}
    >
      {dot && <span className={`h-1.5 w-1.5 rounded-none ${TONE_DOT[tone]}`} />}
      {children}
    </span>
  );
}
