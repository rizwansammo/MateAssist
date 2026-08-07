# Phase 4 — Credential Vault & Engine Contracts

**Status: COMPLETE**, with one item that cannot close without your API keys (§6).

Phase 3 was skipped under **A-008**; ticketing is replaced by an SMTP handoff in Phase 6.

---

## 1. What was built

| Area | Detail |
|---|---|
| Vault | AES-256-GCM **envelope** encryption — per-secret data key, wrapped by the KEK |
| Models | `ProviderKey`, `ModelPrice`, `UsageEvent`, `AuditEvent` |
| Engines | `TextEngine` (DeepSeek) and `VisionEngine` (Gemini) |
| Router | Key pool: LRU round-robin, `FOR UPDATE SKIP LOCKED`, 429 cooldown, failover |
| API | Platform-owner-only vault surface with create / rotate / revoke / purge / pool status |
| RLS | `metering_usageevent` and `audit_auditevent` now policy-protected |
| Frontend | AI Configuration reads and writes the **live** vault; `SEED_KEYS` deleted |

**71 backend tests pass.** `check` clean, `makemigrations --check` clean, both bundles build,
D-100 lint clean.

---

## 2. The engine contract is enforced, not documented

`apps/ai/tests/test_engine_contract.py` — 14 tests attacking the claim from every angle a real
bug would take:

- `TextMessage` has exactly four fields and `content` is typed `str`. There is no shape it can
  take that carries an image.
- `complete()` and `stream()` are asserted to have **no** `image`/`parts`/`attachments`
  parameter, so the contract cannot erode through a well-meaning signature change.
- The runtime guard rejects raw bytes, OpenAI-style parts lists, `data:image/...` URIs inside
  strings, and the `image_url` / `inline_data` / `b64_json` field names.
- It runs **before any client is constructed**, so a misuse cannot leak an image even with a
  valid key and a live network.
- Every message is checked, not just the first.
- The happy path is asserted too: Gemini's *description* passing through to DeepSeek is exactly
  what should work.

No network and no API key is needed to run these — itself part of the design.

## 3. The vault has no read path

D-072 says write-only is the absence of a code path, not a flag. Verified three ways:

1. A test asserts `ProviderKeySerializer` exposes no `ciphertext`/`secret`/`api_key` field — it
   fails the build if one ever appears.
2. Live: creating a key returned no plaintext and no `ciphertext` field; the listing has neither.
3. On disk: `SELECT ciphertext FROM ai_providerkey` returns base64 AEAD output, and a
   `LIKE '%<the secret>%'` scan across the table returns **0 rows**.

AAD binds each ciphertext to its own row, so a blob copied between keys fails to open rather
than silently decrypting as another engine's credential. Rotating `MATEASSIST_VAULT_KEY`
orphans every stored secret — there is a test that documents exactly that.

## 4. Metering is an invariant

Every provider call goes through `call_text` / `call_vision`; there is no second route to an
engine. Each writes a `UsageEvent` with cost computed from a `ModelPrice` **row**, never a
constant. An unpriced model yields zero rather than raising — failing a user's chat because an
admin has not entered a rate would be the wrong trade, and the zero is visible in the dashboard
as a missing price.

## 5. Found by running it

**RLS caught a real design gap.** `cool_down()` writes a *platform-scope* audit event
(`tenant NULL`) — but a Gemini key hits its quota during *a tenant's* upload, when tenant
context is active, and `WITH CHECK` correctly refused the row.

The honest fix was to route platform-scope audit writes to the platform (`admin`) connection,
not to weaken the policy so null-tenant rows slip through during tenant requests. Phase 2's
isolation work paid for itself here: without `WITH CHECK` this would have been a silent
mis-scoping instead of a loud failure.

---

## 6. Blocked on you — open item O-3

The **model-ID verification gate** from DECISIONS.md §5 still has not run. `deepseek-chat`,
`deepseek-reasoner` and `gemini-2.5-flash` are pinned **from documentation, never probed**.

Add real credentials through the admin UI (AI Configuration → Add key) — not to `.env`; the
vault is the only place they belong. Then the gate can run and Phases 5 and 6 become provable
rather than merely built.

## 7. Next — Phase 5

Document ingestion: upload → parse (PyMuPDF / python-docx / markdown) → **Gemini describes each
image** → splice descriptions back at their original position → chunk → embed → pgvector + HNSW.

`call_vision` is already the only path to Gemini and is already metered, so Phase 5 inherits
cost control and the audit trail for free.
