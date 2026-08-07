import { useEffect, useState } from "react";
import { AlertTriangle, Check, Eye, Lock, X } from "lucide-react";

/**
 * Add / rotate a provider credential.
 *
 * D-075: the secret input is type="password" with an explicit show/hide,
 * autoComplete off and spellCheck off.
 *
 * D-072: the plaintext never leaves this component. On save only the last four
 * characters are handed upward for display; Phase 4 posts the secret straight
 * to the vault endpoint, which has no read path at all.
 */
export function KeyModal({ engine, existingKey, onClose, onSave }) {
  const isRotate = Boolean(existingKey);

  const [label, setLabel] = useState(existingKey?.label ?? "");
  const [secret, setSecret] = useState("");
  const [quota, setQuota] = useState(existingKey?.quota ?? "unlimited");
  const [showSecret, setShowSecret] = useState(false);
  const [error, setError] = useState("");

  // Escape closes. A modal that traps you is a bug, not a safeguard.
  useEffect(() => {
    const onKeyDown = (event) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  const submit = (event) => {
    event.preventDefault();
    const trimmed = secret.trim();
    if (!trimmed) {
      setError("Paste the provider credential before saving - nothing was changed.");
      return;
    }
    if (!label.trim()) {
      setError("A label is required so this key can be identified in the audit log.");
      return;
    }
    onSave({
      engineId: engine.id,
      keyId: existingKey?.id,
      label: label.trim(),
      secret: trimmed,
      quota: quota.trim() || "unlimited"
    });
    setSecret("");
    onClose();
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={isRotate ? `Rotate key ${existingKey.label}` : `Add ${engine.provider} key`}
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-[#07101C]/75 p-6"
    >
      <form
        onSubmit={submit}
        className="m-auto flex max-h-[calc(100vh-48px)] w-full max-w-[520px] flex-col rounded-none border border-ink bg-white"
      >
        <div className="flex flex-none items-start gap-4 bg-ink px-6 py-5">
          <div className="flex h-[34px] w-[34px] flex-none items-center justify-center rounded-none bg-emerald-500">
            <Lock size={17} strokeWidth={2} className="text-emerald-950" />
          </div>
          <div className="min-w-0">
            <div className="text-base font-semibold text-white">
              {isRotate ? `Rotate key - ${existingKey.label}` : `Add ${engine.provider} key`}
            </div>
            <div className="mt-1 text-[12.5px] text-slate-400">
              {isRotate
                ? "The existing value is unrecoverable - paste a replacement."
                : "Encrypted at rest and never returned to the browser."}
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="ml-auto flex-none rounded-none p-0.5 text-slate-500 transition hover:text-white"
          >
            <X size={17} />
          </button>
        </div>

        <div className="flex min-h-0 flex-col gap-4 overflow-y-auto p-6">
          <div className="rounded-none border border-hairline bg-slate-50 px-4 py-3">
            <div className="text-[11px] font-semibold uppercase tracking-[0.1em] text-slate-500">
              {engine.section}
            </div>
            <div className="mt-1 font-mono text-[12.5px] text-ink">
              {engine.provider} - {engine.models.join(", ")}
            </div>
          </div>

          <label className="flex flex-col gap-2">
            <span className="text-[11px] font-semibold uppercase tracking-[0.1em] text-slate-700">
              Key label
            </span>
            <input
              type="text"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder={`${engine.id === "text" ? "deepseek" : "gemini"}-pool-01`}
              className="rounded-none border border-slate-300 bg-white px-3.5 py-3 text-sm text-ink"
            />
          </label>

          <label className="flex flex-col gap-2">
            <span className="text-[11px] font-semibold uppercase tracking-[0.1em] text-slate-700">
              Secret key
            </span>
            <div className="flex rounded-none border border-slate-300 bg-white">
              <input
                type={showSecret ? "text" : "password"}
                value={secret}
                onChange={(e) => setSecret(e.target.value)}
                placeholder={engine.keyPlaceholder}
                autoComplete="off"
                spellCheck={false}
                className="min-w-0 flex-1 rounded-none border-0 bg-transparent px-3.5 py-3 font-mono text-sm tracking-wide text-ink"
              />
              <button
                type="button"
                onClick={() => setShowSecret((v) => !v)}
                className="flex flex-none items-center gap-2 rounded-none border-l border-hairline bg-slate-50 px-3.5 text-xs font-semibold text-slate-700 transition hover:bg-slate-100"
              >
                <Eye size={15} strokeWidth={1.8} />
                {showSecret ? "Hide" : "Show"}
              </button>
            </div>
            <span className="text-[11.5px] text-slate-400">
              Stored AES-256-GCM envelope-encrypted. Only the last four characters are ever
              displayed again.
            </span>
          </label>

          <label className="flex flex-col gap-2">
            <span className="text-[11px] font-semibold uppercase tracking-[0.1em] text-slate-700">
              Daily quota
            </span>
            <input
              type="text"
              value={quota}
              onChange={(e) => setQuota(e.target.value)}
              className="rounded-none border border-slate-300 bg-white px-3.5 py-3 text-sm text-ink"
            />
          </label>

          {error && (
            <div
              role="alert"
              className="flex gap-3 rounded-none border border-red-200 bg-red-50 px-4 py-3.5"
            >
              <AlertTriangle size={16} strokeWidth={2} className="mt-0.5 flex-none text-red-700" />
              <span className="text-[12.5px] leading-relaxed text-red-800">{error}</span>
            </div>
          )}

          <div className="flex gap-3 rounded-none border border-amber-200 bg-amber-50 px-4 py-3.5">
            <AlertTriangle size={16} strokeWidth={2} className="mt-0.5 flex-none text-amber-700" />
            <span className="text-[12.5px] leading-relaxed text-amber-800">
              Saving rotates the credential for every tenant immediately. In-flight requests
              finish on the old key.
            </span>
          </div>
        </div>

        <div className="flex flex-none flex-wrap items-center gap-2.5 rounded-none border-t border-hairline bg-slate-50 px-6 py-4">
          <span className="font-mono text-xs text-slate-500">
            audit: {isRotate ? "vault.rotate" : "vault.create"}
          </span>
          <div className="ml-auto flex gap-2.5">
            <button
              type="button"
              onClick={onClose}
              className="rounded-none border border-slate-300 bg-white px-4 py-2.5 text-[13px] font-medium text-slate-700 transition hover:bg-slate-100"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="flex items-center gap-2 rounded-none bg-emerald-600 px-4 py-2.5 text-[13px] font-semibold text-white transition hover:bg-emerald-700"
            >
              <Check size={15} strokeWidth={2.5} />
              {isRotate ? "Rotate key" : "Save key"}
            </button>
          </div>
        </div>
      </form>
    </div>
  );
}
