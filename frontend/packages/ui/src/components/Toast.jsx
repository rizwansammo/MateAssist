import { useEffect } from "react";
import { AlertTriangle, Check, X } from "lucide-react";

export const TOAST_TIMEOUT_MS = 5200;

/**
 * Transient notification.
 *
 * Unified from the two prototypes: the portal's was success-only, the admin's
 * had ok/warn tones. Auto-dismiss lives here so no caller can forget the
 * cleanup and leak a timer.
 */
export function Toast({ toast, onDismiss }) {
  useEffect(() => {
    if (!toast) return undefined;
    const timer = setTimeout(onDismiss, TOAST_TIMEOUT_MS);
    return () => clearTimeout(timer);
  }, [toast, onDismiss]);

  if (!toast) return null;

  const warn = toast.tone === "warn";

  return (
    <div
      role="status"
      aria-live="polite"
      className={`fixed right-6 top-[84px] z-[60] flex min-w-[330px] max-w-[400px] animate-toastIn items-start gap-3 rounded-none border bg-ink px-4 py-3.5 shadow-2xl ${
        warn ? "border-amber-700" : "border-emerald-800"
      }`}
    >
      <span
        className={`flex h-6 w-6 flex-none items-center justify-center rounded-none ${
          warn ? "bg-amber-500" : "bg-emerald-500"
        }`}
      >
        {warn ? (
          <AlertTriangle size={14} strokeWidth={2.6} className="text-amber-950" />
        ) : (
          <Check size={14} strokeWidth={3} className="text-emerald-950" />
        )}
      </span>
      <div className="min-w-0 flex-1">
        <div className="text-[13.5px] font-semibold text-white">{toast.title}</div>
        {toast.body ? (
          <div className="mt-1 text-[12.5px] leading-relaxed text-slate-400">{toast.body}</div>
        ) : null}
      </div>
      <button
        type="button"
        onClick={onDismiss}
        aria-label="Dismiss notification"
        className="flex-none rounded-none p-0.5 text-slate-500 transition hover:text-white"
      >
        <X size={15} />
      </button>
    </div>
  );
}
