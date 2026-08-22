import { Wordmark } from "./Wordmark.jsx";

/**
 * Split-screen sign-in shell (D-177).
 *
 * Dark brand panel on the left, light form on the right - the same layout
 * MateDesk and MateConnect use, so the three products read as siblings the
 * moment someone lands on any of their sign-in pages.
 *
 * Shared between the portal and the platform console rather than copied. The
 * two had already drifted once (different wordmark glyphs), and a sign-in page
 * is the single screen every user of every product sees.
 *
 * No sign-up affordance anywhere, deliberately: MateAssist accounts are created
 * by an administrator, and a "create account" link that leads nowhere is worse
 * than no link at all.
 */
export function AuthShell({
  variant = "portal",
  headline,
  headlineAccent,
  intro,
  features = [],
  asideNote = "By NetaMate Solutions",
  children
}) {
  return (
    <div className="flex min-h-screen flex-col lg:flex-row">
      {/* LEFT - dark brand panel. Hidden below lg: on a phone the form is the
          only thing worth the space. */}
      <aside className="hidden min-w-0 flex-1 flex-col justify-between bg-[#0e1117] p-12 lg:flex xl:p-14">
        <Wordmark size="text-[22px]" mark="h-[26px] w-[26px]" icon={15} variant={variant} dark />

        <div>
          <h2 className="mb-4 font-wordmark text-[clamp(28px,3vw,44px)] uppercase leading-[1.08] tracking-[0.01em] text-[#eceef2]">
            {headline}
            <br />
            <span className="text-emerald-500">{headlineAccent}</span>
          </h2>

          <p className="mb-8 max-w-[380px] text-[15px] leading-relaxed text-[#9aa2b1]">{intro}</p>

          <ul className="flex flex-col gap-3.5">
            {features.map(({ Icon, text }) => (
              <li key={text} className="flex items-center gap-3 text-[14px] text-[#9aa2b1]">
                <Icon size={15} strokeWidth={1.9} className="flex-none text-emerald-500" />
                {text}
              </li>
            ))}
          </ul>
        </div>

        <p className="m-0 text-[12px] text-[#485168]">{asideNote}</p>
      </aside>

      {/* RIGHT - light form panel. Fixed-ish width so the form does not stretch
          across a wide monitor, which is what made the old layout feel unowned. */}
      <main className="flex w-full flex-none flex-col overflow-y-auto bg-white p-8 sm:p-12 lg:w-[clamp(380px,42vw,560px)]">
        {/* The mark repeats here for small screens, where the dark panel is
            hidden and the page would otherwise carry no branding at all. */}
        <div className="mb-10 lg:hidden">
          <Wordmark
            size="text-[20px]"
            mark="h-[24px] w-[24px]"
            icon={14}
            variant={variant}
            dark={false}
          />
        </div>

        <div className="mx-auto flex w-full max-w-[400px] flex-1 flex-col justify-center">
          {children}
        </div>
      </main>
    </div>
  );
}
