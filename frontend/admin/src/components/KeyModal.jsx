import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Check, Eye, Lock, X } from "lucide-react";

import { providersFor } from "../seed/engines.js";

/**
 * Add / rotate a provider credential.
 *
 * D-075: the secret input is type="password" with an explicit show/hide,
 * autoComplete off and spellCheck off.
 *
 * D-072: the plaintext never leaves this component. On save only the last four
 * characters are handed upward for display; the API has no read path at all.
 *
 * A-010: the engine (role) is fixed by the section you opened; the provider is
 * chosen here. Changing the provider cannot change the engine contract - a TEXT
 * key still cannot carry an image, whoever serves it.
 */
export function KeyModal({ engine, existingKey, onClose, onSave }) {
  const isRotate = Boolean(existingKey);
  const providers = useMemo(() => providersFor(engine.id), [engine.id]);

  const [providerId, setProviderId] = useState(existingKey?.provider ?? providers[0]?.id);
  const [label, setLabel] = useState(existingKey?.label ?? "");
  const [secret, setSecret] = useState("");
  const [baseUrl, setBaseUrl] = useState(existingKey?.base_url ?? "");
  const [model, setModel] = useState(existingKey?.model ?? "");
  const [quota, setQuota] = useState(existingKey?.daily_quota ?? "");
  const [showSecret, setShowSecret] = useState(false);
  const [error, setError] = useState("");

  const provider = providers.find((p) => p.id === providerId) ?? providers[0];
  const placeholderModel =
    engine.id === "VISION"
      ? provider?.defaultVisionModel || provider?.defaultModel
      : provider?.defaultModel;

  useEffect(() => {
    const onKeyDown = (event) => event.key === "Escape" && onClose();
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
    if (provider?.needsBaseUrl && !baseUrl.trim()) {
      setError("A generic OpenAI-compatible endpoint needs a base URL.");
      return;
    }
    onSave({
      engineId: engine.id,
      keyId: existingKey?.id,
      provider: providerId,
      label: label.trim(),
      secret: trimmed,
      base_url: baseUrl.trim(),
      model: model.trim(),
      daily_quota: quota ? Number(quota) : null
    });
    setSecret("");
    onClose();
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={isRotate ? `Rotate key ${existingKey.label}` : `Add a ${engine.section} key`}
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-[#07101C]/75 p-6"
    >
      <form
        onSubmit={submit}
        className="m-auto flex max-h-[calc(100vh-48px)] w-full max-w-[560px] flex-col rounded-none border border-ink bg-white"
      >
        <div className="flex flex-none items-start gap-4 bg-ink px-6 py-5">
          <div className="flex h-[34px] w-[34px] flex-none items-center justify-center rounded-none bg-emerald-500">
            <Lock size={17} strokeWidth={2} className="text-emerald-950" />
          </div>
          <div className="min-w-0">
            <div className="text-base font-semibold text-white">
              {isRotate ? `Rotate key - ${existingKey.label}` : `Add key - ${engine.section}`}
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
          <label className="flex flex-col gap-2">
            <span className="text-[11px] font-semibold uppercase tracking-[0.1em] text-slate-700">
              Provider
            </span>
            <select
              value={providerId}
              onChange={(e) => setProviderId(e.target.value)}
              className="rounded-none border border-slate-300 bg-white px-3.5 py-3 text-sm text-ink"
            >
              {providers.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.label}
                </option>
              ))}
            </select>
            {provider?.hint && (
              <span className="text-[11.5px] text-slate-400">{provider.hint}</span>
            )}
          </label>

          <label className="flex flex-col gap-2">
            <span className="text-[11px] font-semibold uppercase tracking-[0.1em] text-slate-700">
              Key label
            </span>
            <input
              type="text"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder={`${providerId.toLowerCase()}-${engine.id.toLowerCase()}-01`}
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

          <div className="grid gap-3.5 sm:grid-cols-2">
            <label className="flex flex-col gap-2">
              <span className="text-[11px] font-semibold uppercase tracking-[0.1em] text-slate-700">
                Model
              </span>
              <input
                type="text"
                value={model}
                onChange={(e) => setModel(e.target.value)}
                placeholder={placeholderModel || "required"}
                className="rounded-none border border-slate-300 bg-white px-3.5 py-3 font-mono text-[13px] text-ink"
              />
              <span className="text-[11.5px] text-slate-400">
                Blank uses the provider default.
              </span>
            </label>

            <label className="flex flex-col gap-2">
              <span className="text-[11px] font-semibold uppercase tracking-[0.1em] text-slate-700">
                Daily quota
              </span>
              <input
                type="number"
                min="1"
                value={quota}
                onChange={(e) => setQuota(e.target.value)}
                placeholder="unmetered"
                className="rounded-none border border-slate-300 bg-white px-3.5 py-3 text-sm text-ink"
              />
            </label>
          </div>

          {/* Only meaningful for a generic endpoint; hidden noise otherwise. */}
          {provider?.needsBaseUrl && (
            <label className="flex flex-col gap-2">
              <span className="text-[11px] font-semibold uppercase tracking-[0.1em] text-slate-700">
                Base URL
              </span>
              <input
                type="url"
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
                placeholder="https://api.groq.com/openai/v1"
                className="rounded-none border border-slate-300 bg-white px-3.5 py-3 font-mono text-[13px] text-ink"
              />
            </label>
          )}

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
