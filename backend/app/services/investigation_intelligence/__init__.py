"""Stage 4 — Investigation Reasoning & Evidence Intelligence.

Layering: API router (cases/investigation) -> service (this package) ->
pure engines (confirmed data records) -> PostgreSQL. All engines run on
confirmed entities/relationships/evidence/timeline events/locations
only; candidate, pending and rejected records never enter analysis.
"""
