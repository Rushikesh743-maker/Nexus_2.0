"""Case data access.

Everything the case API needs lives here so the router and service layers
stay thin: list/detail with aggregate counts, sub-resource reads, the
cross-case entity check, and case creation.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..models import (Case, Contradiction, Document, Entity, Evidence,
                      Hypothesis, InvestigationGap, Location, Relationship,
                      Simulation, TimelineEvent, User)  # noqa: F401


_CASE_OPTIONS = [
    selectinload(Case.documents), selectinload(Case.entities),
    selectinload(Case.relationships_), selectinload(Case.evidence),
    selectinload(Case.evidence).selectinload(Evidence.document),
    selectinload(Case.timeline_events), selectinload(Case.locations),
    selectinload(Case.hypotheses), selectinload(Case.contradictions),
    selectinload(Case.gaps), selectinload(Case.simulations),
]


def list_cases(db: Session) -> list[Case]:
    q = (select(Case).options(*_CASE_OPTIONS)
         .order_by(Case.updated_at.desc(), Case.id.desc()))
    return list(db.scalars(q).unique())


def get_case(db: Session, case_id: int) -> Case | None:
    q = (select(Case).where(Case.id == case_id).options(*_CASE_OPTIONS))
    return db.scalars(q).first()


def create_case(db: Session, *, case_number: str, title: str,
                description: str | None, status: str, priority: str,
                user: User | None) -> Case:
    case = Case(case_number=case_number.upper(), title=title, description=description,
                status=status, priority=priority, created_by=user.id if user else None)
    db.add(case)
    db.commit()
    db.refresh(case)
    return case


def counts_for(case: Case) -> dict[str, int]:
    return {
        "documents": len(case.documents),
        "entities": len(case.entities),
        "relationships": len(case.relationships_),
        "evidence": len(case.evidence),
        "timeline_events": len(case.timeline_events),
        "locations": len(case.locations),
        "hypotheses": len(case.hypotheses),
        "contradictions": len(case.contradictions),
        "gaps": len(case.gaps),
        "simulations": len(case.simulations),
    }


def latest_event_at(case: Case) -> datetime | None:
    stamps = [e.timestamp for e in case.timeline_events if e.timestamp]
    return max(stamps) if stamps else None


def cross_case_links(db: Session, case: Case,
                     allowed_ids: list[int] | None = None) -> list[dict]:
    """Other cases sharing an entity name (case-insensitive) with this one.

    A deliberately simple, explainable definition of "cross-case
    connection" for the foundation stage: same canonical name across cases.
    The later entity-resolution stage will replace this with identity
    matching, but it already answers the question on real data.
    """
    names = {e.canonical_name.strip().lower(): e.canonical_name
             for e in case.entities}
    if not names:
        return []

    other_cases = (
        db.scalars(select(Case)
                   .where(Case.id != case.id)
                   .options(selectinload(Case.entities)))
        .unique()
    )
    links: list[dict] = []
    for other in other_cases:
        if allowed_ids is not None and other.id not in allowed_ids:
            continue  # stage 7: never leak cases the caller cannot access
        shared = sorted(
            {e.canonical_name for e in other.entities
             if e.canonical_name.strip().lower() in names},
            key=str.lower,
        )
        if shared:
            links.append({"case_id": other.id, "case_number": other.case_number,
                          "title": other.title, "status": other.status,
                          "shared_entities": shared})
    links.sort(key=lambda l: (-len(l["shared_entities"]), l["case_number"]))
    return links


# ------------------------------------------------------------ sub-resources

def documents(db: Session, case: Case) -> list[Document]:
    return sorted(case.documents, key=lambda d: d.uploaded_at)


def entities(db: Session, case: Case) -> list[Entity]:
    return sorted(case.entities, key=lambda e: (e.entity_type, e.canonical_name.lower()))


def entity_degrees(case: Case) -> dict[int, int]:
    """Link count per entity, from the case's already-loaded relationships."""
    degrees: dict[int, int] = {}
    for r in case.relationships_:
        degrees[r.source_entity_id] = degrees.get(r.source_entity_id, 0) + 1
        degrees[r.target_entity_id] = degrees.get(r.target_entity_id, 0) + 1
    return degrees


def relationships(db: Session, case: Case) -> list[Relationship]:
    labels = {e.id: e.canonical_name for e in case.entities}
    for r in case.relationships_:
        r.source_label = labels.get(r.source_entity_id, "")
        r.target_label = labels.get(r.target_entity_id, "")
    return sorted(case.relationships_, key=lambda r: (r.relationship_type, r.id))


def evidence(db: Session, case: Case) -> list[Evidence]:
    return sorted(case.evidence, key=lambda e: e.id)


def timeline_events(db: Session, case: Case) -> list[TimelineEvent]:
    return sorted(case.timeline_events,
                  key=lambda e: (e.timestamp is None, e.timestamp or datetime.min, e.id))


def locations(db: Session, case: Case) -> list[Location]:
    return sorted(case.locations, key=lambda l: l.name.lower())


def hypotheses(db: Session, case: Case) -> list[Hypothesis]:
    return sorted(case.hypotheses, key=lambda h: (-(h.score or 0), h.id))


def contradictions(db: Session, case: Case) -> list[Contradiction]:
    return sorted(case.contradictions, key=lambda c: c.id)


def gaps(db: Session, case: Case) -> list[InvestigationGap]:
    return sorted(case.gaps, key=lambda g: g.id)


def simulations(db: Session, case: Case) -> list[Simulation]:
    return sorted(case.simulations, key=lambda s: s.id)


def create_simulation(db: Session, case: Case, *, name: str,
                      description: str | None, user: User | None) -> Simulation:
    sim = Simulation(case_id=case.id, name=name, description=description,
                     created_by=user.id if user else None)
    db.add(sim)
    db.commit()
    db.refresh(sim)
    return sim
