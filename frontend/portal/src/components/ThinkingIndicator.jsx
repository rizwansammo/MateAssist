import { Bot } from "lucide-react";

/**
 * What the assistant is doing right now (D-165).
 *
 * A single static line said "Looking this up..." for the whole wait, which is
 * the one thing a person cannot tell from a frozen screen: whether anything is
 * happening at all. Movement is the reassurance - the words only say which part
 * of the work is running.
 *
 * The two phases are genuinely different lengths. Retrieval is about 50ms;
 * writing takes seconds. Naming them separately means the label is true rather
 * than merely present.
 *
 * Squares, not dots: D-100 puts zero border-radius on everything in this
 * product, and a typing indicator is not the place to make an exception.
 */

const PHASE = {
  searching: {
    label: "Searching your runbooks",
    hint: "Finding the documents that match your question"
  },
  writing: {
    label: "Writing your answer",
    hint: "Working through what the runbook says"
  }
};

export function ThinkingIndicator({ phase }) {
  const state = PHASE[phase] ?? PHASE.searching;

  return (
    <div className="flex gap-3" role="status" aria-live="polite">
      <div className="relative flex h-[30px] w-[30px] flex-none items-center justify-center rounded-none bg-ink">
        <Bot size={16} strokeWidth={1.8} className="text-emerald-400" />
        {/* A slow halo on the avatar, so the whole row reads as active rather
            than just the three squares. */}
        <span className="absolute inset-0 animate-ping bg-emerald-500/20" />
      </div>

      <div className="min-w-0 rounded-none border border-hairline bg-white px-4 py-3">
        <div className="flex items-center gap-2.5">
          <span className="flex items-end gap-1" aria-hidden="true">
            {[0, 1, 2].map((index) => (
              <span
                key={index}
                className="h-[6px] w-[6px] animate-bounce rounded-none bg-emerald-500"
                // Staggered so they travel as a wave. Identical delays would
                // pulse in unison, which reads as a loading bar rather than
                // something composing a reply.
                style={{ animationDelay: `${index * 140}ms`, animationDuration: "900ms" }}
              />
            ))}
          </span>

          <span className="text-[13.5px] font-medium text-ink">{state.label}</span>

          {/* A moving sheen across the label. Cheap, and it keeps the row alive
              during the long gaps between token batches. */}
          <span className="relative ml-1 hidden h-[3px] w-16 overflow-hidden bg-slate-100 sm:block">
            <span className="absolute inset-y-0 -left-1/2 w-1/2 animate-shimmer bg-emerald-500/70" />
          </span>
        </div>

        <p className="mt-1 text-[12px] leading-relaxed text-slate-500">{state.hint}</p>
      </div>
    </div>
  );
}
