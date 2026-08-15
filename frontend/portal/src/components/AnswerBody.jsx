import Markdown from "react-markdown";

/**
 * Renders an assistant answer as Markdown (D-152).
 *
 * The prompt asks the model for numbered steps, **bold** UI labels and
 * `backticked` commands, because a wall of prose is unreadable at a broken
 * machine. Rendered as plain text, those markers show up literally - asterisks
 * and backticks scattered through the answer - so the formatting rules and this
 * component only make sense together. Shipping either alone makes the output
 * worse than doing nothing.
 *
 * **No raw HTML, deliberately.** react-markdown ignores embedded HTML unless a
 * plugin is added, and none is. That matters more here than in a typical
 * Markdown view: this text is model output shaped by retrieved runbook content,
 * which is untrusted (D-130). A runbook containing a <script> tag must render as
 * the characters "<script>", not execute. Do not add rehype-raw.
 *
 * Every element is styled explicitly. The default browser styles round nothing
 * but do add margins and radii that would break D-100 and the vertical rhythm.
 */
const COMPONENTS = {
  p: ({ children }) => <p className="mb-3 last:mb-0 leading-relaxed">{children}</p>,

  // Ordered lists carry the steps, so they get the most attention: a marker
  // that reads as a step number rather than a bullet, and enough spacing that
  // one step does not blur into the next.
  ol: ({ children }) => (
    <ol className="mb-3 last:mb-0 ml-0 list-none space-y-2 [counter-reset:step]">{children}</ol>
  ),
  ul: ({ children }) => (
    <ul className="mb-3 last:mb-0 ml-0 list-none space-y-1.5">{children}</ul>
  ),
  li: ({ children, ...props }) => {
    const ordered = props.node?.parentNode?.tagName === "ol";
    return ordered ? (
      <li className="relative pl-7 leading-relaxed [counter-increment:step] before:absolute before:left-0 before:top-[3px] before:flex before:h-[18px] before:w-[18px] before:items-center before:justify-center before:bg-ink before:text-[10.5px] before:font-bold before:text-emerald-400 before:content-[counter(step)]">
        {children}
      </li>
    ) : (
      <li className="relative pl-4 leading-relaxed before:absolute before:left-0 before:top-[9px] before:h-[5px] before:w-[5px] before:bg-emerald-500 before:content-['']">
        {children}
      </li>
    );
  },

  strong: ({ children }) => <strong className="font-semibold text-ink">{children}</strong>,
  em: ({ children }) => <em className="italic">{children}</em>,

  // Inline code is commands and paths - the things people copy and mistype.
  code: ({ inline, children }) =>
    inline ? (
      <code className="rounded-none border border-hairline bg-slate-100 px-1.5 py-[1px] font-mono text-[12.5px] text-ink">
        {children}
      </code>
    ) : (
      <code className="block font-mono text-[12.5px] leading-relaxed text-slate-100">
        {children}
      </code>
    ),
  pre: ({ children }) => (
    <pre className="mb-3 last:mb-0 overflow-x-auto rounded-none border border-slate-800 bg-ink p-3.5">
      {children}
    </pre>
  ),

  h1: ({ children }) => <p className="mb-2 font-semibold text-ink">{children}</p>,
  h2: ({ children }) => <p className="mb-2 font-semibold text-ink">{children}</p>,
  h3: ({ children }) => <p className="mb-2 font-semibold text-ink">{children}</p>,

  // Links are rendered but not clickable-by-default styling surprises: an
  // answer should not send someone off to a URL the runbook did not vouch for.
  a: ({ children, href }) => (
    <a
      href={href}
      rel="noopener noreferrer nofollow"
      target="_blank"
      className="underline decoration-emerald-500 underline-offset-2"
    >
      {children}
    </a>
  ),

  blockquote: ({ children }) => (
    <blockquote className="mb-3 border-l-2 border-emerald-500 pl-3 text-slate-600">
      {children}
    </blockquote>
  ),
  hr: () => <hr className="my-4 border-hairline" />,
  table: ({ children }) => (
    <div className="mb-3 overflow-x-auto">
      <table className="w-full border-collapse text-[13px]">{children}</table>
    </div>
  ),
  th: ({ children }) => (
    <th className="border border-hairline bg-slate-50 px-2.5 py-1.5 text-left font-semibold">
      {children}
    </th>
  ),
  td: ({ children }) => <td className="border border-hairline px-2.5 py-1.5">{children}</td>
};

export function AnswerBody({ text }) {
  return (
    <div className="text-[14.5px] text-slate-800">
      <Markdown components={COMPONENTS}>{text || ""}</Markdown>
    </div>
  );
}
