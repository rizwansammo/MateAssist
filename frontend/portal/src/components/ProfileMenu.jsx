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
export function ProfileMenu({ user, subtitle, onOpenAccount, onSignOut }) {
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
        className="flex items-center gap-2.5 rounded-none border border-transparent p-1 pr-1.5 transition hover:border-hairline hover:bg-slate-50"
      >
        <div className="flex h-[30px] w-[30px] items-center justify-center rounded-none bg-teal-700 text-xs font-semibold text-white">
          {user?.initials ?? "?"}
        </div>
        <div className="hidden text-left sm:block">
          <div className="text-[13px] font-medium leading-tight text-ink">
            {user?.display_name ?? user?.email}
          </div>
          <div className="text-[11px] leading-tight text-slate-500">{subtitle || ""}</div>
        </div>
        <ChevronDown
          size={14}
          className={`text-slate-400 transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>

      {open && (
        <div
          role="menu"
          className="absolute right-0 z-50 mt-1.5 w-[248px] rounded-none border border-hairline bg-white shadow-lg"
        >
          {/* The email, not just the name. It is the login identity, and until
              now there was nowhere in the product a user could read their own. */}
          <div className="border-b border-hairline px-4 py-3">
            <div className="truncate text-[13px] font-medium text-ink">
              {user?.display_name ?? "Signed in"}
            </div>
            <div className="mt-0.5 truncate text-[12px] text-slate-500">{user?.email}</div>
          </div>

          <button
            type="button"
            role="menuitem"
            onClick={() => {
              setOpen(false);
              onOpenAccount();
            }}
            className="flex w-full items-center gap-2.5 px-4 py-2.5 text-left text-[13px] text-ink transition hover:bg-slate-50"
          >
            <UserCog size={15} strokeWidth={1.8} className="text-slate-500" />
            Account settings
          </button>

          <div className="border-t border-hairline">
            <button
              type="button"
              role="menuitem"
              onClick={() => {
                setOpen(false);
                onSignOut();
              }}
              className="flex w-full items-center gap-2.5 px-4 py-2.5 text-left text-[13px] text-red-700 transition hover:bg-red-50"
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
