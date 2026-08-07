"""Core - cross-cutting infrastructure.

Owns the health endpoint and the database-level migrations that are not specific
to any bounded context, such as enabling pgvector (D-015).
"""
