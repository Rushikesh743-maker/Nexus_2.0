"""Stage 5 — structured claims: the R4 evidence-contradiction engine and
end-to-end claim materialization (candidate acceptance → evidence_claim).

All sample texts are SYNTHETIC DEMONSTRATION DATA (fictional stage-5
entity set). The E2E part runs the real pipeline: create a scratch case,
upload Marathi + Hindi documents, accept every candidate/match, verify
confirmed evidence_claim rows, then run the investigation analysis and
verify the EVIDENCE_CONTRADICTION finding.
"""

import datetime as dt
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.database import SessionLocal  # noqa: E402
from app.models import Case, EvidenceClaim  # noqa: E402
from app.services.graph_intelligence.graph_builder import EntityRecord  # noqa: E402
from app.services.investigation_intelligence.claim_contradictions import (  # noqa: E402
    detect_claim_contradictions)
from app.services.investigation_intelligence.data import (  # noqa: E402
    ClaimRecord, LocationRecord, Stage4Data, load_stage4_data)
from sqlalchemy import select  # noqa: E402

RUN = time.strftime("%Y%m%d-%H%M%S")
TS = dt.datetime(2026, 8, 14, 21, 10, tzinfo=dt.timezone.utc)


# ================================================================ R4 engine
def _ctx(claims, locations=None, entities=None):
    d = Stage4Data(case_id=999)
    d.entities = entities or [EntityRecord(1, 999, "person", "Rajesh Kumar")]
    d.locations = locations or [
        LocationRecord(1, 999, "Pune", 18.52, 73.86),
        LocationRecord(2, 999, "Mumbai", 19.08, 72.88)]
    d.entities_by_id = {e.id: e for e in d.entities}
    d.claims = claims
    return d


class TestR4Engine:
    def test_spatial_contradiction_high(self):
        d = _ctx([
            ClaimRecord(1, 999, 101, 1, "was_at", None, "Pune", TS, 1, "pune"),
            ClaimRecord(2, 999, 102, 1, "was_at", None, "Mumbai",
                        TS + dt.timedelta(minutes=3), 2, "mumbai")])
        res, insuf = detect_claim_contradictions(d)
        assert len(res) == 1
        r = res[0]
        assert r.contradiction_type == "EVIDENCE_CONTRADICTION"
        assert r.severity == "HIGH"            # 3 min <= 5 min
        assert r.supporting_evidence_ids == [101, 102]
        assert r.details["rule"] == "R4"
        assert r.details["variant"] == "spatial"
        assert insuf == {"pairs_skipped_no_time": 0,
                         "pairs_skipped_no_location": 0}

    def test_medium_severity_over_5_min(self):
        d = _ctx([
            ClaimRecord(1, 999, 101, 1, "was_at", None, "Pune", TS, 1, "pune"),
            ClaimRecord(2, 999, 102, 1, "was_at", None, "Mumbai",
                        TS + dt.timedelta(minutes=10), 2, "mumbai")])
        res, _ = detect_claim_contradictions(d)
        assert len(res) == 1
        assert res[0].severity == "MEDIUM"     # 10 min > 5 min but <= 15

    def test_same_location_no_finding(self):
        d = _ctx([
            ClaimRecord(1, 999, 101, 1, "was_at", None, "Pune", TS, 1, "pune"),
            ClaimRecord(2, 999, 102, 1, "was_at", None, "Pune",
                        TS + dt.timedelta(minutes=2), 1, "pune")])
        res, insuf = detect_claim_contradictions(d)
        assert res == []
        assert insuf["pairs_skipped_no_location"] == 1

    def test_far_apart_in_time_no_finding(self):
        d = _ctx([
            ClaimRecord(1, 999, 101, 1, "was_at", None, "Pune", TS, 1, "pune"),
            ClaimRecord(2, 999, 102, 1, "was_at", None, "Mumbai",
                        TS + dt.timedelta(hours=1), 2, "mumbai")])
        res, _ = detect_claim_contradictions(d)
        assert res == []

    def test_different_subject_no_finding(self):
        d = _ctx(
            [ClaimRecord(1, 999, 101, 1, "was_at", None, "Pune", TS, 1, "pune"),
             ClaimRecord(2, 999, 102, 2, "was_at", None, "Mumbai", TS, 2,
                         "mumbai")],
            entities=[EntityRecord(1, 999, "person", "Rajesh Kumar"),
                      EntityRecord(2, 999, "person", "Vikram Rao")])
        res, _ = detect_claim_contradictions(d)
        assert res == []

    def test_missing_time_is_insufficient_not_finding(self):
        d = _ctx([
            ClaimRecord(1, 999, 101, 1, "was_at", None, "Pune", None, 1, "pune"),
            ClaimRecord(2, 999, 102, 1, "was_at", None, "Mumbai", TS, 2,
                        "mumbai")])
        res, insuf = detect_claim_contradictions(d)
        assert res == []
        assert insuf["pairs_skipped_no_time"] == 1

    def test_location_entity_fallback_no_location_rows(self):
        """Extracted locations are confirmed ENTITIES (no coordinates row) —
        the engine must still compare them via the confirmed entity."""
        d = Stage4Data(case_id=999)
        d.entities = [EntityRecord(1, 999, "person", "Rajesh Kumar"),
                      EntityRecord(2, 999, "location", "Pune"),
                      EntityRecord(3, 999, "location", "Mumbai")]
        d.entities_by_id = {e.id: e for e in d.entities}
        d.locations = []   # fresh case: no seeded location rows
        d.claims = [
            ClaimRecord(1, 999, 101, 1, "was_at", 2, "Pune", TS, None, "pune"),
            ClaimRecord(2, 999, 102, 1, "was_at", 3, "Mumbai",
                        TS + dt.timedelta(minutes=5), None, "mumbai")]
        res, insuf = detect_claim_contradictions(d)
        assert len(res) == 1, insuf
        assert res[0].severity == "HIGH"          # 5 min <= NEAR_MIN
        assert "Pune" in res[0].title and "Mumbai" in res[0].title
        assert res[0].details["locations"]["names"] == \
            {"a": "Pune", "b": "Mumbai"}
        assert res[0].details["distance_km"] is None  # no coordinates
        assert insuf == {"pairs_skipped_no_time": 0,
                         "pairs_skipped_no_location": 0}

    def test_value_variant(self):
        d = _ctx(
            [ClaimRecord(1, 999, 101, 1, "owns", 2, "9876543210", TS, None,
                         "9876543210"),
             ClaimRecord(2, 999, 102, 1, "owns", 3, "+91-12345",
                         TS + dt.timedelta(minutes=2), None, "+91-12345")],
            entities=[EntityRecord(1, 999, "person", "Rajesh Kumar"),
                      EntityRecord(2, 999, "phone", "9876543210"),
                      EntityRecord(3, 999, "phone", "+91-12345")])
        res, _ = detect_claim_contradictions(d)
        assert len(res) == 1
        assert res[0].details["variant"] == "value"
        assert res[0].details["predicate"] == "owns"

    def test_identical_value_no_finding(self):
        d = _ctx([
            ClaimRecord(1, 999, 101, 1, "owns", None, "9876543210", TS, None,
                        "9876543210"),
            ClaimRecord(2, 999, 102, 1, "owns", None, "9876543210",
                        TS + dt.timedelta(minutes=2), None, "9876543210")])
        res, _ = detect_claim_contradictions(d)
        assert res == []

    def test_neutral_language_in_explanation(self):
        d = _ctx([
            ClaimRecord(1, 999, 101, 1, "was_at", None, "Pune", TS, 1, "pune"),
            ClaimRecord(2, 999, 102, 1, "was_at", None, "Mumbai",
                        TS + dt.timedelta(minutes=1), 2, "mumbai")])
        res, _ = detect_claim_contradictions(d)
        joined = " ".join(res[0].explanation).lower()
        for banned in ("proves", "guilty", "false", "liar"):
            assert banned not in joined


# ====================================================== stage-4 data hookup
class TestStage4DataClaims:
    def test_version_hash_changes_with_claims(self):
        from app.services.investigation_intelligence.data import (
            compute_stage4_version)
        d0 = Stage4Data(case_id=7)
        d1 = Stage4Data(case_id=7)
        d1.claims = [ClaimRecord(1, 7, 10, 1, "was_at", None, "Pune", TS,
                                 1, "pune")]
        assert compute_stage4_version(d0) != compute_stage4_version(d1)

    def test_load_stage4_data_includes_claims(self):
        db = SessionLocal()
        try:
            data = load_stage4_data(db, 1)
            assert isinstance(data.claims, list)
        finally:
            db.close()


# ==================================================================== E2E
# `client` and `auth` come from conftest (Supabase tokens).


def _upload(client, headers, case_id, filename, text):
    r = client.post(f"/api/v1/cases/{case_id}/documents",
                    files={"file": (filename, text.encode(), "text/plain")},
                    headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _wait_processed(client, headers, doc_id, timeout=30):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        r = client.get(f"/api/v1/documents/{doc_id}/status", headers=headers)
        assert r.status_code == 200
        last = r.json()
        if last["processing_status"] in ("PROCESSED", "FAILED"):
            return last
        time.sleep(0.4)
    raise AssertionError(f"doc {doc_id} did not finish: {last}")


def _accept_all(client, headers, doc_id):
    """Accept every pending candidate: matches first (they fold a
    candidate into an existing entity), then entity candidates, then
    relationship candidates (which require confirmed endpoints)."""
    for _ in range(12):  # bounded convergence
        r = client.get(f"/api/v1/documents/{doc_id}/extraction",
                       headers=headers)
        assert r.status_code == 200, r.text
        ex = r.json()
        progressed = False
        for m in ex["matches"]:
            if m["status"] == "PENDING":
                ra = client.post(
                    f"/api/v1/documents/{doc_id}/extraction/matches/"
                    f"{m['id']}/accept", headers=headers)
                assert ra.status_code in (200, 201), ra.text
                progressed = True
        for c in ex["entities"]:
            if c["status"] != "PENDING":
                continue
            if c.get("match") and c["match"]["status"] == "PENDING":
                continue  # needs match resolution (handled above)
            ra = client.post(
                f"/api/v1/documents/{doc_id}/extraction/candidates/"
                f"{c['id']}/accept", headers=headers)
            assert ra.status_code in (200, 201), ra.text
            progressed = True
        for rel in ex["relationships"]:
            if rel["status"] != "PENDING":
                continue
            ra = client.post(
                f"/api/v1/documents/{doc_id}/extraction/relationships/"
                f"{rel['id']}/accept", headers=headers)
            # 409 is transient: an endpoint candidate may still be pending
            assert ra.status_code in (200, 201, 409), ra.text
            if ra.status_code in (200, 201):
                progressed = True
        if not progressed:
            return ex
    raise AssertionError("acceptance loop did not converge")


class TestClaimMaterializationE2E:
    """Two languages, same person, same time, two locations → the real
    pipeline must produce confirmed claims and an EVIDENCE_CONTRADICTION."""

    CASE_NUMBER = f"TEST-2026-{int(time.time()) % 1000000:06d}"
    # SYNTHETIC DEMONSTRATION DATA (fictional stage-5 names). The label
    # lives in the case description/title — appending Latin text to the
    # document body would pollute script detection, which is honest about
    # mixed-script input. A structured was_at claim is only produced for a
    # person resolvable via the alias registry, so the docs use the known
    # demo person (Rajesh Kumar) in Marathi + Hindi — same subject, 5 min
    # apart, two locations → R4 EVIDENCE_CONTRADICTION.
    DOC_A = "राजेश कुमार पुण्यात दिसून आला. 2026-08-14 21:10"
    DOC_B = "राजेश कुमार मुंबई में देखे गए। 2026-08-14 21:15"

    @pytest.fixture(scope="class")
    def case_id(self, client, auth):
        r = client.post("/api/v1/cases", headers=auth, json={
            "case_number": self.CASE_NUMBER,
            "title": f"Stage-5 claims E2E {RUN}",
            "description": "SYNTHETIC DEMONSTRATION DATA"})
        assert r.status_code == 201, r.text
        cid = r.json()["id"]
        yield cid
        # cleanup: remove the scratch case (FKs cascade) so re-runs do not
        # accumulate synthetic cases in the dev database
        db = SessionLocal()
        try:
            db.delete(db.get(Case, cid))
            db.commit()
        except Exception:  # noqa: BLE001 — cleanup is best-effort
            db.rollback()
        finally:
            db.close()

    @pytest.fixture(scope="class")
    def docs(self, client, auth, case_id):
        da = _upload(client, auth, case_id, f"synthetic_mr_{RUN}.txt",
                     self.DOC_A)
        db = _upload(client, auth, case_id, f"synthetic_hi_{RUN}.txt",
                     self.DOC_B)
        for d in (da, db):
            st = _wait_processed(client, auth, d)
            assert st["processing_status"] == "PROCESSED", st
            # the full review workflow: matches, then entities, then
            # relationships — every candidate confirmed
            _accept_all(client, auth, d)
        return [da, db]

    def test_01_original_text_preserved(self, client, auth, docs):
        for d in docs:
            r = client.get(f"/api/v1/documents/{d}/extraction", headers=auth)
            body = r.json()
            s = body["summary"]
            assert s["original_text"], "original text must be stored in full"
            assert s["language"] in ("mr", "hi")
            assert s["language_confidence"] is not None

    def test_02_claims_materialized_on_acceptance(self, client, auth, docs,
                                                   case_id):
        # (acceptance already happened in the `docs` fixture)
        db = SessionLocal()
        try:
            claims = db.execute(select(EvidenceClaim).where(
                EvidenceClaim.case_id == case_id)).scalars().all()
            was_at = [c for c in claims if c.predicate == "was_at"]
            assert len(was_at) >= 2, \
                f"expected >=2 was_at claims, got {len(was_at)}"
            subjects = {c.subject_entity_id for c in was_at}
            assert len(subjects) == 1, "both claims must share one subject"
            # extracted locations are confirmed location ENTITIES (a fresh
            # case has no seeded location rows with coordinates), so the
            # claims must be attached to two different confirmed entities
            locs = {c.object_entity_id for c in was_at}
            assert len(locs) == 2 and None not in locs, \
                f"claims must attach to two confirmed locations: {locs}"
            values = {c.normalized_value for c in was_at}
            assert len(values) == 2, f"two distinct location values: {values}"
            times = {c.event_time for c in was_at}
            assert all(t is not None for t in times)
            deltas = sorted(abs((a - b).total_seconds()) / 60
                            for i, a in enumerate(times)
                            for b in list(times)[i + 1:] if a is not None
                            and b is not None)
            assert deltas and deltas[0] <= 15, "times must be within 15 min"
        finally:
            db.close()

    def test_03_acceptance_is_idempotent(self, client, auth, docs, case_id):
        # re-accepting is impossible via API (status != PENDING) — but the
        # service-level guard is the idempotent source_reference key.
        db = SessionLocal()
        try:
            claims = db.execute(select(EvidenceClaim).where(
                EvidenceClaim.case_id == case_id)).scalars().all()
            refs = [c.source_reference for c in claims]
            assert len(refs) == len(set(refs)), "duplicate claim rows"
            assert all(r and r.startswith("candidate:") for r in refs)
        finally:
            db.close()

    def test_04_analysis_produces_evidence_contradiction(self, client, auth,
                                                         docs, case_id):
        r = client.post(f"/api/v1/cases/{case_id}/investigation/analyze",
                        headers=auth)
        assert r.status_code == 200, r.text
        r2 = client.get(f"/api/v1/cases/{case_id}/investigation/findings",
                        headers=auth)
        assert r2.status_code == 200
        body = r2.json()
        rows = body.get("current_findings", [])
        ev = [f for f in rows if f.get("finding_type") == "CONTRADICTION"
              and (f.get("details") or {}).get("contradiction_type")
              == "EVIDENCE_CONTRADICTION"]
        assert ev, f"no EVIDENCE_CONTRADICTION finding in {len(rows)} rows"
        f0 = ev[0]
        assert f0["details"]["rule"] == "R4"
        assert f0["details"]["variant"] == "spatial"
        assert f0["details"]["severity"] in ("HIGH", "MEDIUM")
        joined = " ".join(f0.get("explanation") or []).lower()
        assert "investigator review" in joined
        for banned in ("proves", "guilty"):
            assert banned not in joined

    def test_05_impact_and_copilot_see_the_claims(self, client, auth, docs,
                                                  case_id):
        r = client.get(f"/api/v1/cases/{case_id}/copilot/suggestions",
                       headers=auth)
        assert r.status_code == 200
        r2 = client.post(f"/api/v1/cases/{case_id}/copilot/ask",
                         headers=auth,
                         json={"question": "What contradictions are there?"})
        assert r2.status_code == 200
        a = r2.json()
        assert a["intent"] == "contradictions"
        assert a["status"] == "answered"
        assert a["data"]["contradictions"], "copilot must report the R4 finding"
        assert a["provider"] == "deterministic"
