"""Trusted PostgreSQL-only metadata gateway internals.

This package is deployed separately from the AI-facing stdio adapter. It owns
strict central configuration loading, request authorization, the password file,
the PostgreSQL driver, and the three fixed catalog operations.
"""
