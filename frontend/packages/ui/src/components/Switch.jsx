/**
 * Square toggle. Presentational only - the parent owns the state.
 *
 * No border-radius even on the knob: D-100 has no exceptions, and a rounded
 * pill toggle is the most common place a design system like this leaks.
 */
export function Switch({ on, size = "md" }) {
  const track = size === "sm" ? "h-4 w-[30px]" : "h-5 w-[38px]";
  const knob = size === "sm" ? "h-3 w-3" : "h-4 w-4";

  return (
    <span
      className={`flex ${track} flex-none items-center rounded-none p-0.5 ${
        on ? "justify-end bg-emerald-600" : "justify-start bg-slate-300"
      }`}
    >
      <span className={`${knob} rounded-none bg-white`} />
    </span>
  );
}
