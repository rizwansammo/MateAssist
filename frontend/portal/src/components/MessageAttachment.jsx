import { useEffect, useState } from "react";
import { ImageOff } from "lucide-react";

import { chatApi } from "../lib/chat.js";

/**
 * The screenshot a user attached, shown in their own bubble.
 *
 * Two sources, deliberately in this order:
 *
 *  1. `previewUrl` - a local object URL created at send time. It renders with
 *     no network round trip, so the picture is on screen the moment the message
 *     is. Waiting for the server put the image on screen AFTER the answer,
 *     which read as the upload having failed.
 *
 *  2. `has_attachment` - the persisted copy, fetched through an authorised
 *     endpoint. This is what makes the screenshot still be there tomorrow, and
 *     what takes over once the optimistic message is replaced by the real one.
 *
 * What is deliberately absent is the vision engine's transcription. It is still
 * generated and still stored, because it is the only thing the text engine ever
 * sees (D-042) - but the user already knows what they sent, and showing them a
 * paragraph of machine-read text instead of their own picture exposed our
 * plumbing as though it were the point.
 */
export function MessageAttachment({ message, conversationId }) {
  const [fetchedUrl, setFetchedUrl] = useState(null);
  const [failed, setFailed] = useState(false);

  const needsFetch = !message.previewUrl && message.has_attachment && conversationId;

  useEffect(() => {
    if (!needsFetch) return undefined;

    let url = null;
    let live = true;

    chatApi
      .attachmentUrl(conversationId, message.id)
      .then((objectUrl) => {
        url = objectUrl;
        // Unmounted mid-flight: revoke rather than set state on a dead
        // component, or the blob is stranded for the life of the tab.
        if (live) setFetchedUrl(objectUrl);
        else URL.revokeObjectURL(objectUrl);
      })
      .catch(() => {
        if (live) setFailed(true);
      });

    return () => {
      live = false;
      if (url) URL.revokeObjectURL(url);
    };
  }, [needsFetch, conversationId, message.id]);

  const src = message.previewUrl ?? fetchedUrl;

  if (!src) {
    if (failed) {
      return (
        <div className="mt-3 flex items-center gap-2 border border-slate-700 bg-ink2 px-3 py-2.5 text-[12px] text-slate-400">
          <ImageOff size={14} strokeWidth={1.8} />
          That screenshot is no longer available.
        </div>
      );
    }
    // A skeleton only while a stored image is genuinely on its way. A message
    // with no attachment must render nothing at all.
    if (needsFetch) {
      return <div className="mt-3 h-[120px] w-[200px] animate-pulse border border-slate-700 bg-ink2" />;
    }
    return null;
  }

  return (
    <div className="mt-3 overflow-hidden border border-slate-700">
      <img
        src={src}
        alt="Screenshot attached to this message"
        // Capped so a full-desktop screenshot cannot push the conversation off
        // the page, but still large enough to read an error dialog in.
        className="block max-h-[320px] w-auto max-w-full object-contain"
      />
    </div>
  );
}
