"""Stage 4 smoke-verification seed (idempotent, additive, INSERT-only).

Creates two labeled SYNTHETIC DEMONSTRATION cases for the stage-4
acceptance smoke tests. Fictional names only (the spec's demonstration
vocabulary); no real people, no real databases. Re-running is a no-op
(case_number is unique; the script checks before inserting).

* CASE-DEMO-EMPTY-01 — an empty case: no confirmed graph data, so the
  stage-4 analysis must report INSUFFICIENT_CONFIRMED_DATA (409) and the
  UI must show the explicit insufficient state.
* CASE-DEMO-CONTRA-01 — contains documented, deterministic contradictions:
    R1  Aarav Deshmukh: Pune Central 09:00 -> CSMT Mumbai 09:20
        (~146 km, minimum travel ~88 min at the documented 100 km/h)
        -> TIMELINE_CONTRADICTION
    R2  Rohan Patil: Pune Industrial Area and Pune Central at the
        identical timestamp 14:00 -> LOCATION_CONTRADICTION
    R3  Vikram Rao OWNS MH12AB9999 and MH12AB9999 OWNS Vikram Rao
        -> RELATIONSHIP_CONTRADICTION
  plus events/locations/relationships that exercise timeline, geospatial,
  gap and hypothesis engines.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import select  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
from app.models import (Case, Entity, Evidence, Location, Relationship,
                        TimelineEvent)  # noqa: E402

META = {"synthetic": True, "demonstration": "stage4-smoke"}
LABEL = "SYNTHETIC DEMONSTRATION DATA — fictional records for smoke testing"


def _exists(db, case_number: str) -> bool:
    return db.execute(
        select(Case.id).where(Case.case_number == case_number)
    ).first() is not None


def seed_empty_case(db) -> str:
    if _exists(db, "CASE-DEMO-EMPTY-01"):
        return "exists"
    case = Case(
        case_number="CASE-DEMO-EMPTY-01",
        title=("Empty case — insufficient-data demonstration "
               "(SYNTHETIC DEMONSTRATION DATA)"),
        description=LABEL,
        status="OPEN", priority="LOW", is_synthetic=True)
    db.add(case)
    db.commit()
    return f"created case {case.id}"


def seed_contradiction_case(db) -> str:
    if _exists(db, "CASE-DEMO-CONTRA-01"):
        return "exists"
    case = Case(
        case_number="CASE-DEMO-CONTRA-01",
        title=("Contradiction demonstration case "
               "(SYNTHETIC DEMONSTRATION DATA)"),
        description=(LABEL + ". Deliberate, documented inconsistencies "
                     "(speed, identical-timestamp locations, mutual "
                     "ownership) exist so the stage-4 engines have "
                     "something deterministic to detect."),
        status="OPEN", priority="MEDIUM", is_synthetic=True)
    db.add(case)
    db.flush()

    loc_pune_central = Location(case_id=case.id,
                                name="Pune Central Station (demo)",
                                latitude=18.5286, longitude=73.8744,
                                meta=META)
    loc_csmt = Location(case_id=case.id,
                        name="CSMT Mumbai (demo)",
                        latitude=18.9396, longitude=72.8353, meta=META)
    loc_industrial = Location(case_id=case.id,
                              name="Pune Industrial Area (demo)",
                              latitude=18.5823, longitude=73.8341,
                              meta=META)
    db.add_all([loc_pune_central, loc_csmt, loc_industrial])
    db.flush()

    aarav = Entity(case_id=case.id, entity_type="person",
                   canonical_name="Aarav Deshmukh", meta=META)
    rohan = Entity(case_id=case.id, entity_type="person",
                   canonical_name="Rohan Patil", meta=META)
    vikram = Entity(case_id=case.id, entity_type="person",
                    canonical_name="Vikram Rao", meta=META)
    neha = Entity(case_id=case.id, entity_type="person",
                  canonical_name="Neha Kulkarni", meta=META)
    vehicle = Entity(case_id=case.id, entity_type="vehicle",
                     canonical_name="MH12AB9999", meta=META)
    db.add_all([aarav, rohan, vikram, neha, vehicle])
    db.flush()

    ev1 = Evidence(case_id=case.id, evidence_type="document",
                   description="Arrival record (demo, synthetic)",
                   source_reference="demo:stage4-synthetic-1",
                   confidence=0.9)
    ev2 = Evidence(case_id=case.id, evidence_type="document",
                   description="Departure record (demo, synthetic)",
                   source_reference="demo:stage4-synthetic-2",
                   confidence=0.9)
    ev3 = Evidence(case_id=case.id, evidence_type="observation",
                   description="Field sighting record (demo, synthetic)",
                   source_reference="demo:stage4-synthetic-3",
                   confidence=0.7)
    ev4 = Evidence(case_id=case.id, evidence_type="observation",
                   description="Second field sighting (demo, synthetic)",
                   source_reference="demo:stage4-synthetic-4",
                   confidence=0.7)
    db.add_all([ev1, ev2, ev3, ev4])
    db.flush()

    t = "2026-06-10"
    events = [
        # R1: speed violation (20 min for ~146 km)
        TimelineEvent(case_id=case.id, entity_id=aarav.id,
                      event_type="arrival_recorded",
                      timestamp=datetime.fromisoformat(t + "T09:00:00"),
                      location_id=loc_pune_central.id,
                      description="Aarav Deshmukh recorded at Pune Central (demo)",
                      evidence_id=ev1.id),
        TimelineEvent(case_id=case.id, entity_id=aarav.id,
                      event_type="departure_recorded",
                      timestamp=datetime.fromisoformat(t + "T09:20:00"),
                      location_id=loc_csmt.id,
                      description="Aarav Deshmukh recorded at CSMT Mumbai (demo)",
                      evidence_id=ev2.id),
        # R2: identical timestamp, different locations
        TimelineEvent(case_id=case.id, entity_id=rohan.id,
                      event_type="sighting_recorded",
                      timestamp=datetime.fromisoformat(t + "T14:00:00"),
                      location_id=loc_industrial.id,
                      description="Rohan Patil sighted in Pune Industrial Area (demo)",
                      evidence_id=ev3.id),
        TimelineEvent(case_id=case.id, entity_id=rohan.id,
                      event_type="sighting_recorded",
                      timestamp=datetime.fromisoformat(t + "T14:00:00"),
                      location_id=loc_pune_central.id,
                      description="Rohan Patil sighted at Pune Central (demo)",
                      evidence_id=ev4.id),
        TimelineEvent(case_id=case.id, entity_id=neha.id,
                      event_type="arrival_recorded",
                      timestamp=datetime.fromisoformat(t + "T18:30:00"),
                      location_id=loc_pune_central.id,
                      description="Neha Kulkarni recorded at Pune Central (demo)",
                      evidence_id=ev3.id),
    ]
    db.add_all(events)
    db.flush()

    rels = [
        # R3: mutual OWNS
        Relationship(case_id=case.id, source_entity_id=vikram.id,
                     target_entity_id=vehicle.id,
                     relationship_type="OWNS", confidence=0.8, meta=META),
        Relationship(case_id=case.id, source_entity_id=vehicle.id,
                     target_entity_id=vikram.id,
                     relationship_type="OWNS", confidence=0.8, meta=META),
        Relationship(case_id=case.id, source_entity_id=aarav.id,
                     target_entity_id=rohan.id,
                     relationship_type="COMMUNICATED_WITH", confidence=0.6,
                     meta=META),
        Relationship(case_id=case.id, source_entity_id=neha.id,
                     target_entity_id=aarav.id,
                     relationship_type="ASSOCIATED_WITH", confidence=0.5,
                     meta=META),
        Relationship(case_id=case.id, source_entity_id=vikram.id,
                     target_entity_id=aarav.id,
                     relationship_type="ASSOCIATED_WITH", confidence=0.5,
                     meta=META),
    ]
    db.add_all(rels)
    db.commit()
    return f"created case {case.id}"


def main() -> None:
    db = SessionLocal()
    try:
        print("empty case:", seed_empty_case(db))
        print("contradiction case:", seed_contradiction_case(db))
    finally:
        db.close()


if __name__ == "__main__":
    main()
