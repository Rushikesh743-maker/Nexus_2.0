"""Multilingual, case-scoped search over CONFIRMED records only.

Used by both the platform search endpoint (``GET /cases/{id}/search``) and
the copilot's search intent. The query is normalized with the stage-5
normalizer (script-insensitive: Devanagari / Perso-Arabic are transliterated
before comparison), so a single query can match ``Rajesh Kumar``,
``राजेश कुमार`` and ``راجش کمار``.

Only substring matching on confirmed fields — no free-text guessing, no
similarity over unconfirmed data. Every hit names the field that matched
and carries a short snippet.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict

from .context import CaseContext, _norm

MAX_HITS = 50


@dataclass
class SearchHit:
    kind: str          # entity|relationship|evidence|event|location|claim
    id: int
    label: str
    field: str
    snippet: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def search_case(ctx: CaseContext, query: str, k: int = MAX_HITS) -> dict:
    """Return ``{query, hits, counts}`` for a multilingual search."""
    q = (query or "").strip()
    out: dict = {"query": q, "hits": [], "counts": {}}
    if not q:
        return out
    qn = _norm(q)
    if not qn:
        return out
    hits: list[SearchHit] = []

    def add(kind, rid, label, fld, snippet):
        if len(hits) < k:
            hits.append(SearchHit(kind, rid, label, fld, snippet))

    for e in ctx.data.entities:
        forms = [e.canonical_name] + (
            ctx.data.entity_metadata.get(e.id, {}).get("aliases") or [])
        for form in forms:
            if qn in _norm(form):
                add("entity", e.id, e.canonical_name, "name", form)
                break
    for r in ctx.data.relationships:
        if qn in _norm(r.relationship_type):
            add("relationship", r.id, r.relationship_type, "type",
                f"{ctx.name_of(r.source_entity_id)} → "
                f"{ctx.name_of(r.target_entity_id)}")
    for v in ctx.data.evidence:
        if qn in _norm(v.evidence_type) or (
                v.source_reference and qn in _norm(v.source_reference)):
            add("evidence", v.id, f"E{v.id} ({v.evidence_type})",
                "type/source", v.source_reference or v.evidence_type)
    for e in ctx.data.events:
        hay = " ".join(x for x in (e.event_type, e.description or "") if x)
        if qn in _norm(hay):
            add("event", e.id,
                f"{e.event_type} @ {ctx.name_of(e.entity_id)}", "event",
                (e.description or e.event_type)[:80])
    for l in ctx.data.locations:
        if qn in _norm(l.name):
            add("location", l.id, l.name, "name", l.name)
    for c in ctx.data.claims:
        if qn in _norm(c.object_value or "") or qn in _norm(c.predicate):
            add("claim", c.id,
                f"{ctx.name_of(c.subject_entity_id)} {c.predicate}", "claim",
                c.object_value or c.predicate)

    counts: dict[str, int] = {}
    for h in hits:
        counts[h.kind] = counts.get(h.kind, 0) + 1
    out["hits"] = [h.to_dict() for h in hits]
    out["counts"] = counts
    out["total"] = len(hits)
    return out
