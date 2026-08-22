import { Bot, ShieldCheck } from "lucide-react";

/**
 * The MateAssist wordmark (D-104, revised D-177).
 *
 * Geometry deliberately shared with MateDesk and MateConnect: the same clipped
 * tile, the same emerald-to-lime gradient, the same two-tone lockup where the
 * product half of the name carries the accent. Three products from one company
 * should read as siblings on sight, and the mark is the only thing a visitor
 * sees on every one of them.
 *
 * The clipped corner is a path, not a border radius - D-100 still holds.
 *
 * `variant` keeps the glyph choice from diverging again: the portal and the
 * admin console had drifted to different marks before this was one component.
 */
export function Wordmark({
  size = "text-xl",
  mark = "h-8 w-8",
  icon = 18,
  variant = "portal",
  dark = true
}) {
  const Glyph = variant === "admin" ? ShieldCheck : Bot;

  return (
    <div className="flex items-center gap-2.5 rounded-none">
      <div className={`${mark} relative flex flex-none items-center justify-center`}>
        {/* The tile is an SVG rather than a div so the corner can be cut. A
            square with one clipped corner is the shape all three products
            share; a plain rectangle would lose the family resemblance. */}
        <svg viewBox="0 0 32 32" className="absolute inset-0 h-full w-full" aria-hidden="true">
          <defs>
            <linearGradient id="ma-tile" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0" stopColor="#10b981" />
              <stop offset="1" stopColor="#4ade80" />
            </linearGradient>
          </defs>
          <path d="M7 1 H31 V25 L25 31 H1 V7 Z" fill="url(#ma-tile)" />
        </svg>
        <Glyph
          size={icon}
          strokeWidth={2.2}
          className="relative text-[#06231a]"
        />
      </div>

      <span className={`font-wordmark ${size} uppercase leading-none tracking-[0.04em]`}>
        <span className={dark ? "text-[#eceef2]" : "text-[#0b1220]"}>Mate</span>
        <span className="text-emerald-500">Assist</span>
      </span>
    </div>
  );
}
