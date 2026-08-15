import { useEffect, useRef, useState } from "react";
import { ChevronDown, LogOut } from "lucide-react";

/**
 * The account menu behind the avatar, dark-surface twin of the portal's
 * (D-158).
 *
 * It replaces a button whose whole click target ran sign-out while carrying no
 * hint that it would: clicking your own name threw you back to the login form.
 *
 * No "Account settings" item here yet. The platform owner's own profile is
 * edited in the portal; duplicating the page into this console would mean two
 * places to keep in step for one person's name.
 */
export function ProfileMenu({ user, role, onSignOut }) {
  const [open, setOpen] = useState(false);
  const wrapper = useRef(null);

  useEffect(() => {
    if (!open) return undefined;

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
        className="flex items-center gap-2.5 rounded-none border border-transparent p-1 pr-1.5 transition hover:border-slate-800 hover:bg-[#0F1B2D]"
      >
        <div className="flex h-[30px] w-[30px] items-center justify-center rounded-none bg-emerald-500 text-xs font-bold text-emerald-950">
          {user?.initials ?? "?"}
        </div>
        <div className="hidden text-left sm:block">
          <div className="text-[13px] font-medium leading-tight text-white">
            {user?.display_name ?? user?.email}
          </div>
          <div className="font-mono text-[11px] leading-tight text-slate-500">
            {(role ?? "").toLowerCase().replace("_", "-")}
          </div>
        </div>
        <ChevronDown
          size={14}
          className={`text-slate-500 transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>

      {open && (
        <div
          role="menu"
          className="absolute right-0 z-50 mt-1.5 w-[248px] rounded-none border border-slate-800 bg-[#0F1B2D] shadow-lg"
        >
          <div className="border-b border-slate-800 px-4 py-3">
            <div className="truncate text-[13px] font-medium text-white">
              {user?.display_name ?? "Signed in"}
            </div>
            <div className="mt-0.5 truncate text-[12px] text-slate-400">{user?.email}</div>
          </div>

          <button
            type="button"
            role="menuitem"
            onClick={() => {
              setOpen(false);
              onSignOut();
            }}
            className="flex w-full items-center gap-2.5 px-4 py-2.5 text-left text-[13px] text-red-400 transition hover:bg-[#16233A]"
          >
            <LogOut size={15} strokeWidth={1.8} />
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}
