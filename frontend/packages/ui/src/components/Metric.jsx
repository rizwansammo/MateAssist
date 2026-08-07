/**
 * Headline metric tile.
 *
 * `valueClass` exists because the two prototypes used different value sizes
 * (portal text-3xl, admin text-[32px]). Preserved rather than normalised - the
 * design system is reproduced exactly, not tidied (D-101).
 */
export function Metric({
  label,
  value,
  note,
  noteClass = "text-slate-400",
  valueClass = "text-3xl",
  mono = false
}) {
  return (
    <div className="rounded-none bg-white px-6 py-5">
      <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500">
        {label}
      </div>
      <div
        className={`mt-2.5 ${valueClass} font-semibold tracking-tight text-ink ${
          mono ? "font-mono" : ""
        }`}
      >
        {value}
      </div>
      {note ? <div className={`mt-1 text-xs ${noteClass}`}>{note}</div> : null}
    </div>
  );
}
