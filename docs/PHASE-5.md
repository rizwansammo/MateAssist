# Phase 5 — Document Ingestion & Vector Index

**Status: COMPLETE.** A real PDF containing a diagram goes in; retrievable,
tenant-isolated vectors come out.

---

## 1. The gate

```
python manage.py ingest_demo --tenant netswitch

  Built a 334,087-byte PDF: prose + one embedded figure
  Running the pipeline (parse -> Gemini -> splice -> chunk -> embed)...

  status=INDEXED
  pages=1  images=1  described=1  chunks=1

  Figure at block 1 (420x260, DESCRIBED)
    The image depicts an abstract wireframe or schematic representation of a
    modal dialog window or user interface panel. It features a dark navy blue
    header bar along the top and a light blue-gray main content area...

  D-054 VERIFIED: the figure description is inside chunk 0, alongside the
  procedure text.
```

Gemini genuinely read a synthetic dialog screenshot and described it correctly.

Then, proving the vectors are real rather than merely stored:

```
query embedded: 384 dims

as netswitch, on-topic  ("Why does the VPN disconnect...")   sim=0.6753
as netswitch, off-topic ("How do I reset a printer toner...") sim=0.5158
as apptriangle          (same question)                       0 rows

PASS  retrieved with similarity 0.6753
PASS  on-topic scores higher than off-topic - embeddings are meaningful
PASS  cross-tenant retrieval returned nothing (RLS holds on vectors)
      chunks visible with no tenant context: 0 (fail closed)
```

**95 tests pass** (80 → 95), ruff and black clean, no missing migrations, both
frontend bundles build, D-100 lint clean.

---

## 2. What was built

| Component | File | Note |
|---|---|---|
| Schema | `models.py` | `Category`, `Document`, `DocumentAsset`, `DocumentChunk`; RLS on all four; HNSW at `m=16, ef_construction=64` |
| Block stream | `parsers/base.py` | Ordered blocks with images at their real positions |
| PDF | `parsers/pdf.py` | PyMuPDF; scanned pages rasterised for OCR |
| DOCX | `parsers/docx.py` | Walks the XML body in order, not `paragraphs` |
| Markdown | `parsers/markdown.py` | Heading breadcrumbs, fences kept whole, **remote images never fetched** |
| Splice + chunk | `chunking.py` | D-054 and D-055 |
| Embeddings | `embeddings.py` | Local `bge-small-en-v1.5`, 384-dim (D-060) |
| Pipeline | `tasks.py` | Celery, tenant context armed first |
| Storage | `storage.py` | MinIO/S3, random keys |
| API | `views.py` | Upload / list / reindex / chunks / assets, TENANT_ADMIN-gated |

## 3. The decisions that shaped it

**Image position is everything (D-054).** A Gemini description is not stored as
its own searchable object — it is substituted for the image *at the image's own
index in the block stream*, before chunking. The consequence is that a diagram's
description lands in the same chunk as the procedure referencing it. Index
descriptions separately and you get orphans: a chunk reading *"the dialog shows
Advanced Settings"* retrieves alone, with nothing to say which product or which
step it belongs to. That looks like it works right up until someone asks a
question.

**An undescribed image is dropped, not placeholdered.** `[image]` is noise that
dilutes the embedding of whatever chunk it lands in, making the surrounding text
*harder* to retrieve.

**Heading breadcrumbs are embedded with the text.** A chunk saying *"restart the
print spooler"* is far more retrievable carrying *"Printers > HP LaserJet M479"*
with it.

**Scanned pages are rasterised.** A PDF page with no text layer is sent to Gemini
whole. Without this, scanned runbooks — common in IT departments — would ingest
as empty documents and silently answer nothing.

**Content is sniffed, not trusted.** Upload checks magic bytes, so a payload
renamed to `.pdf` is rejected before any parser sees it (D-131).

**Markdown never fetches a remote image.** Following a URL out of a
tenant-uploaded document would turn ingestion into an SSRF primitive aimed at
whatever the worker can reach, including cloud metadata endpoints. Local paths
are containment-checked against the document root.

**Images are deduplicated by content hash.** At ~1,100 tokens per image (measured
in A-009), a logo repeating on 200 pages would cost 220k tokens to describe the
same picture 200 times.

**Ingestion is one task, not a chord.** The fan-out shape suggests parallel image
calls, but the Gemini free tier rate-limits hard enough that concurrency makes it
slower — every parallel call past the limit becomes a 429, a key cooldown and a
retry.

## 4. Found by running it

**RLS caught the gate itself.** `ingest_demo` failed with *"new row violates
row-level security policy"*. The cause was mine: `set_config(..., is_local =>
true)` is scoped to the current transaction, and a management command runs in
autocommit — so the tenant id was discarded before the INSERT. The request
middleware wraps every request for exactly this reason; the command didn't.
Fixed with an explicit `transaction.atomic()`.

This is the fourth time in this project that RLS has converted a silent
mis-scoping into a loud failure.

## 5. Honest limitations

- **The gate document produced one chunk.** At 437 tokens it is under the 512
  target, so splicing and chunking are proven, but multi-chunk behaviour at the
  boundary is covered by unit tests rather than the live run. A larger real
  runbook would exercise it better.
- **DOCX and Markdown parsers have no live end-to-end run.** Their logic is unit
  tested and the shared splice/chunk path is proven by the PDF run, but neither
  has been through the full pipeline against a real file.
- **The tenant-admin upload UI is not built.** The API is complete and tested;
  the Knowledge Base screen still reads `seed/knowledge.js`. That is the one
  piece of D-090 outstanding.
- **Only one Gemini key is configured**, so the pool has nothing to fail over to
  when the free tier rate-limits. Recommend adding 2–3.

## 6. Next — Phase 6

Agentic RAG chat: hybrid retrieval (pgvector ∥ FTS, fused by RRF), DeepSeek
streaming over SSE, citations resolving to these documents, screenshot upload
through the same `call_vision` path, and the `escalate_via_email` handoff
(A-008).

**Needs a DeepSeek API key to close** — the text engine has still never made a
live call.
