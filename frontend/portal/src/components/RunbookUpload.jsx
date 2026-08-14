import { useCallback, useRef, useState } from "react";
import { AlertTriangle, FileUp, Upload, X } from "lucide-react";

import { ACCEPTED_EXTENSIONS, knowledgeApi } from "../lib/knowledge.js";

/**
 * Runbook upload (D-090). Tenant-admin only - the caller decides whether to
 * render it; the API enforces it.
 *
 * Drag-and-drop plus a file picker. Files are validated by extension here for a
 * fast, friendly error; the server independently sniffs the magic bytes, because
 * a client-side check is a courtesy, not a control (D-131).
 */
export function RunbookUpload({ onUploaded, onError }) {
  const inputRef = useRef(null);
  const [dragging, setDragging] = useState(false);
  const [queue, setQueue] = useState([]);

  const accepted = ACCEPTED_EXTENSIONS.join(",");

  const startUpload = useCallback(
    async (files) => {
      const list = Array.from(files);
      if (!list.length) return;

      for (const file of list) {
        const extension = `.${file.name.split(".").pop()?.toLowerCase()}`;
        if (!ACCEPTED_EXTENSIONS.includes(extension)) {
          onError?.(`${file.name}: only ${ACCEPTED_EXTENSIONS.join(", ")} are accepted.`);
          continue;
        }

        const entry = { name: file.name, progress: 0, state: "uploading" };
        setQueue((prev) => [...prev, entry]);

        const update = (patch) =>
          setQueue((prev) =>
            prev.map((item) => (item.name === file.name ? { ...item, ...patch } : item))
          );

        try {
          const document = await knowledgeApi.upload(file, {
            onProgress: (progress) => update({ progress })
          });
          update({ state: "done", progress: 100 });
          onUploaded?.(document);
          // The row now lives in the document table with a live status, so the
          // queue entry has done its job.
          setTimeout(
            () => setQueue((prev) => prev.filter((item) => item.name !== file.name)),
            1500
          );
        } catch (error) {
          update({ state: "failed", error: error.message });
          onError?.(`${file.name}: ${error.message}`);
        }
      }
    },
    [onUploaded, onError]
  );

  const onDrop = (event) => {
    event.preventDefault();
    setDragging(false);
    startUpload(event.dataTransfer.files);
  };

  return (
    <div className="flex flex-col gap-3">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={`flex flex-col items-center justify-center gap-3 rounded-none border-2 border-dashed px-6 py-10 transition ${
          dragging ? "border-emerald-600 bg-emerald-50" : "border-hairline bg-slate-50"
        }`}
      >
        <div className="flex h-11 w-11 items-center justify-center rounded-none border border-hairline bg-white">
          <FileUp size={20} strokeWidth={1.8} className="text-slate-600" />
        </div>
        <div className="text-center">
          <div className="text-[14.5px] font-semibold text-ink">
            Drop runbooks here, or choose files
          </div>
          <p className="mt-1 text-[12.5px] text-slate-500">
            PDF, Word and Markdown. Diagrams and screenshots are read automatically and
            indexed alongside the steps they illustrate.
          </p>
        </div>
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          className="flex items-center gap-2 rounded-none bg-emerald-600 px-4 py-2.5 text-[13px] font-semibold text-white transition hover:bg-emerald-700"
        >
          <Upload size={15} />
          Choose files
        </button>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept={accepted}
          onChange={(e) => {
            startUpload(e.target.files);
            e.target.value = "";
          }}
          className="hidden"
        />
      </div>

      {queue.length > 0 && (
        <div className="flex flex-col gap-px rounded-none border border-hairline bg-hairline">
          {queue.map((item) => (
            <div key={item.name} className="flex items-center gap-3 bg-white px-4 py-3">
              <span className="min-w-0 flex-1 truncate text-[13px] text-ink">{item.name}</span>
              {item.state === "failed" ? (
                <span className="flex items-center gap-2 text-[12.5px] text-amber-700">
                  <AlertTriangle size={14} />
                  {item.error}
                </span>
              ) : (
                <>
                  <div className="h-1.5 w-36 rounded-none bg-slate-100">
                    <div
                      className="h-1.5 rounded-none bg-emerald-600 transition-all"
                      style={{ width: `${item.progress}%` }}
                    />
                  </div>
                  <span className="w-10 text-right font-mono text-[11.5px] text-slate-500">
                    {item.progress}%
                  </span>
                </>
              )}
              {item.state === "failed" && (
                <button
                  type="button"
                  onClick={() =>
                    setQueue((prev) => prev.filter((entry) => entry.name !== item.name))
                  }
                  className="rounded-none p-0.5 text-slate-400 hover:text-ink"
                  aria-label="Dismiss"
                >
                  <X size={14} />
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
