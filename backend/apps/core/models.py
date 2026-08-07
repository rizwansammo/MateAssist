"""Core has no models.

It exists as an app so that infrastructure-level migrations (enabling pgvector,
and in Phase 2 the RLS policy DDL) have a home that is not owned by any single
bounded context.
"""
