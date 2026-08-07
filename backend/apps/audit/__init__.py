"""Append-only platform event log (D-114).

Phase 4 delivered AuditEvent, the record() helper and RLS policies. Vault
operations and key-pool cooldowns write here today.

Still to come in Phase 7: the System Logs live tail and 90-day retention.

Platform-scope events (tenant NULL) are written through the `admin` connection -
see the note in record() for why.
"""
