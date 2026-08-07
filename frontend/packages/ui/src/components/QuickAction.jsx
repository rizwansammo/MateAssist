import { ArrowRight } from "lucide-react";

/** Dashboard shortcut card with a coloured top rule. */
export function QuickAction({ icon, title, body, accent, tint, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex flex-col gap-3 rounded-none border border-hairline ${accent} bg-white p-6 text-left transition hover:shadow-[0_0_0_1px_currentColor]`}
    >
      <div className="flex items-center justify-between">
        <div
          className={`flex h-10 w-10 items-center justify-center rounded-none border ${tint}`}
        >
          {icon}
        </div>
        <ArrowRight size={18} className="text-slate-400" />
      </div>
      <div>
        <div className="text-base font-semibold text-ink">{title}</div>
        <p className="mt-1.5 text-[13px] leading-relaxed text-slate-500">{body}</p>
      </div>
    </button>
  );
}
