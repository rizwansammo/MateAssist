/**
 * Deterministic tenant avatar colours (D-088).
 *
 * The prototype hardcoded a colour per tenant name, so tenant number seven
 * would have rendered grey forever. Deriving from the slug means every tenant
 * gets a stable colour the moment it is provisioned, with no lookup to maintain.
 */

const PALETTE = [
  "bg-ink text-emerald-400",
  "bg-cyan-900 text-cyan-200",
  "bg-emerald-800 text-emerald-200",
  "bg-amber-900 text-amber-200",
  "bg-slate-800 text-slate-300",
  "bg-teal-900 text-teal-200"
];

/** FNV-1a: tiny, stable across runs, and good enough to spread short slugs. */
function hash(value) {
  let h = 0x811c9dc5;
  for (let i = 0; i < value.length; i += 1) {
    h ^= value.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h;
}

export function avatarClasses(slug = "") {
  return PALETTE[hash(slug) % PALETTE.length];
}

export function avatarInitials(name = "") {
  return name.slice(0, 2).toUpperCase();
}
