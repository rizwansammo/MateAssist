"""Accounts - email-identified User and authentication.

The User model lands in Phase 1 rather than Phase 2 because AUTH_USER_MODEL is
frozen by the first migration. JWT issuance, roles and tenant membership follow
in Phase 2.
"""
