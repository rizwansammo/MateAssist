import { useEffect, useRef, useState } from "react";
import { ChevronDown, LogOut, UserCog } from "lucide-react";

/**
 * The account menu behind the avatar (D-158).
 *
 * This replaces a button whose entire click target ran sign-out. It carried a
 * chevron, so it looked like a menu and behaved like a logout: clicking your own
 * name threw you back to the login form. Nobody misread it - the affordance was
 * simply lying about what the control did.
 *
 * The chevron now opens a menu, and signing out is one item in it, below the
 * address so a reader can see which account they are about to leave.
 */
const TONE = {
  light: {
    trigger: "hover:border-hairline hover:bg-slate-50",
    name: "text-ink",
    subtitle: "text-slate-500",
    chevron: "text-slate-400",
    panel: "border-hairline bg-white",
    divider: "border-hairline",
    itemName: "text-ink",
    itemEmail: "text-slate-500",
    item: "text-ink hover:bg-slate-50",
    itemIcon: "text-slate-500",
    signOut: "text-red-700 hover:bg-red-50"
  },
  // The sidebar is ink; the light panel's white-on-white read as a hole in it.
  dark: {
    trigger: "hover:border-slate-800 hover:bg-ink2",
    name: "text-slate-100",
    subtitle: "text-slate-500",
    chevron: "text-slate-500",
    panel: "border-slate-800 bg-ink2",
    divider: "border-slate-800",
    itemName: "text-white",
    itemEmail: "text-slate-400",
    item: "text-slate-200 hover:bg-ink",
    itemIcon: "text-slate-400",
    signOut: "text-red-400 hover:bg-ink"
  }
};

export function ProfileMenu({ user, subtitle, tone = "light", onOpenAccount, onSignOut }) {
  const skin = TONE[tone] ?? TONE.light;
  const [open, setOpen] = useState(false);
  const wrapper = useRef(null);

  useEffect(() => {
    if (!open) return undefined;

    // Close on an outside click or Escape. Without both, the menu strands
    // itself open over the page and the only way out is to click the trigger
    // again - which people do not think to try.
    const onPointerDown = (event) => {
      if (!wrapper.current?.contains(event.target)) setOpen(false);
    };
    const onKeyDown = (event) => {
      if (event.key === "Escape") setOpen(false);
    };

    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <div className="relative" ref={wrapper}>
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        aria-haspopup="menu"
        aria-expanded={open}
        className={`flex w-full items-center gap-2.5 rounded-none border border-transparent p-1 pr-1.5 transition ${skin.trigger}`}
      >
        <div className="flex h-[30px] w-[30px] items-center justify-center rounded-none bg-teal-700 text-xs font-semibold text-white">
          {user?.initials ?? "?"}
        </div>
        <div className="min-w-0 flex-1 text-left">
          <div className={`truncate text-[13px] font-medium leading-tight ${skin.name}`}>
            {user?.display_name ?? user?.email}
          </div>
          <div className={`truncate text-[11px] leading-tight ${skin.subtitle}`}>
            {subtitle || user?.email || ""}
          </div>
        </div>
        <ChevronDown
          size={14}
          className={`flex-none transition-transform ${skin.chevron} ${open ? "rotate-180" : ""}`}
        />
      </button>

      {open && (
        <div
          role="menu"
          className={`absolute bottom-full right-0 z-50 mb-1.5 w-[248px] rounded-none border shadow-lg ${skin.panel}`}
        >
          {/* The email, not just the name. It is the login identity, and until
              now there was nowhere in the product a user could read their own. */}
          <div className={`border-b px-4 py-3 ${skin.divider}`}>
            <div className={`truncate text-[13px] font-medium ${skin.itemName}`}>
              {user?.display_name ?? "Signed in"}
            </div>
            <div className={`mt-0.5 truncate text-[12px] ${skin.itemEmail}`}>{user?.email}</div>
          </div>

          <button
            type="button"
            role="menuitem"
            onClick={() => {
              setOpen(false);
              onOpenAccount();
            }}
            className={`flex w-full items-center gap-2.5 px-4 py-2.5 text-left text-[13px] transition ${skin.item}`}
          >
            <UserCog size={15} strokeWidth={1.8} className={skin.itemIcon} />
            Account settings
          </button>

          <div className={`border-t ${skin.divider}`}>
            <button
              type="button"
              role="menuitem"
              onClick={() => {
                setOpen(false);
                onSignOut();
              }}
              className={`flex w-full items-center gap-2.5 px-4 py-2.5 text-left text-[13px] transition ${skin.signOut}`}
            >
              <LogOut size={15} strokeWidth={1.8} />
              Sign out
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
