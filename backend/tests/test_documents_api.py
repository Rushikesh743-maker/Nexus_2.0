"""End-to-end tests for the Stage-2 document lifecycle.

Runs against the real development PostgreSQL, using the seeded CASE-2026-001
(it already has confirmed entities, so match suggestions are exercised).
Every uploaded document gets a unique run marker so the suite is
re-runnable (SHA-256 duplicate detection would otherwise trip on the
previous run's upload).
"""

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

FIXTURES = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "documents"))

RUN = time.strftime("%Y%m%d-%H%M%S")
CASE_ID = 1  # seeded CASE-2026-001 with confirmed entities

# `client`, `auth`, `analyst` and `supervisor` come from conftest (Supabase
# tokens).


def _marked_text(tag: str = "") -> str:
    with open(os.path.join(FIXTURES, "synthetic_fir.txt"), encoding="utf-8") as fh:
        return fh.read().rstrip() + f"\n# run marker {RUN}-{tag}\n"


def _upload(client, headers, filename, content, content_type):
    return client.post(
        f"/api/v1/cases/{CASE_ID}/documents",
        files={"file": (filename, content, content_type)},
        headers=headers)


def _wait_status(client, headers, doc_id, want=("PROCESSED", "FAILED"), timeout=30):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        r = client.get(f"/api/v1/documents/{doc_id}/status", headers=headers)
        assert r.status_code == 200, r.text
        last = r.json()
        if last["processing_status"] in want:
            return last
        time.sleep(0.3)
    raise AssertionError(f"document {doc_id} never reached {want}: {last}")


def _extraction(client, headers, doc_id):
    r = client.get(f"/api/v1/documents/{doc_id}/extraction", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def _cand(extraction, etype, name):
    hits = [c for c in extraction["entities"]
            if c["entity_type"] == etype and c["candidate_name"] == name]
    assert hits, (f"no {etype} candidate {name!r}: "
                  f"{[c['candidate_name'] for c in extraction['entities']]}")
    return hits[0]


def _accept_candidate_or_match(client, headers, doc, cand):
    """Accept a candidate the way the workflow demands: if a match
    suggestion is pending, it must be accepted first (which confirms the
    candidate against the existing entity); otherwise accept directly."""
    if cand["match"] and cand["match"]["status"] == "PENDING":
        r = client.post(f"/api/v1/documents/{doc}/extraction/matches/{cand['match']['id']}/accept",
                        headers=headers)
        assert r.status_code == 200, r.text
        return
    r = client.post(f"/api/v1/documents/{doc}/extraction/candidates/{cand['id']}/accept",
                    headers=headers)
    assert r.status_code == 200, r.text


def _get_cand(client, headers, doc, etype, name):
    return _cand(_extraction(client, headers, doc), etype, name)


def _cand_by_id(extraction, candidate_id):
    for c in extraction["entities"]:
        if c["id"] == candidate_id:
            return c
    raise AssertionError(f"candidate {candidate_id} not in extraction")


# ----------------------------------------------------------------- validation

class TestUploadValidation:
    def test_unsupported_extension(self, client, auth):
        r = _upload(client, auth, "evil.exe", b"MZ...binary", "application/octet-stream")
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "DOCUMENT_UNSUPPORTED_TYPE"
        assert "traceback" not in r.text.lower()

    def test_empty_file(self, client, auth):
        r = _upload(client, auth, "empty.txt", b"", "text/plain")
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "DOCUMENT_INVALID"

    def test_pdf_extension_with_text_body(self, client, auth):
        r = _upload(client, auth, "fake.pdf", b"this is not a pdf at all", "text/plain")
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "DOCUMENT_INVALID"

    def test_no_auth(self, client):
        r = client.post(f"/api/v1/cases/{CASE_ID}/documents",
                        files={"file": ("x.txt", b"hello", "text/plain")})
        assert r.status_code == 401

    def test_analyst_can_upload(self, client, analyst):
        r = _upload(client, analyst, f"analyst_{RUN}.txt",
                    _marked_text("analyst").encode(), "text/plain")
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["processing_status"] == "UPLOADED"
        assert "storage_path" not in body  # FS paths never exposed
        assert body["file_hash"]
        st = _wait_status(client, analyst, body["id"])
        assert st["processing_status"] == "PROCESSED"

    def test_supervisor_can_view(self, client, supervisor):
        r = client.get(f"/api/v1/cases/{CASE_ID}/documents", headers=supervisor)
        assert r.status_code == 200


# ------------------------------------------------------------- FIR lifecycle

class TestFIREndToEnd:
    """Upload -> process -> candidates -> match -> accept/reject -> graph."""

    @pytest.fixture(scope="class")
    def state(self, client, auth):
        r = _upload(client, auth, f"synthetic_fir_{RUN}.txt",
                    _marked_text("fir").encode(), "text/plain")
        assert r.status_code == 201, r.text
        doc = r.json()
        st = _wait_status(client, auth, doc["id"])
        assert st["processing_status"] == "PROCESSED", st
        assert st["summary"]["entities"] >= 5
        extraction = _extraction(client, auth, doc["id"])
        entities_before = client.get(f"/api/v1/cases/{CASE_ID}/entities",
                                     headers=auth).json()
        rels_before = client.get(f"/api/v1/cases/{CASE_ID}/relationships",
                                 headers=auth).json()
        return {"doc": doc["id"], "extraction": extraction,
                "entities_before": len(entities_before),
                "rels_before": len(rels_before)}

    def test_candidates_have_provenance(self, state):
        for c in state["extraction"]["entities"]:
            loc = c["source_location"] or {}
            assert loc.get("line") is not None
            assert c["source_snippet"]
            assert 0.0 < c["confidence"] <= 1.0

    def test_expected_entities(self, state):
        names = {(c["entity_type"], c["candidate_name"])
                 for c in state["extraction"]["entities"]}
        assert ("person", "Vikram Rao") in names
        assert ("person", "Suresh Kulkarni") in names
        assert ("phone", "9822044117") in names
        assert ("vehicle", "MH01GH9876") in names
        assert ("vehicle", "MH12AB1234") in names
        types = {t for t, _ in names}
        assert {"account", "event", "case"} <= types

    def test_relationships_with_support(self, state):
        rels = {(r["source_name"], r["relationship_type"], r["target_name"])
                for r in state["extraction"]["relationships"]}
        assert ("Vikram Rao", "CALLED", "9822044117") in rels
        assert ("Suresh Kulkarni", "OWNS", "MH01GH9876") in rels
        assert ("Neha Patil", "USED", "MH12AB1234") in rels
        assert any(t == "TRANSFERRED_TO" for _, t, _ in rels)
        for r in state["extraction"]["relationships"]:
            assert r["source_snippet"]
            assert r["endpoints_confirmed"] is False

    def test_match_suggestions_exist(self, state):
        vikram = _cand(state["extraction"], "person", "Vikram Rao")
        assert vikram["match"], "expected a match suggestion for Vikram Rao"
        m = vikram["match"]
        assert m["similarity"] == 1.0
        assert m["status"] == "PENDING"
        assert m["existing_entity_name"] == "Vikram Rao"
        assert m["reasons"]
        # "V. Rao" (initial + surname) must surface as a 0.8-class match
        vr = _cand(state["extraction"], "person", "V. Rao")
        assert vr["match"]
        assert 0.7 <= vr["match"]["similarity"] < 1.0
        assert vr["match"]["existing_entity_name"] == "Vikram Rao"

    def test_accept_blocked_until_match_reviewed(self, client, auth, state):
        doc, ext = state["doc"], state["extraction"]
        vikram = _cand(ext, "person", "Vikram Rao")
        r = client.post(f"/api/v1/documents/{doc}/extraction/candidates/{vikram['id']}/accept",
                        headers=auth)
        assert r.status_code == 409
        assert r.json()["error"]["code"] == "MATCH_REVIEW_REQUIRED"

    def test_accept_match_folds_into_entity(self, client, auth, state):
        doc, ext = state["doc"], state["extraction"]
        vikram = _cand(ext, "person", "Vikram Rao")
        r = client.post(f"/api/v1/documents/{doc}/extraction/matches/{vikram['match']['id']}/accept",
                        headers=auth)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "ACCEPTED"
        # the candidate is now accepted against the EXISTING entity
        ext2 = _extraction(client, auth, doc)
        v2 = _cand(ext2, "person", "Vikram Rao")
        assert v2["status"] == "ACCEPTED"
        assert v2["accepted_entity_id"]
        assert len(client.get(f"/api/v1/cases/{CASE_ID}/entities",
                              headers=auth).json()) == state["entities_before"]

    def test_accept_new_entity_creates_it(self, client, auth, state):
        """Acceptance links the candidate to a confirmed entity: a new one
        if the case doesn't have that name yet, the existing one if an
        earlier run already confirmed it (deterministic dedup either way)."""
        doc, ext = state["doc"], state["extraction"]
        suresh = _cand(ext, "person", "Suresh Kulkarni")
        _accept_candidate_or_match(client, auth, doc, suresh)
        s2 = _get_cand(client, auth, doc, "person", "Suresh Kulkarni")
        assert s2["status"] == "ACCEPTED"
        assert s2["accepted_entity_id"]
        ents = client.get(f"/api/v1/cases/{CASE_ID}/entities", headers=auth).json()
        assert len(ents) in (state["entities_before"], state["entities_before"] + 1)
        target = [e for e in ents if e["id"] == s2["accepted_entity_id"]]
        assert target and target[0]["canonical_name"] == "Suresh Kulkarni"

    def test_relationship_requires_confirmed_endpoints(self, client, auth, state):
        doc, ext = state["doc"], state["extraction"]
        owns = next(r for r in ext["relationships"]
                    if r["relationship_type"] == "OWNS"
                    and r["source_name"] == "Suresh Kulkarni")
        r = client.post(f"/api/v1/documents/{doc}/extraction/relationships/{owns['id']}/accept",
                        headers=auth)
        assert r.status_code == 409
        assert r.json()["error"]["code"] == "CANDIDATE_NOT_CONFIRMED"
        # The relationship names its exact endpoint candidates; accept those
        # specific rows (not merely "a" candidate with that name).
        # Re-fetch: earlier tests in this class may already have confirmed
        # one of the endpoints.
        ext = _extraction(client, auth, doc)
        owns = next(r for r in ext["relationships"]
                    if r["relationship_type"] == "OWNS"
                    and r["source_name"] == "Suresh Kulkarni")
        src = _cand_by_id(ext, owns["source_candidate_id"])
        tgt = _cand_by_id(ext, owns["target_candidate_id"])
        assert src["candidate_name"] == "Suresh Kulkarni"
        assert tgt["candidate_name"] == "MH01GH9876"
        if src["status"] != "ACCEPTED":
            _accept_candidate_or_match(client, auth, doc, src)
        if tgt["status"] != "ACCEPTED":
            _accept_candidate_or_match(client, auth, doc, tgt)
        r = client.post(f"/api/v1/documents/{doc}/extraction/relationships/{owns['id']}/accept",
                        headers=auth)
        assert r.status_code == 200, r.text
        # the confirmed relationship exists between the two accepted entities
        # (dedup: re-accepting across runs must not create a second row)
        ext = _extraction(client, auth, doc)
        src_e = _cand_by_id(ext, owns["source_candidate_id"])["accepted_entity_id"]
        tgt_e = _cand_by_id(ext, owns["target_candidate_id"])["accepted_entity_id"]
        assert src_e and tgt_e
        rels = client.get(f"/api/v1/cases/{CASE_ID}/relationships", headers=auth).json()
        assert any(
            x["relationship_type"] == "OWNS"
            and {x["source_entity_id"], x["target_entity_id"]} == {src_e, tgt_e}
            for x in rels)

    def test_relationship_rejected_twice_is_conflict(self, client, auth, state):
        doc, ext = state["doc"], state["extraction"]
        transfer = next(r for r in ext["relationships"]
                        if r["relationship_type"] == "TRANSFERRED_TO")
        r = client.post(f"/api/v1/documents/{doc}/extraction/relationships/{transfer['id']}/reject",
                        headers=auth)
        assert r.status_code == 200
        assert r.json()["status"] == "REJECTED"
        r = client.post(f"/api/v1/documents/{doc}/extraction/relationships/{transfer['id']}/reject",
                        headers=auth)
        assert r.status_code == 409
        assert r.json()["error"]["code"] == "CANDIDATE_ALREADY_REVIEWED"

    def test_reject_entity_cascades_to_relationships(self, client, auth, state):
        doc, ext = state["doc"], state["extraction"]
        phone = _cand(ext, "phone", "9822044117")
        r = client.post(f"/api/v1/documents/{doc}/extraction/candidates/{phone['id']}/reject",
                        headers=auth)
        assert r.status_code == 200
        # the CALLED relationship (Vikram Rao -> phone) must be auto-rejected
        ext2 = _extraction(client, auth, doc)
        called = next(r for r in ext2["relationships"] if r["relationship_type"] == "CALLED")
        assert called["status"] == "REJECTED"
        assert called["decision_note"] == "endpoint entity rejected"

    def test_reject_twice_is_conflict(self, client, auth, state):
        doc, ext = state["doc"], state["extraction"]
        phone = _cand(ext, "phone", "9822044117")
        r = client.post(f"/api/v1/documents/{doc}/extraction/candidates/{phone['id']}/reject",
                        headers=auth)
        assert r.status_code == 409
        assert r.json()["error"]["code"] == "CANDIDATE_ALREADY_REVIEWED"

    def test_duplicate_upload_blocked_by_sha(self, client, auth, state):
        content = _marked_text("fir").encode()
        r = _upload(client, auth, f"dup_{RUN}.txt", content, "text/plain")
        assert r.status_code == 409
        assert r.json()["error"]["code"] == "DOCUMENT_DUPLICATE"

    def test_processed_document_cannot_reprocess(self, client, auth, state):
        r = client.post(f"/api/v1/documents/{state['doc']}/process", headers=auth)
        assert r.status_code == 409
        assert r.json()["error"]["code"] == "DOCUMENT_ALREADY_PROCESSED"


# --------------------------------------------------------------- corrupted PDF

class TestFailedProcessing:
    def test_corrupt_pdf_fails_honestly(self, client, auth):
        with open(os.path.join(FIXTURES, "synthetic_fir.pdf"), "rb") as fh:
            good = fh.read()
        # cut before the xref table (guaranteed invalid), then append unique
        # tail bytes so re-runs don't trip the SHA-256 duplicate check
        truncated = good[:120] + b"%corrupt-run " + RUN.encode()
        r = _upload(client, auth, f"corrupt_{RUN}.pdf", truncated, "application/pdf")
        assert r.status_code == 201, r.text
        st = _wait_status(client, auth, r.json()["id"])
        assert st["processing_status"] == "FAILED"
        assert st["processing_error"]
        low = st["processing_error"].lower()
        assert "traceback" not in low
        assert "/home" not in st["processing_error"]  # no FS paths

    def test_retry_failed_keeps_failing_without_duplication(self, client, auth):
        # find the corrupted document from the previous test by listing
        docs = client.get(f"/api/v1/cases/{CASE_ID}/documents", headers=auth).json()
        failed = [d for d in docs if d["processing_status"] == "FAILED"]
        assert failed, "expected the corrupted PDF to still be FAILED"
        doc = failed[0]
        r = client.post(f"/api/v1/documents/{doc['id']}/process", headers=auth)
        assert r.status_code == 202
        st = _wait_status(client, auth, doc["id"])
        assert st["processing_status"] == "FAILED"
        ext = _extraction(client, auth, doc["id"])
        assert ext["summary"]["entities"] == 0


# ---------------------------------------------------------------------- CSV

class TestCSVEndToEnd:
    @pytest.fixture(scope="class")
    def state(self, client, auth):
        with open(os.path.join(FIXTURES, "synthetic_calls.csv"),
                  encoding="utf-8") as fh:
            content = fh.read().rstrip() + f"\n# synthetic run {RUN}\n"
        r = _upload(client, auth, f"synthetic_calls_{RUN}.csv",
                    content.encode(), "text/csv")
        assert r.status_code == 201, r.text
        doc = r.json()
        st = _wait_status(client, auth, doc["id"])
        assert st["processing_status"] == "PROCESSED", st
        return {"doc": doc["id"], "extraction": _extraction(client, auth, doc["id"])}

    def test_row_provenance(self, state):
        ext = state["extraction"]
        assert ext["summary"]["source_type"] == "csv"
        for c in ext["entities"]:
            loc = c["source_location"] or {}
            assert loc.get("row") is not None
            assert loc.get("column")

    def test_cdr_relationships(self, state):
        rels = {(r["relationship_type"]) for r in state["extraction"]["relationships"]}
        assert {"CALLED", "OWNS", "LOCATED_AT", "INVOLVED_IN"} <= rels

    def test_name_matches_case_entity(self, state):
        vikram = _cand(state["extraction"], "person", "Vikram Rao")
        assert vikram["match"]
        assert vikram["match"]["similarity"] == 1.0


# ------------------------------------------------------------------- audit

class TestAudit:
    def test_document_actions_are_audited(self):
        # the audit log is the database table — read it directly
        from sqlalchemy import select

        from app.core.database import SessionLocal
        from app.models import AuditLog

        db = SessionLocal()
        try:
            actions = {a.action for a in db.scalars(select(AuditLog)).all()}
        finally:
            db.close()
        for expected in ("DOCUMENT_UPLOADED", "DOCUMENT_PROCESSING_STARTED",
                         "DOCUMENT_PROCESSING_COMPLETED",
                         "ENTITY_ACCEPTED", "ENTITY_REJECTED",
                         "ENTITY_MATCH_ACCEPTED", "RELATIONSHIP_ACCEPTED",
                         "RELATIONSHIP_REJECTED"):
            assert expected in actions, f"missing audit action {expected}"
