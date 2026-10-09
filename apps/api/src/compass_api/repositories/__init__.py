"""Database access.

Repositories own SQL. They take and return typed values, never HTTP or provider
objects, and they never contain financial rules - those belong in services (ADR-0004).
"""
