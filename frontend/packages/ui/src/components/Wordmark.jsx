import { Bot, ShieldCheck } from "lucide-react";

/**
 * The MateAssist wordmark.
 *
 * Extracted from both prototypes, which had drifted: the portal used a Bot glyph
 * on emerald, the admin panel a ShieldCheck. Kept as one component with a
 * `variant` so the lockup geometry can never diverge again (D-104).
 */
export function Wordmark({
  size = "text-xl",
  mark = "h-8 w-8",
  icon = 18,
  variant = "portal"
}) {
  const Glyph = variant === "admin" ? ShieldCheck : Bot;

  return (
    <div className="flex items-center gap-3 rounded-none">
      <div
        className={`${mark} flex flex-none items-center justify-center rounded-none bg-emerald-500`}
      >
        <Glyph size={icon} strokeWidth={2} className="text-emerald-950" />
      </div>
      <span className={`font-wordmark ${size} uppercase tracking-wide text-white`}>
        MateAssist
      </span>
    </div>
  );
}
