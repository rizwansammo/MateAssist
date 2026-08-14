import { useCallback, useEffect, useRef, useState } from "react";
import { Image as ImageIcon, Paperclip, Send, X } from "lucide-react";

/**
 * Chat composer with screenshot support (D-091).
 *
 * Three ways to attach, because people reach for different ones: Ctrl+V after a
 * Snipping Tool capture, drag from a folder, or the paperclip. Paste is the one
 * that matters most for a helpdesk - the user has just screenshotted an error.
 *
 * The image goes to the vision engine and stops there; only the text it returns
 * reaches the reasoning engine (D-042).
 */
export function ChatComposer({ onSend, busy }) {
  const [text, setText] = useState("");
  const [image, setImage] = useState(null);
  const [preview, setPreview] = useState("");
  const [dragging, setDragging] = useState(false);
  const fileRef = useRef(null);

  const attach = useCallback((file) => {
    if (!file || !file.type.startsWith("image/")) return;
    setImage(file);
    setPreview(URL.createObjectURL(file));
  }, []);

  const clear = useCallback(() => {
    setImage(null);
    // Revoking matters: without it every pasted screenshot leaks an object URL
    // for the lifetime of the tab.
    setPreview((current) => {
      if (current) URL.revokeObjectURL(current);
      return "";
    });
  }, []);

  useEffect(() => {
    const onPaste = (event) => {
      const item = Array.from(event.clipboardData?.items ?? []).find((i) =>
        i.type.startsWith("image/")
      );
      if (item) attach(item.getAsFile());
    };
    window.addEventListener("paste", onPaste);
    return () => window.removeEventListener("paste", onPaste);
  }, [attach]);

  useEffect(() => () => preview && URL.revokeObjectURL(preview), [preview]);

  const submit = () => {
    if (busy) return;
    if (!text.trim() && !image) return;
    onSend({ text: text.trim(), image });
    setText("");
    clear();
  };

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        attach(e.dataTransfer.files?.[0]);
      }}
      className={`sticky bottom-0 border-t bg-white px-6 pb-5 pt-4 ${
        dragging ? "border-emerald-600 bg-emerald-50" : "border-hairline"
      }`}
    >
      {preview && (
        <div className="mb-3 flex items-start gap-3 rounded-none border border-hairline bg-slate-50 p-3">
          <img
            src={preview}
            alt="Attached screenshot preview"
            className="h-20 w-auto rounded-none border border-hairline object-contain"
          />
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 text-[12.5px] font-medium text-ink">
              <ImageIcon size={14} className="text-slate-500" />
              {image?.name || "screenshot.png"}
            </div>
            <p className="mt-1 text-[11.5px] leading-relaxed text-slate-500">
              This image is read by the vision engine; only its text description is sent to
              the assistant.
            </p>
          </div>
          <button
            type="button"
            onClick={clear}
            aria-label="Remove attachment"
            className="rounded-none p-1 text-slate-400 transition hover:text-ink"
          >
            <X size={15} />
          </button>
        </div>
      )}

      <div className="flex rounded-none border border-slate-300 bg-white">
        <button
          type="button"
          onClick={() => fileRef.current?.click()}
          aria-label="Attach a screenshot"
          className="flex flex-none items-center rounded-none border-r border-hairline px-3 text-slate-500 transition hover:text-ink"
        >
          <Paperclip size={16} />
        </button>
        <input
          ref={fileRef}
          type="file"
          accept="image/*"
          onChange={(e) => {
            attach(e.target.files?.[0]);
            e.target.value = "";
          }}
          className="hidden"
        />
        <input
          type="text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && submit()}
          disabled={busy}
          placeholder={
            busy ? "MateAssist is answering..." : "Describe your issue, or paste a screenshot"
          }
          className="min-w-0 flex-1 rounded-none border-0 bg-transparent px-4 py-3.5 text-sm text-ink disabled:bg-slate-50"
        />
        <button
          type="button"
          onClick={submit}
          disabled={busy || (!text.trim() && !image)}
          className="flex flex-none items-center gap-2 rounded-none bg-ink px-5 text-[13px] font-semibold text-white transition hover:bg-emerald-600 disabled:cursor-not-allowed disabled:bg-slate-400"
        >
          Send
          <Send size={15} />
        </button>
      </div>
      <div className="mt-2.5 text-[11.5px] text-slate-400">
        Paste a screenshot with Ctrl+V, drag one in, or use the paperclip.
      </div>
    </div>
  );
}
