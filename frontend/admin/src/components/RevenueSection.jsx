import { useCallback, useEffect, useState } from "react";
import { Plus, Receipt, Trash2 } from "lucide-react";

import { useAdmin } from "../context/AdminContext.jsx";
import { vaultApi } from "../lib/vault.js";

/**
 * What workspaces are charged, and what each owes this month (D-160).
 *
 * Sits above the cost analysis on the same page, and the ordering is the point:
 * revenue first, then what it cost to produce. The two must never be read as
 * one number - `BillingRate` is the sell price, `ModelPrice` is the buy price,
 * and their difference is the margin shown in the last column.
 *
 * Statements are recomputed from usage events on every request, never stored. A
 * saved invoice is a second copy of the truth that drifts from the usage table
 * the moment either is corrected.
 */

const CELL = "border-b border-slate-100 px-4 py-3.5";
const HEAD = "border-b border-hairline px-4 py-3";

function currentMonth() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

export function RevenueSection({ tenants = [] }) {
  const { notify } = useAdmin();
  const [month, setMonth] = useState(currentMonth());
  const [statements, setStatements] = useState(null);
  const [rates, setRates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [adding, setAdding] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [statementData, rateData] = await Promise.all([
        vaultApi.statements(month),
        vaultApi.billingRates()
      ]);
      setStatements(statementData);
      setRates(Array.isArray(rateData) ? rateData : (rateData?.results ?? []));
    } catch (error) {
      notify("Could not load billing", error.message, "warn");
    } finally {
      setLoading(false);
    }
  }, [month, notify]);

  useEffect(() => {
    load();
  }, [load]);

  const removeRate = async (rate) => {
    if (!window.confirm("Delete this rate? Statements will fall back to the one before it.")) {
      return;
    }
    try {
      await vaultApi.deleteBillingRate(rate.id);
      await load();
    } catch (error) {
      notify("Could not delete that rate", error.message, "warn");
    }
  };

  const rows = statements?.statements ?? [];
  const unbilled = rows.filter((row) => !row.billable);

  return (
    <>
      <section className="rounded-none border border-hairline bg-white">
        <div className="flex flex-wrap items-center gap-3 border-b border-hairline px-6 py-4">
          <Receipt size={16} strokeWidth={1.8} className="text-slate-500" />
          <div className="flex-1">
            <div className="text-[15px] font-semibold text-ink">Invoices</div>
            <div className="mt-0.5 text-[12.5px] text-slate-500">
              What each workspace owes. Recomputed from usage, never stored.
            </div>
          </div>
          <input
            type="month"
            value={month}
            onChange={(event) => setMonth(event.target.value)}
            className="rounded-none border border-hairline bg-white px-3 py-2 text-[13px] text-ink outline-none focus:border-emerald-600"
          />
          <div className="rounded-none border border-ink bg-ink px-4 py-2 text-right">
            <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-400">
              Billed
            </div>
            <div className="font-mono text-[15px] font-semibold text-white">
              ${statements?.total ?? "0.00"}
            </div>
          </div>
        </div>

        {unbilled.length > 0 && (
          // Not decoration. A workspace with no rate has an UNKNOWN bill, and
          // reporting it as $0.00 would hide real usage behind a number that
          // looks like a finished answer.
          <div className="border-b border-amber-200 bg-amber-50 px-6 py-3.5">
            <div className="text-[13px] font-semibold text-amber-900">
              {unbilled.length} workspace(s) have no rate in force for {month}, so their usage
              is not charged
            </div>
            <div className="mt-1 text-[12px] text-amber-800">
              {unbilled
                .map((row) => `${row.tenant} (${row.tokens.toLocaleString()} tokens)`)
                .join(", ")}
            </div>
            {/* The usual cause is not a missing rate but one dated after the
                month being viewed, which is invisible without saying so. */}
            <div className="mt-1.5 text-[12px] text-amber-800">
              A rate only applies to months that start on or after its effective date. If you
              added one mid-month, add another dated the 1st to charge {month}.
            </div>
          </div>
        )}

        <div className="overflow-x-auto">
          <table className="w-full text-left text-[13px]">
            <thead>
              <tr className="text-[11px] font-semibold uppercase tracking-[0.1em] text-slate-500">
                <th className={`${HEAD} pl-6`}>Workspace</th>
                <th className={`${HEAD} text-right`}>Tokens</th>
                <th className={`${HEAD} text-right`}>Images</th>
                <th className={`${HEAD} text-right`}>Escalations</th>
                <th className={`${HEAD} text-right`}>Rate</th>
                <th className={`${HEAD} text-right`}>Charged</th>
                <th className={`${HEAD} text-right`}>Our cost</th>
                <th className={`${HEAD} pr-6 text-right`}>Margin</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.tenant}>
                  <td className={`${CELL} pl-6`}>
                    <div className="font-medium text-ink">{row.tenant}</div>
                    {row.rate_is_override && (
                      <div className="mt-0.5 text-[11px] text-cyan-700">negotiated rate</div>
                    )}
                  </td>
                  <td className={`${CELL} text-right font-mono text-slate-600`}>
                    {row.tokens.toLocaleString()}
                  </td>
                  <td className={`${CELL} text-right font-mono text-slate-600`}>{row.images}</td>
                  <td className={`${CELL} text-right font-mono text-slate-600`}>
                    {row.escalations ?? 0}
                  </td>
                  <td className={`${CELL} text-right font-mono text-slate-500`}>
                    {row.billable ? `$${row.rate_per_1m_tokens}/1M` : "-"}
                  </td>
                  <td className={`${CELL} text-right font-mono font-semibold text-ink`}>
                    {row.billable ? `$${row.total}` : "not billable"}
                  </td>
                  <td className={`${CELL} text-right font-mono text-slate-500`}>
                    {row.billable ? `$${row.provider_cost}` : "-"}
                  </td>
                  <td className={`${CELL} pr-6 text-right font-mono font-semibold`}>
                    {row.billable ? (
                      <span
                        className={
                          Number(row.margin) < 0 ? "text-red-700" : "text-emerald-700"
                        }
                      >
                        ${row.margin}
                      </span>
                    ) : (
                      "-"
                    )}
                  </td>
                </tr>
              ))}
              {!loading && rows.length === 0 && (
                <tr>
                  <td colSpan={8} className="px-6 py-10 text-center text-slate-500">
                    No workspaces to bill for {month}.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      {/* ---- rates ---- */}
      <section className="rounded-none border border-hairline bg-white">
        <div className="flex flex-wrap items-center gap-3 border-b border-hairline px-6 py-4">
          <div className="flex-1">
            <div className="text-[15px] font-semibold text-ink">Billing rates</div>
            <div className="mt-0.5 text-[12.5px] text-slate-500">
              What workspaces pay you. Distinct from model prices below, which are what you pay
              providers.
            </div>
          </div>
          <button
            type="button"
            onClick={() => setAdding(true)}
            className="flex items-center gap-1.5 rounded-none border border-ink bg-ink px-3.5 py-2 text-[12.5px] font-semibold text-white transition hover:bg-slate-800"
          >
            <Plus size={14} />
            Add rate
          </button>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-[13px]">
            <thead>
              <tr className="text-[11px] font-semibold uppercase tracking-[0.1em] text-slate-500">
                <th className={`${HEAD} pl-6`}>Applies to</th>
                <th className={`${HEAD} text-right`}>Per 1M tokens</th>
                <th className={`${HEAD} text-right`}>Per request</th>
                <th className={`${HEAD} text-right`}>Per image</th>
                <th className={`${HEAD} text-right`}>Per escalation</th>
                <th className={HEAD}>Effective from</th>
                <th className={`${HEAD} pr-6 text-right`}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {rates.map((rate) => (
                <tr key={rate.id}>
                  <td className={`${CELL} pl-6 font-medium text-ink`}>
                    {rate.tenant_name ?? "All workspaces"}
                  </td>
                  <td className={`${CELL} text-right font-mono`}>${rate.per_1m_tokens}</td>
                  <td className={`${CELL} text-right font-mono`}>${rate.per_request}</td>
                  <td className={`${CELL} text-right font-mono`}>${rate.per_image}</td>
                  <td className={`${CELL} text-right font-mono`}>${rate.per_escalation}</td>
                  <td className={`${CELL} text-slate-600`}>{rate.effective_from}</td>
                  <td className={`${CELL} pr-6 text-right`}>
                    <button
                      type="button"
                      onClick={() => removeRate(rate)}
                      aria-label="Delete rate"
                      className="rounded-none border border-red-200 bg-white p-1.5 text-red-700 transition hover:bg-red-50"
                    >
                      <Trash2 size={14} />
                    </button>
                  </td>
                </tr>
              ))}
              {!loading && rates.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-6 py-10 text-center text-slate-500">
                    No rates set, so nothing can be billed yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      {adding && (
        <RateDialog
          tenants={tenants}
          onClose={() => setAdding(false)}
          onSaved={async () => {
            setAdding(false);
            await load();
          }}
        />
      )}
    </>
  );
}

function RateDialog({ tenants, onClose, onSaved }) {
  const { notify } = useAdmin();
  const [form, setForm] = useState({
    tenant: "",
    per_1m_tokens: "15",
    per_image: "0.02",
    // Zero means "do not charge for this unit" rather than "free" - a rate with
    // tokens at 0 and requests set is simply a per-request contract.
    per_request: "0",
    per_escalation: "0",
    // The FIRST of this month, not today. A month is billed at the rate in
    // force on its first day, so a rate dated today leaves the month you are
    // looking at "not billable" the moment you save it - which reads as the
    // rate having failed. Defaulting to the 1st makes the obvious action
    // produce the obvious result.
    effective_from: `${currentMonth()}-01`,
    note: ""
  });
  const [saving, setSaving] = useState(false);

  const submit = async (event) => {
    event.preventDefault();
    setSaving(true);
    try {
      await vaultApi.saveBillingRate({ ...form, tenant: form.tenant || null });
      await onSaved();
    } catch (error) {
      notify("Could not save that rate", error.message, "warn");
    } finally {
      setSaving(false);
    }
  };

  const field =
    "w-full rounded-none border border-hairline bg-white px-3.5 py-2.5 text-[13.5px] text-ink outline-none focus:border-emerald-600";
  const label =
    "mb-1.5 block text-[12px] font-semibold uppercase tracking-[0.1em] text-slate-500";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/50 p-4">
      <form onSubmit={submit} className="w-full max-w-[520px] rounded-none border border-hairline bg-white">
        <div className="border-b border-hairline px-6 py-4">
          <div className="text-[15px] font-semibold text-ink">Add a billing rate</div>
          <div className="mt-0.5 text-[12.5px] text-slate-500">
            Rates are a history, not a setting. Adding one leaves earlier invoices untouched.
          </div>
        </div>

        <div className="grid gap-5 px-6 py-5">
          <div>
            <label htmlFor="rate_tenant" className={label}>
              Applies to
            </label>
            <select
              id="rate_tenant"
              value={form.tenant}
              onChange={(e) => setForm({ ...form, tenant: e.target.value })}
              className={field}
            >
              <option value="">All workspaces (default)</option>
              {tenants.map((tenant) => (
                <option key={tenant.id} value={tenant.id}>
                  {tenant.name} - override
                </option>
              ))}
            </select>
          </div>

          <div className="grid gap-5 sm:grid-cols-2">
            <div>
              <label htmlFor="rate_tokens" className={label}>
                Per 1M tokens
              </label>
              <input
                id="rate_tokens"
                value={form.per_1m_tokens}
                onChange={(e) => setForm({ ...form, per_1m_tokens: e.target.value })}
                className={`${field} font-mono`}
              />
            </div>
            <div>
              <label htmlFor="rate_request" className={label}>
                Per request
              </label>
              <input
                id="rate_request"
                value={form.per_request}
                onChange={(e) => setForm({ ...form, per_request: e.target.value })}
                className={`${field} font-mono`}
              />
            </div>
            <div>
              <label htmlFor="rate_image" className={label}>
                Per image
              </label>
              <input
                id="rate_image"
                value={form.per_image}
                onChange={(e) => setForm({ ...form, per_image: e.target.value })}
                className={`${field} font-mono`}
              />
            </div>
            <div>
              <label htmlFor="rate_escalation" className={label}>
                Per escalation
              </label>
              <input
                id="rate_escalation"
                value={form.per_escalation}
                onChange={(e) => setForm({ ...form, per_escalation: e.target.value })}
                className={`${field} font-mono`}
              />
            </div>
          </div>

          <p className="-mt-1 text-[11.5px] leading-relaxed text-slate-400">
            These add up. Leave a price at <span className="font-mono">0</span> to not charge
            for that unit &mdash; a per-request contract is simply tokens at 0.
          </p>

          <div>
            <label htmlFor="rate_from" className={label}>
              Effective from
            </label>
            <input
              id="rate_from"
              type="date"
              value={form.effective_from}
              onChange={(e) => setForm({ ...form, effective_from: e.target.value })}
              className={field}
            />
            <p className="mt-1.5 text-[11.5px] text-slate-400">
              A month is billed at the rate in force on its first day, so this defaults to the
              1st of this month. Set it later only to schedule a price change.
            </p>
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
            {saving ? "Saving..." : "Add rate"}
          </button>
        </div>
      </form>
    </div>
  );
}
