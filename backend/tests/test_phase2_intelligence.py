"""Phase 2 tests (work item B): a finding is never shown without its
evidence chain.

``GET /cases/{id}/investigation/findings/{fid}`` resolves the finding's
referenced entity / relationship / evidence ids to named rows plus
provenance (document, location, snippet). When nothing is linked the
response says so explicitly instead of presenting an empty box.

The end-to-end test builds its own case (two documents placing the same
confirmed person at different confirmed locations 15 minutes apart),
runs the real analysis, and asserts the resulting CONTRADICTION finding
resolves to a complete chain with document names and claim snippets.
"""

import os
import sys
import time
import uuid

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.database import SessionLocal  # noqa: E402

RUN = time.strftime("%Y%m%d%H%M%S") + uuid.uuid4().hex[:6]

# `client` and `auth` come from conftest (Supabase tokens).


def _new_case(client, headers, tag):
    r = None
    for _ in range(5):
        case_number = f"PHI-2026-{uuid.uuid4().int % 10**9:09d}"
        r = client.post("/api/v1/cases",
                        json={"case_number": case_number,
                              "title": f"phase-2 intelligence {tag} {RUN}"},
                        headers=headers)
        if r.status_code == 201:
            return r.json()
        assert r.status_code != 409, f"case number collision: {r.text}"
    raise AssertionError(f"could not create a case: {r.text}")


def _delete_case(db, case_id):
    from sqlalchemy import text
    db.execute(text('DELETE FROM "case" WHERE id = :i'), {"i": case_id})
    db.commit()


def _upload(client, headers, case_id, filename, content):
    r = client.post(f"/api/v1/cases/{case_id}/documents",
                    files={"file": (filename, content.encode(), "text/plain")},
                    headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def _wait_docs_terminal(client, headers, case_id, timeout=120):
    deadline = time.time() + timeout
    docs = []
    while time.time() < deadline:
        docs = client.get(f"/api/v1/cases/{case_id}/documents",
                          headers=headers).json()
        if docs and all(d["processing_status"] in ("PROCESSED", "FAILED")
                        for d in docs):
            return docs
        time.sleep(0.5)
    raise AssertionError(f"documents never reached a terminal state: {docs}")


def _cand(extraction, etype, name):
    for e in extraction["entities"]:
        if e["entity_type"] == etype and e["candidate_name"] == name:
            return e
    return None


def _drain_review(client, headers, case_id):
    """Resolve every pending review item so the case can leave
    REVIEW_REQUIRED: reject match suggestions (keep entities separate),
    reject extra entity candidates, confirm remaining relationship
    candidates. All data is synthetic test fixture content."""
    docs = client.get(f"/api/v1/cases/{case_id}/documents",
                      headers=headers).json()
    doc_ids = [d["id"] for d in docs]
    for _ in range(12):
        acted = False
        for did in doc_ids:
            ex = client.get(f"/api/v1/documents/{did}/extraction",
                            headers=headers).json()
            for m in ex.get("matches", []):
                if m["status"] == "PENDING":
                    r = client.post(
                        f"/api/v1/documents/{did}/extraction/matches/"
                        f"{m['id']}/reject", headers=headers)
                    assert r.status_code == 200, r.text
                    acted = True
        q = client.get(f"/api/v1/cases/{case_id}/review/queue",
                       headers=headers).json()
        rels = [x["id"] for x in q.get("candidate_relationships", [])]
        ents = [x["id"] for x in q.get("new_entities", [])]
        if ents:
            r = client.post(f"/api/v1/cases/{case_id}/review/bulk",
                            json={"category": "entity", "action": "reject",
                                  "item_ids": ents}, headers=headers)
            assert r.status_code == 200, r.text
            acted = True
        if rels:
            r = client.post(f"/api/v1/cases/{case_id}/review/bulk",
                            json={"category": "relationship",
                                  "action": "confirm",
                                  "item_ids": rels}, headers=headers)
            assert r.status_code == 200, r.text
            acted = True
        if q.get("total_pending", 0) == 0:
            return
        if not acted:
            break
    raise AssertionError(f"review queue never drained: {q}")


def _confirm(client, headers, case_id, item_ids):
    r = client.post(f"/api/v1/cases/{case_id}/review/bulk",
                    json={"category": "entity", "action": "confirm",
                          "item_ids": item_ids},
                    headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def _build_contradiction_case(client, auth, case_id):
    """Same confirmed person, two confirmed locations, 15 minutes apart
    (plus the confirmed LOCATED_AT edges so a graph exists)."""
    d1 = _upload(client, auth, case_id, "fir.txt",
                 "SYNTHETIC DEMONSTRATION DATA - phase 2 intelligence.\n"
                 "On 2026-07-20 22:30, Vikram Sethi was seen at Bhiwandi Godown.\n")
    d2 = _upload(client, auth, case_id, "surv.txt",
                 "SYNTHETIC DEMONSTRATION DATA - phase 2 intelligence 2.\n"
                 "On 2026-07-20 22:45, Vikram Sethi was seen at Kurla.\n")
    _wait_docs_terminal(client, auth, case_id)

    ids = []
    for doc, loc in ((d1, "Bhiwandi Godown"), (d2, "Kurla")):
        ex = client.get(f"/api/v1/documents/{doc['id']}/extraction",
                        headers=auth).json()
        person = _cand(ex, "person", "Vikram Sethi")
        place = _cand(ex, "location", loc)
        assert person and place, (
            f"expected person+location candidates, got: "
            f"{[(e['entity_type'], e['candidate_name']) for e in ex['entities']]}")
        ids += [person["id"], place["id"]]
    _confirm(client, auth, case_id, ids)

    # confirm the LOCATED_AT relationship candidates (endpoints accepted)
    queue = client.get(f"/api/v1/cases/{case_id}/review/queue",
                       headers=auth).json()
    rel_ids = [x["id"] for x in queue["candidate_relationships"]
               if x["relationship_type"] == "LOCATED_AT"
               and {x["source_name"], x["target_name"]}
               <= {"Vikram Sethi", "Bhiwandi Godown", "Kurla"}]
    rels_seen = [(x["source_name"], x["relationship_type"], x["target_name"])
                 for x in queue["candidate_relationships"]]
    assert len(rel_ids) == 2, (
        f"expected 2 LOCATED_AT relationship candidates: {rels_seen}")
    r = client.post(f"/api/v1/cases/{case_id}/review/bulk",
                    json={"category": "relationship", "action": "confirm",
                          "item_ids": rel_ids},
                    headers=auth)
    assert r.status_code == 200, r.text


def test_finding_detail_resolves_full_evidence_chain(client, auth):
    """A CONTRADICTION finding resolves to named entities, evidence rows
    with document names, and claims with original text — the chain is
    complete, nothing is missing."""
    case_id = _new_case(client, auth, "chain")["id"]
    db = SessionLocal()
    try:
        _build_contradiction_case(client, auth, case_id)
        r = client.post(f"/api/v1/cases/{case_id}/investigation/analyze",
                        headers=auth)
        assert r.status_code == 200, r.text
        analysis = r.json()
        contradictions = [f for f in analysis["findings"]
                          if f["finding_type"] == "CONTRADICTION"]
        assert contradictions, (
            f"expected a CONTRADICTION finding, got: "
            f"{[f['finding_type'] for f in analysis['findings']]}")
        fid = contradictions[0]["id"]

        d = client.get(f"/api/v1/cases/{case_id}/investigation/findings/{fid}",
                       headers=auth)
        assert d.status_code == 200, d.text
        body = d.json()
        assert body["finding"]["id"] == fid
        assert body["finding"]["finding_type"] == "CONTRADICTION"

        chain = body["evidence_chain"]
        assert chain["complete"] is True
        assert chain["missing"] == []

        # the involved person is resolved to a named entity
        names = [e["canonical_name"] for e in chain["entities"]]
        assert "Vikram Sethi" in names

        # both evidence rows resolve with their real document names
        assert len(chain["evidence"]) == 2
        docs = {ev["document"] for ev in chain["evidence"]}
        assert docs == {"fir.txt", "surv.txt"}, docs
        for ev in chain["evidence"]:
            assert ev["document_id"], "evidence row lost its document link"

        # claims carry the original language snippet + location
        claims = [c for ev in chain["evidence"] for c in ev["claims"]]
        assert len(claims) == 2
        locs = {c["location"] for c in claims}
        assert locs == {"Bhiwandi Godown", "Kurla"}, locs
        for c in claims:
            assert c["predicate"] == "was_at"
            assert c["original_text"], "claim lost its original snippet"
            assert "Vikram Sethi" in c["original_text"]
    finally:
        _delete_case(db, case_id)
        db.close()


def test_snapshot_create_list_get_compare(client, auth):
    """Immutable snapshots: v1 captured, new confirmed data added, v2
    captured; the compare answers 'what changed' as a pure diff
    (new entities / relationships / evidence), and the snapshots stay
    immutable (no update or delete endpoints exist)."""
    case_id = _new_case(client, auth, "snap")["id"]
    db = SessionLocal()
    try:
        # -- baseline: one confirmed person + location + edge ------------
        d1 = _upload(client, auth, case_id, "base.txt",
                     "SYNTHETIC DEMONSTRATION DATA - phase 2 snapshots.\n"
                     "On 2026-07-20 22:30, Vikram Sethi was seen at Kurla.\n")
        _wait_docs_terminal(client, auth, case_id)
        ex = client.get(f"/api/v1/documents/{d1['id']}/extraction",
                        headers=auth).json()
        _confirm(client, auth, case_id,
                 [c["id"] for c in ex["entities"]
                  if c["candidate_name"] in ("Vikram Sethi", "Kurla")])
        q = client.get(f"/api/v1/cases/{case_id}/review/queue",
                       headers=auth).json()
        r = client.post(f"/api/v1/cases/{case_id}/review/bulk",
                        json={"category": "relationship", "action": "confirm",
                              "item_ids": [x["id"] for x in
                                           q["candidate_relationships"]
                                           if x["relationship_type"] ==
                                           "LOCATED_AT"]},
                        headers=auth)
        assert r.status_code == 200, r.text

        # -- snapshot 1 ----------------------------------------------------
        s1 = client.post(f"/api/v1/cases/{case_id}/snapshots",
                         json={"label": "v1 baseline"}, headers=auth)
        assert s1.status_code == 201, s1.text
        s1 = s1.json()
        assert s1["sequence"] == 1
        assert s1["created_by_name"]

        # -- add confirmed data: a new person + vehicle + OWNS ------------
        d2 = _upload(client, auth, case_id, "more.txt",
                     "SYNTHETIC DEMONSTRATION DATA - phase 2 snapshots 2.\n"
                     "Rajesh Kumar was seen at Kurla on 2026-07-21.\n"
                     "Vehicle MH09ZZ5544 owned by Rajesh Kumar.\n")
        _wait_docs_terminal(client, auth, case_id)
        ex2 = client.get(f"/api/v1/documents/{d2['id']}/extraction",
                         headers=auth).json()
        names = {e["candidate_name"]: e["id"] for e in ex2["entities"]}
        _confirm(client, auth, case_id,
                 [names["Rajesh Kumar"], names["MH09ZZ5544"]])
        q2 = client.get(f"/api/v1/cases/{case_id}/review/queue",
                        headers=auth).json()
        owns = [x["id"] for x in q2["candidate_relationships"]
                if x["relationship_type"] == "OWNS"]
        r2 = client.post(f"/api/v1/cases/{case_id}/review/bulk",
                         json={"category": "relationship",
                               "action": "confirm", "item_ids": owns},
                         headers=auth)
        assert r2.status_code == 200, r2.text

        # -- snapshot 2 + compare ------------------------------------------
        s2 = client.post(f"/api/v1/cases/{case_id}/snapshots",
                         json={}, headers=auth)
        assert s2.status_code == 201
        s2 = s2.json()
        assert s2["sequence"] == 2
        # the confirmed data moved -> different graph version
        assert s2["graph_version"] != s1["graph_version"]

        cmp = client.get(
            f"/api/v1/cases/{case_id}/snapshots/compare?from_seq=1&to_seq=2",
            headers=auth)
        assert cmp.status_code == 200, cmp.text
        diff = cmp.json()
        assert diff["from"]["sequence"] == 1
        assert diff["to"]["sequence"] == 2
        added_entities = {e["canonical_name"]
                          for e in diff["entities"]["added"]}
        assert "Rajesh Kumar" in added_entities
        assert "Vikram Sethi" not in added_entities  # unchanged
        assert diff["entities"]["removed"] == []
        added_rels = {(rel["relationship_type"], rel["source_name"])
                      for rel in diff["relationships"]["added"]}
        assert ("OWNS", "Rajesh Kumar") in added_rels
        assert len(diff["evidence"]["added"]) >= 2  # new extractions
        assert diff["summary"]["entities_added"] == 2
        assert diff["summary"]["entities_removed"] == 0

        # -- immutability: v1 still shows the old state ---------------------
        g1 = client.get(f"/api/v1/cases/{case_id}/snapshots/{s1['id']}",
                        headers=auth).json()
        g2 = client.get(f"/api/v1/cases/{case_id}/snapshots/{s2['id']}",
                        headers=auth).json()
        assert g1["graph_version"] == s1["graph_version"]
        assert g2["graph_version"] == s2["graph_version"]
        n1 = {e["canonical_name"] for e in g1["payload"]["entities"]}
        n2 = {e["canonical_name"] for e in g2["payload"]["entities"]}
        assert "Rajesh Kumar" not in n1
        assert "Rajesh Kumar" in n2
        assert g1["payload"] != g2["payload"]

        # and there is no way to mutate or delete a snapshot
        for method in ("put", "patch", "delete"):
            resp = getattr(client, method)(
                f"/api/v1/cases/{case_id}/snapshots/1", headers=auth)
            assert resp.status_code == 405, (method, resp.status_code)

        # invalid compare pairs are rejected explicitly
        bad = client.get(
            f"/api/v1/cases/{case_id}/snapshots/compare?from_seq=1&to_seq=9",
            headers=auth)
        assert bad.status_code == 404
        assert bad.json()["error"]["code"] == "SNAPSHOT_COMPARE_INVALID"
    finally:
        _delete_case(db, case_id)
        db.close()


def test_snapshot_404_semantics(client, auth):
    """Snapshots are case-scoped: another case's snapshot id is a 404."""
    case_id = _new_case(client, auth, "snap404")["id"]
    other = _new_case(client, auth, "snap404b")["id"]
    db = SessionLocal()
    try:
        s = client.post(f"/api/v1/cases/{case_id}/snapshots", json={},
                        headers=auth)
        assert s.status_code == 201
        sid = s.json()["id"]
        r = client.get(f"/api/v1/cases/{other}/snapshots/{sid}",
                       headers=auth)
        assert r.status_code == 404
        r2 = client.get(
            f"/api/v1/cases/{case_id}/snapshots/compare?from_seq=5&to_seq=6",
            headers=auth)
        assert r2.status_code == 404
    finally:
        _delete_case(db, case_id)
        _delete_case(db, other)
        db.close()


def test_analysis_state_on_all_intelligence_surfaces(client, auth):
    """P2-E: every intelligence surface carries the analysis-state block
    (state + graph_version + reason + analyzed + insufficient) so stale
    results are never silently presented as current. The block flips
    not-analyzed -> up-to-date (after analysis) -> stale (after new
    confirmed data) -> up-to-date (after recalculation)."""
    case_id = _new_case(client, auth, "analysis-state")["id"]
    db = SessionLocal()
    try:
        # -- one confirmed person + location + edge --------------------
        d1 = _upload(client, auth, case_id, "state.txt",
                     "SYNTHETIC DEMONSTRATION DATA - phase 2 analysis state.\n"
                     "On 2026-07-20 22:30, Vikram Sethi was seen at Kurla.\n")
        _wait_docs_terminal(client, auth, case_id)
        ex = client.get(f"/api/v1/documents/{d1['id']}/extraction",
                        headers=auth).json()
        _confirm(client, auth, case_id,
                 [c["id"] for c in ex["entities"]
                  if c["candidate_name"] in ("Vikram Sethi", "Kurla")])
        q = client.get(f"/api/v1/cases/{case_id}/review/queue",
                       headers=auth).json()
        r = client.post(f"/api/v1/cases/{case_id}/review/bulk",
                        json={"category": "relationship",
                              "action": "confirm",
                              "item_ids": [x["id"] for x in
                                           q["candidate_relationships"]
                                           if x["relationship_type"] ==
                                           "LOCATED_AT"]},
                        headers=auth)
        assert r.status_code == 200, r.text
        _drain_review(client, auth, case_id)  # queue empty -> ready

        base = f"/api/v1/cases/{case_id}"
        surfaces = [
            f"{base}/graph/metrics", f"{base}/graph/bridges",
            f"{base}/graph/clusters", f"{base}/graph/cross-case",
            f"{base}/graph/findings",
            f"{base}/investigation/findings",
            f"{base}/investigation/contradictions",
            f"{base}/investigation/gaps",
            f"{base}/investigation/hypotheses",
            f"{base}/investigation/timeline",
            f"{base}/investigation/geospatial",
            f"{base}/investigation/evidence-impact",
            f"{base}/snapshots",
        ]

        # -- before any analysis: NOT_ANALYZED on every surface --------
        for url in surfaces:
            ab = client.get(url, headers=auth).json()["analysis"]
            assert ab["state"] == "not-analyzed", (url, ab)

        # -- run the full analysis -> UP_TO_DATE everywhere -------------
        run = client.post(f"{base}/analysis/run", headers=auth)
        assert run.status_code == 200, run.text
        ab = run.json()["analysis"]
        assert ab["state"] == "up-to-date", ab
        assert ab["analyzed"] is True
        version = ab["graph_version"]
        for url in surfaces:
            r = client.get(url, headers=auth)
            assert r.status_code == 200, (url, r.text)
            a = r.json()["analysis"]
            assert a["state"] == "up-to-date", (url, a)
            assert a["graph_version"] == version, (url, a)
            assert a["analyzed"] is True, url

        # -- add new confirmed data -> STALE everywhere ------------------
        d2 = _upload(client, auth, case_id, "state2.txt",
                     "SYNTHETIC DEMONSTRATION DATA - phase 2 analysis state 2.\n"
                     "Rajesh Kumar was seen at Kurla on 2026-07-21.\n")
        _wait_docs_terminal(client, auth, case_id)
        ex2 = client.get(f"/api/v1/documents/{d2['id']}/extraction",
                         headers=auth).json()
        names = {e["candidate_name"]: e["id"] for e in ex2["entities"]}
        _confirm(client, auth, case_id, [names["Rajesh Kumar"]])
        _drain_review(client, auth, case_id)  # queue empty again
        a = client.get(f"{base}/graph/metrics", headers=auth).json()["analysis"]
        assert a["state"] == "stale", a
        assert "changed" in a["reason"].lower(), a["reason"]
        a2 = client.get(f"{base}/snapshots", headers=auth).json()["analysis"]
        assert a2["state"] == "stale"
        assert a2["graph_version"] != version  # confirmed data moved on

        # -- recalculate -> UP_TO_DATE again ------------------------------
        rec = client.post(f"{base}/analysis/recalculate", headers=auth)
        assert rec.status_code == 200, rec.text
        assert rec.json()["analysis"]["state"] == "up-to-date"
    finally:
        _delete_case(db, case_id)
        db.close()


def test_entity_profile_full_resolution(client, auth):
    """A confirmed person's profile: connections with provenance, claims
    with original text, locations, findings, computed metrics and the
    case's analysis freshness — all from confirmed data."""
    case_id = _new_case(client, auth, "profile")["id"]
    db = SessionLocal()
    try:
        _build_contradiction_case(client, auth, case_id)
        r = client.post(f"/api/v1/cases/{case_id}/investigation/analyze",
                        headers=auth)
        assert r.status_code == 200, r.text

        ents = client.get(f"/api/v1/cases/{case_id}/entities",
                          headers=auth).json()
        vikram = next(e for e in ents
                      if e["canonical_name"] == "Vikram Sethi")

        d = client.get(f"/api/v1/cases/{case_id}/entities/{vikram['id']}",
                       headers=auth)
        assert d.status_code == 200, d.text
        p = d.json()
        assert p["entity"]["canonical_name"] == "Vikram Sethi"
        assert p["entity"]["entity_type"] == "person"

        # two confirmed LOCATED_AT edges, one per document
        assert p["metrics"]["degree"] == 2
        assert p["metrics"]["documents"] == 2
        assert p["metrics"]["first_seen"].startswith("2026-07-20T22:30")
        assert p["metrics"]["last_seen"].startswith("2026-07-20T22:45")
        assert p["metrics"]["time_span_hours"] == 0.25

        peers = {(c["relationship_type"], c["peer"]["canonical_name"])
                 for c in p["connections"]}
        assert peers == {("LOCATED_AT", "Bhiwandi Godown"),
                         ("LOCATED_AT", "Kurla")}, peers
        for c in p["connections"]:
            assert c["provenance"]["document_id"], "connection lost its doc"
            assert c["direction"] in ("outgoing", "incoming")

        # the two was_at claims keep their original text
        assert len(p["claims"]) == 2
        assert {c["location"] for c in p["claims"]} == {
            "Bhiwandi Godown", "Kurla"}
        for c in p["claims"]:
            assert c["predicate"] == "was_at"
            assert "Vikram Sethi" in c["original_text"]

        # locations: names from confirmed data, coordinates never guessed
        locs = {l["name"]: l for l in p["locations"]}
        assert set(locs) == {"Bhiwandi Godown", "Kurla"}
        for l in p["locations"]:
            # no geocoder configured in this environment -> None, not a guess
            assert l["latitude"] is None and l["longitude"] is None

        # the CONTRADICTION finding that involves him is listed
        assert any(f["finding_type"] == "CONTRADICTION"
                   for f in p["findings"])

        # analysis freshness travels with the profile
        assert p["analysis"]["state"] in (
            "not-analyzed", "up-to-date", "stale", "insufficient")
        assert p["analysis"]["graph_version"]
        assert p["analysis"]["state"] == "up-to-date"
    finally:
        _delete_case(db, case_id)
        db.close()


def test_entity_profile_candidate_id_is_not_a_confirmed_entity(client, auth):
    """An extraction candidate id is a 400 with an explicit explanation,
    not a 404 and not a silent empty profile."""
    case_id = _new_case(client, auth, "cand")["id"]
    db = SessionLocal()
    try:
        d1 = _upload(client, auth, case_id, "c.txt",
                     "SYNTHETIC DEMONSTRATION DATA - phase 2 candidate.\n"
                     "Vikram Sethi was seen at Kurla on 2026-07-20.\n")
        _wait_docs_terminal(client, auth, case_id)
        ex = client.get(f"/api/v1/documents/{d1['id']}/extraction",
                        headers=auth).json()
        person = _cand(ex, "person", "Vikram Sethi")
        assert person, [e["candidate_name"] for e in ex["entities"]]
        # still PENDING — the profile refuses with the exact reason
        r = client.get(f"/api/v1/cases/{case_id}/entities/{person['id']}",
                       headers=auth)
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "ENTITY_NOT_CONFIRMED"
    finally:
        _delete_case(db, case_id)
        db.close()


def test_entity_profile_404_semantics(client, auth):
    """Unknown entity id -> 404; a real entity requested through another
    case -> 404 (case-scoped isolation)."""
    r = client.get("/api/v1/cases/8/entities/999999", headers=auth)
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "ENTITY_NOT_FOUND"

    ents = client.get("/api/v1/cases/8/entities", headers=auth).json()
    real = ents[0]
    r2 = client.get(f"/api/v1/cases/1/entities/{real['id']}", headers=auth)
    assert r2.status_code == 404


def test_finding_detail_without_chain_is_explicit(client, auth):
    """A finding that links no rows must say 'no evidence' explicitly —
    complete=False plus a message in `missing`, never a silent empty
    box. A synthetic finding row with empty id lists is inserted into a
    throwaway case purely to exercise the resolver's explicit-empty path
    (it is a test fixture, not a claim about real data)."""
    case_id = _new_case(client, auth, "nochain")["id"]
    db = SessionLocal()
    try:
        from app.models import GraphFinding
        f = GraphFinding(
            case_id=case_id,
            finding_type="INVESTIGATION_GAP",
            title="Test fixture: a gap with no linked rows",
            summary="Inserted to exercise the explicit no-evidence path.",
            explanation=[],
            details={},
            involved_entity_ids=[],
            supporting_relationship_ids=[],
            supporting_evidence_ids=[],
            related_case_ids=[],
            analysis_method="test-fixture",
            graph_version="0" * 32,
            status="ACTIVE",
        )
        db.add(f)
        db.commit()
        db.refresh(f)
        fid = f.id

        d = client.get(f"/api/v1/cases/{case_id}/investigation/findings/{fid}",
                       headers=auth)
        assert d.status_code == 200, d.text
        chain = d.json()["evidence_chain"]
        assert chain["complete"] is False
        assert chain["entities"] == [] and chain["relationships"] == []
        assert chain["evidence"] == []
        assert any("no" in m.lower() and "evidence" in m.lower()
                   for m in chain["missing"]), chain["missing"]
    finally:
        _delete_case(db, case_id)
        db.close()


def test_finding_detail_404_semantics(client, auth):
    """Unknown finding id and a real finding requested through a
    different case are both 404 (case-scoped isolation: cross-case
    access is indistinguishable from not found)."""
    r = client.get("/api/v1/cases/1/investigation/findings/999999",
                   headers=auth)
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "FINDING_NOT_FOUND"

    # a REAL finding of the demo E2E case, requested through case 1
    rr = client.post("/api/v1/cases/8/investigation/analyze", headers=auth)
    assert rr.status_code == 200, rr.text
    fs = rr.json()["findings"]
    assert fs, "demo E2E case must yield at least one finding"
    fid = fs[0]["id"]
    r2 = client.get(f"/api/v1/cases/1/investigation/findings/{fid}",
                    headers=auth)
    assert r2.status_code == 404
    # and through its own case it resolves fine
    r3 = client.get(f"/api/v1/cases/8/investigation/findings/{fid}",
                    headers=auth)
    assert r3.status_code == 200


def test_finding_detail_requires_case_access(client, auth, investigator_b):
    """A user without access to the case gets 404 (not 403) — the case
    itself is never revealed. A different INVESTIGATOR cannot see this
    investigator's case (only own + platform cases)."""
    case_id = _new_case(client, auth, "iso")["id"]
    db = SessionLocal()
    try:
        # A second, distinct investigator (same role) must not see it.
        other = investigator_b
        d = client.get(
            f"/api/v1/cases/{case_id}/investigation/findings/1",
            headers=other)
        assert d.status_code == 404, d.text
        # and the case list itself must not contain the case
        lst = client.get("/api/v1/cases", headers=other).json()
        assert case_id not in [c["id"] for c in lst]
    finally:
        _delete_case(db, case_id)
        db.close()
