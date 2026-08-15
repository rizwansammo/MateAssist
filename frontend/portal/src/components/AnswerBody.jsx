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

  // Marker styling lives on the LIST, targeting its direct children, rather
  // than on the item.
  //
  // The item used to decide for itself by reading
  // `props.node.parentNode.tagName`. react-markdown v10 does not expose a
  // parent link, so that check silently evaluated to undefined and every
  // numbered step rendered as a bullet - the model was emitting correct
  // ordered lists and we were flattening them. Styling from the parent cannot
  // drift that way: an `ol` is an `ol` whatever the library passes down.
  ol: ({ children }) => (
    <ol
      className="mb-3 last:mb-0 ml-0 list-none space-y-2.5 [counter-reset:step] [&>li]:relative [&>li]:pl-7 [&>li]:leading-relaxed [&>li]:[counter-increment:step] [&>li]:before:absolute [&>li]:before:left-0 [&>li]:before:top-[2px] [&>li]:before:flex [&>li]:before:h-[18px] [&>li]:before:w-[18px] [&>li]:before:items-center [&>li]:before:justify-center [&>li]:before:bg-ink [&>li]:before:text-[10.5px] [&>li]:before:font-bold [&>li]:before:text-emerald-400 [&>li]:before:content-[counter(step)]"
    >
      {children}
    </ol>
  ),
  ul: ({ children }) => (
    <ul className="mb-3 last:mb-0 ml-0 list-none space-y-1.5 [&>li]:relative [&>li]:pl-4 [&>li]:leading-relaxed [&>li]:before:absolute [&>li]:before:left-0 [&>li]:before:top-[9px] [&>li]:before:h-[5px] [&>li]:before:w-[5px] [&>li]:before:bg-emerald-500 [&>li]:before:content-['']">
      {children}
    </ul>
  ),

  strong: ({ children }) => <strong className="font-semibold text-ink">{children}</strong>,
  em: ({ children }) => <em className="italic">{children}</em>,

  // Inline code is commands and paths - the things people copy and mistype.
  //
  // Always styled for INLINE use. The block case is handled by `pre` below,
  // which restyles the code it contains.
  //
  // This used to branch on an `inline` prop. react-markdown stopped passing it
  // at v9, so it read as undefined and EVERY inline snippet took the block
  // branch - white text, no background, on a white bubble. Commands the reader
  // was meant to copy were rendered invisible, and the answer looked like the
  // unformatted prose the formatting rules exist to prevent.
  //
  // Nothing here now depends on a prop the library may stop sending.
  code: ({ children }) => (
    <code className="rounded-none border border-hairline bg-slate-100 px-1.5 py-[1px] font-mono text-[12.5px] text-ink">
      {children}
    </code>
  ),

  // A fenced block owns its contents, so it strips the inline chrome off the
  // `code` inside it via a descendant selector rather than by asking the code
  // element to know where it lives.
  pre: ({ children }) => (
    <pre className="mb-3 last:mb-0 overflow-x-auto rounded-none border border-slate-800 bg-ink p-3.5 [&_code]:block [&_code]:border-0 [&_code]:bg-transparent [&_code]:p-0 [&_code]:text-[12.5px] [&_code]:leading-relaxed [&_code]:text-slate-100">
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
