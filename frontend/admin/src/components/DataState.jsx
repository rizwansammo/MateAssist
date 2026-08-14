/**
 * Loading, error and empty states for a data panel.
 *
 * Separate from the panels themselves so every screen fails the same way. An
 * error here is shown rather than swallowed: a billing table that silently
 * renders nothing when the request fails is indistinguishable from a month with
 * no spend, and the operator would act on the wrong one.
 *
 * D-100: rounded-none everywhere, no exceptions.
 */
export function Loading({ label = "Loading", rows = 3, dark = false }) {
  return (
    <div className="px-6 py-6" role="status" aria-live="polite">
      <span className="sr-only">{label}</span>
      <div className="flex flex-col gap-2.5">
        {Array.from({ length: rows }).map((_, index) => (
          <div
            key={index}
            className={`h-3 animate-pulse rounded-none ${dark ? "bg-slate-800" : "bg-slate-100"}`}
            style={{ width: `${92 - index * 14}%` }}
          />
        ))}
      </div>
    </div>
  );
}

export function ErrorState({ error, onRetry, dark = false }) {
  // A 403 is a different conversation from a broken request: the operator is
  // signed in on the wrong surface, and "retry" will not help them.
  const forbidden = error?.status === 403;
  const detail = forbidden
    ? "This screen is platform-owner only. Sign in on the admin host."
    : error?.status === 0
      ? "The API is unreachable. Is the backend running?"
      : (error?.message ?? "Something went wrong.");

  return (
    <div className={`px-6 py-10 text-center ${dark ? "text-slate-300" : ""}`}>
      <div className={`text-sm font-semibold ${dark ? "text-white" : "text-ink"}`}>
        {forbidden ? "Not authorised" : "Could not load this panel"}
      </div>
      <div className={`mt-1.5 text-[12.5px] ${dark ? "text-slate-400" : "text-slate-500"}`}>
        {detail}
      </div>
      {!forbidden && onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className={`mt-4 rounded-none border px-4 py-2 text-[12.5px] font-semibold transition ${
            dark
              ? "border-emerald-500 bg-transparent text-emerald-400 hover:bg-slate-900"
              : "border-slate-300 bg-white text-ink hover:bg-slate-50"
          }`}
        >
          Try again
        </button>
      )}
    </div>
  );
}

export function Empty({ title, detail, action, dark = false }) {
  return (
    <div className="px-6 py-10 text-center">
      <div className={`text-sm font-semibold ${dark ? "text-white" : "text-ink"}`}>{title}</div>
      {detail && (
        <div className={`mt-1.5 text-[12.5px] ${dark ? "text-slate-400" : "text-slate-500"}`}>
          {detail}
        </div>
      )}
      {action}
    </div>
  );
}

/**
 * Panel body switch. Keeps every screen's three-state handling identical
 * instead of re-deriving it per page.
 */
export function DataState({ loading, error, isEmpty, onRetry, empty, dark, children, rows }) {
  if (loading) return <Loading rows={rows} dark={dark} />;
  if (error) return <ErrorState error={error} onRetry={onRetry} dark={dark} />;
  if (isEmpty) return empty ?? <Empty title="Nothing to show yet" dark={dark} />;
  return children;
}
