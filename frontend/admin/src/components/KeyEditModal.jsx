import { useState } from "react";
import { AlertTriangle, Lock, X } from "lucide-react";

/**
 * Edit a key's configuration without re-entering its credential (D-155).
 *
 * Separate from KeyModal on purpose. That dialog exists to accept a secret;
 * this one cannot, and the absence of the field is the point - an operator
 * correcting a model id should not be holding a live credential in a form at
 * all. The engine is shown but not editable: a key's role is fixed at creation,
 * because the guarantee that text engines never receive images (A-010) must not
 * depend on an admin form.
 *
 * Why this exists: providers retire model names. When Google withdrew
 * gemini-1.5-flash the only route to a working configuration was deleting the
 * key and typing the secret again - friction that ends with an operator leaving
 * something broken.
 */

const FIELD =
  "w-full rounded-none border border-hairline bg-white px-3.5 py-2.5 text-[13.5px] " +
  "text-ink outline-none transition placeholder:text-slate-300 focus:border-emerald-600";

const LABEL =
  "mb-1.5 block text-[12px] font-semibold uppercase tracking-[0.1em] text-slate-500";

export function KeyEditModal({ apiKey, onClose, onSave }) {
  const [form, setForm] = useState({
    label: apiKey.label,
    model: apiKey.model ?? "",
    base_url: apiKey.base_url ?? "",
    weight: apiKey.weight ?? 1,
    daily_quota: apiKey.daily_quota ?? ""
  });
  const [saving, setSaving] = useState(false);

  const set = (field) => (event) => setForm({ ...form, [field]: event.target.value });

  const submit = async (event) => {
    event.preventDefault();
    setSaving(true);
    // An empty quota means unmetered, which is null rather than "".
    await onSave({
      ...form,
      weight: Number(form.weight) || 1,
      daily_quota: form.daily_quota === "" ? null : Number(form.daily_quota)
    });
    setSaving(false);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/50 p-4">
      <form
        onSubmit={submit}
        className="max-h-[90vh] w-full max-w-[560px] overflow-y-auto rounded-none border border-hairline bg-white"
      >
        <div className="flex items-start justify-between border-b border-hairline px-6 py-4">
          <div>
            <div className="text-[15px] font-semibold text-ink">Edit key</div>
            <div className="mt-0.5 text-[12.5px] text-slate-500">
              {apiKey.engine} engine &middot; {apiKey.provider}
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-none border border-hairline bg-white p-1.5 text-slate-500 transition hover:bg-slate-50"
          >
            <X size={15} />
          </button>
        </div>

        <div className="grid gap-5 px-6 py-5">
          <div className="flex items-center gap-2.5 rounded-none border border-hairline bg-slate-50 px-3.5 py-2.5">
            <Lock size={14} className="flex-none text-slate-500" />
            <span className="font-mono text-[12.5px] tracking-wide text-slate-700">
              {apiKey.masked}
            </span>
            <span className="ml-auto text-[11.5px] text-slate-400">
              Unchanged &mdash; use Rotate to replace it
            </span>
          </div>

          <div>
            <label htmlFor="edit_label" className={LABEL}>
              Label
            </label>
            <input id="edit_label" value={form.label} onChange={set("label")} className={FIELD} />
          </div>

          <div>
            <label htmlFor="edit_model" className={LABEL}>
              Model
            </label>
            <input
              id="edit_model"
              value={form.model}
              onChange={set("model")}
              placeholder={apiKey.resolved_model}
              className={`${FIELD} font-mono`}
            />
            <p className="mt-1.5 text-[11.5px] text-slate-400">
              Blank uses the provider default. Currently calling{" "}
              <span className="font-mono text-slate-600">{apiKey.resolved_model}</span>.
            </p>
          </div>

          <div>
            <label htmlFor="edit_base_url" className={LABEL}>
              Base URL
            </label>
            <input
              id="edit_base_url"
              value={form.base_url}
              onChange={set("base_url")}
              placeholder={apiKey.resolved_base_url}
              className={`${FIELD} font-mono`}
            />
          </div>

          <div className="grid gap-5 sm:grid-cols-2">
            <div>
              <label htmlFor="edit_weight" className={LABEL}>
                Weight
              </label>
              <input
                id="edit_weight"
                type="number"
                min={1}
                max={100}
                value={form.weight}
                onChange={set("weight")}
                className={FIELD}
              />
            </div>
            <div>
              <label htmlFor="edit_quota" className={LABEL}>
                Daily quota
              </label>
              <input
                id="edit_quota"
                type="number"
                min={1}
                value={form.daily_quota}
                onChange={set("daily_quota")}
                placeholder="unmetered"
                className={FIELD}
              />
            </div>
          </div>

          <div className="flex gap-3 rounded-none border border-amber-200 bg-amber-50 p-3.5">
            <AlertTriangle size={15} className="mt-0.5 flex-none text-amber-600" />
            <div className="text-[12.5px] leading-relaxed text-amber-900">
              Saving puts this key straight back into rotation if it was parked as
              rate-limited. Press <strong>Test</strong> afterwards to confirm the model
              actually answers before a user finds out.
            </div>
          </div>
        </div>

        <div className="flex justify-end gap-3 border-t border-hairline px-6 py-4">
          <button
            type="button"
            onClick={onClose}
            className="rounded-none border border-slate-300 bg-white px-4 py-2.5 text-[13px] font-medium text-slate-700 transition hover:bg-slate-50"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={saving}
            className="rounded-none border border-ink bg-ink px-5 py-2.5 text-[13px] font-semibold text-white transition hover:bg-slate-800 disabled:opacity-60"
          >
            {saving ? "Saving..." : "Save changes"}
          </button>
        </div>
      </form>
    </div>
  );
}
