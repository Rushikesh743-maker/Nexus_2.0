"""Data-model tests on an in-memory SQLite database.

These verify the ORM layer itself — creation, relationships, cascade
deletes, JSON columns — independent of the live PostgreSQL instance.
"""

import os
import sys

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import uuid

from app.core.database import Base  # noqa: E402
from app.models import (Case, Contradiction, Document, Entity, Evidence,  # noqa: E402
                        Hypothesis, InvestigationGap, Location,
                        Relationship, Simulation, TimelineEvent, User)


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    with Session() as session:
        yield session


def test_user_supabase_id_identity(db):
    sub_id = uuid.uuid4()
    user = User(email="investigator@unit.gov.in", name="R. Patil",
                role="INVESTIGATOR", officer_id="IND-4421", supabase_id=sub_id)
    db.add(user)
    db.commit()

    saved = db.scalars(select(User).where(User.supabase_id == sub_id)).first()
    assert saved is not None
    assert saved.email == "investigator@unit.gov.in"
    assert saved.role == "INVESTIGATOR"
    assert saved.supabase_id == sub_id
    assert saved.is_active is True


def test_full_case_graph_creates_and_relates(db):
    user_id = uuid.uuid4()
    user = User(email="t@example.org", name="Test", role="ANALYST",
                supabase_id=user_id)
    case = Case(case_number="TST-2026-001", title="Model test",
                description="d", status="OPEN", priority="LOW", created_by=None)
    db.add_all([user, case])
    db.flush()

    a = Entity(case_id=case.id, entity_type="person", canonical_name="A")
    b = Entity(case_id=case.id, entity_type="vehicle", canonical_name="V")
    loc = Location(case_id=case.id, name="Place", latitude=18.5, longitude=73.8,
                   metadata={"synthetic": True})
    doc = Document(case_id=case.id, filename="f.txt", file_type="text",
                   language="en", file_size=10, processing_status="PROCESSED")
    db.add_all([a, b, loc, doc])
    db.flush()

    ev = Evidence(case_id=case.id, document_id=doc.id, evidence_type="fir",
                  description="d", source_reference="FIR-1", confidence=0.9)
    db.add(ev)
    db.flush()
    rel = Relationship(case_id=case.id, source_entity_id=a.id,
                       target_entity_id=b.id, relationship_type="OWNS",
                       confidence=0.8, meta={"evidence": ["FIR-1"]})
    event = TimelineEvent(case_id=case.id, entity_id=a.id, event_type="sighting",
                          description="seen", location_id=loc.id, evidence_id=ev.id)
    db.add_all([rel, event])
    db.flush()

    db.add(Hypothesis(case_id=case.id, title="h", score=0.5, status="OPEN"))
    db.add(Contradiction(case_id=case.id, title="c", severity="HIGH", status="OPEN"))
    db.add(InvestigationGap(case_id=case.id, title="g", priority="MEDIUM",
                            status="OPEN"))
    db.add(Simulation(case_id=case.id, name="s", created_by=user.id))
    db.commit()

    assert case.entities and len(case.entities) == 2
    assert rel.source.canonical_name == "A" and rel.target.canonical_name == "V"
    assert event.location.name == "Place"
    assert event.evidence.source_reference == "FIR-1"
    assert case.creator is None and user.created_cases == []
    assert case.simulations[0].creator is user


def test_cascade_delete_removes_case_children(db):
    case = Case(case_number="TST-2026-002", title="cascade")
    db.add(case)
    db.flush()
    a = Entity(case_id=case.id, entity_type="person", canonical_name="X")
    doc = Document(case_id=case.id, filename="x.txt", file_type="text")
    db.add_all([a, doc])
    db.flush()
    db.add(Evidence(case_id=case.id, evidence_type="note", source_reference="E1"))
    db.commit()

    db.delete(case)
    db.commit()
    assert len(db.scalars(select(Entity)).all()) == 0
    assert len(db.scalars(select(Document)).all()) == 0
    assert len(db.scalars(select(Evidence)).all()) == 0


def test_json_metadata_roundtrip(db):
    case = Case(case_number="TST-2026-003", title="json")
    db.add(case)
    db.flush()
    e = Entity(case_id=case.id, entity_type="person", canonical_name="J",
               meta={"aliases": ["J. Junior"], "phones": ["9000000001"]})
    db.add(e)
    db.commit()
    fresh = db.get(Entity, e.id)
    assert fresh.meta["aliases"] == ["J. Junior"]
    # the database column keeps the spec name
    assert "metadata" in Entity.__table__.columns
