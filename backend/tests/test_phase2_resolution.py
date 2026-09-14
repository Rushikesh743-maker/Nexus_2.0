"""Phase 2 tests (work item A): ranked entity resolution with reasons and
contextual signals (shared phone / vehicle / account / location).

Suggestions only — nothing is auto-merged. The end-to-end tests drive the
real workflow:

  1. context test  — doc1 confirms person + vehicle + OWNS; doc2 (CSV)
     re-states the vehicle next to an initial-form name. The suggestion
     for the initial-form candidate must cite the shared vehicle and be
     capped below certainty.
  2. multi test    — one candidate with two plausible confirmed names
     (exact + extended) gets TWO ranked suggestions, best first.

Only the deterministic rule extractor is exercised (no LLM), so every
extraction in here is reproducible.
"""

import os
import sys
import time
import uuid

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.database import SessionLocal  # noqa: E402
from app.services.entity_resolution import (  # noqa: E402
    combine_scores, contextual_signals, ranked_matches, score_pair)

RUN = time.strftime("%Y%m%d%H%M%S") + uuid.uuid4().hex[:6]

# `client` and `auth` come from conftest (Supabase tokens).


def _new_case(client, headers, tag):
    r = None
    for _ in range(5):
        case_number = f"PHR-2026-{uuid.uuid4().int % 10**9:09d}"
        r = client.post("/api/v1/cases",
                        json={"case_number": case_number,
                              "title": f"phase-2 resolution {tag} {RUN}"},
                        headers=headers)
        if r.status_code == 201:
            return r.json()
        assert r.status_code != 409, f"case number collision: {r.text}"
    raise AssertionError(f"could not create a case: {r.text}")


def _delete_case(db, case_id):
    from sqlalchemy import text
    db.execute(text('DELETE FROM "case" WHERE id = :i'), {"i": case_id})
    db.commit()


def _upload(client, headers, case_id, filename, content, ctype):
    r = client.post(f"/api/v1/cases/{case_id}/documents",
                    files={"file": (filename, content, ctype)},
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


def _confirm(client, headers, case_id, category, item_ids):
    r = client.post(f"/api/v1/cases/{case_id}/review/bulk",
                    json={"category": category, "action": "confirm",
                          "item_ids": item_ids},
                    headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


# ------------------------------------------------------------- pure scoring

def test_ranked_matches_returns_ranked_alternatives():
    """Several plausible existing names -> ranked list, best first, all
    with data-supported reasons (only the documented deterministic rules
    fire — nothing speculative)."""
    names = ["Rajesh Kumar", "Rajesh Kumar Nair", "Rajesh Sharma",
             "Vikram Rao"]
    ranked = ranked_matches("Rajesh Kumar Singh", names, top_k=3)
    # two names share 2 of 3 tokens (Jaccard >= 0.5) -> both suggested
    assert [n for n, _, _ in ranked] == ["Rajesh Kumar", "Rajesh Kumar Nair"]
    sims = [s for _, s, _ in ranked]
    assert sims == sorted(sims, reverse=True)
    for _, sim, reasons in ranked:
        assert sim >= 0.55 and reasons, "every suggestion cites its reason"
    # the initial-form rule still fires and scores highest
    ranked2 = ranked_matches("Rajesh K.", ["Rajesh Kumar"], top_k=3)
    assert ranked2[0][0] == "Rajesh Kumar"
    assert any("initial" in x for x in ranked2[0][2])
    # deterministic tie-break: same input -> same order
    assert ranked == ranked_matches("Rajesh Kumar Singh", names, top_k=3)


def test_ranked_matches_threshold_and_dedup():
    """Below-threshold names are not suggested; duplicate names dedupe."""
    ranked = ranked_matches("Completely Different Person",
                            ["Rajesh Kumar", "Suresh Yadav",
                             "Suresh Yadav"], top_k=3)
    assert ranked == []
    # identical normalized names score exactly 1.0
    sim, reasons = score_pair("Vikram Rao", "vikram   rao")
    assert sim == 1.0


def test_contextual_signals_shared_identifiers():
    """Shared phone/vehicle/location produce bounded, explained bonuses."""
    cand = {"phone": {"9822044117"}, "location": {"kurla"}}
    ent = {"phone": {"9822044117"}, "vehicle": {"mh01gh9876"},
           "location": {"kurla", "worli"}}
    bonus, reasons = contextual_signals(cand, ent)
    assert bonus == pytest.approx(0.20 + 0.10)  # phone + location, no vehicle
    assert any("phone" in r and "9822044117" in r for r in reasons)
    assert any("location" in r and "kurla" in r for r in reasons)
    assert not any("vehicle" in r for r in reasons)


def test_combine_scores_caps_only_with_context():
    """No context: the name score stands (exact = 1.0). With context:
    capped below certainty and the context is cited in the reasons."""
    total, reasons = combine_scores(1.0, ["normalized names are identical"],
                                    0.0, [])
    assert total == 1.0 and reasons == ["normalized names are identical"]
    total, reasons = combine_scores(0.82, ["all other name tokens are identical"],
                                    0.20, ["same vehicle: mh09ab1234"])
    assert total == 0.99  # 0.82 + 0.20 = 1.02 -> capped
    assert any("contextual" in r for r in reasons)


# --------------------------------------------------------- end-to-end flows

def test_ranked_suggestion_with_context_e2e(client, auth):
    """Real workflow: doc1 confirms person + vehicle + OWNS. doc2 (CSV)
    pairs the SAME vehicle with an initial-form name. The suggestion must
    cite the shared vehicle (a data-supported reason) and be capped below
    certainty. Nothing is auto-merged."""
    case_id = _new_case(client, auth, "context")["id"]
    db = SessionLocal()
    try:
        # -- doc 1: establish confirmed person + vehicle + OWNS ----------
        doc1 = ("SYNTHETIC DEMONSTRATION DATA - phase 2 resolution test.\n"
                "Rajesh Kumar was seen at Kurla on 2026-09-03.\n"
                "Vehicle MH09AB1234 owned by Rajesh Kumar.\n")
        d1 = _upload(client, auth, case_id, "doc1.txt",
                     doc1.encode(), "text/plain")
        docs = _wait_docs_terminal(client, auth, case_id)
        assert docs[0]["processing_status"] == "PROCESSED", docs[0]
        ex = client.get(f"/api/v1/documents/{d1['id']}/extraction",
                        headers=auth).json()
        rajesh = _cand(ex, "person", "Rajesh Kumar")
        vehicle = _cand(ex, "vehicle", "MH09AB1234")
        assert rajesh and vehicle, (
            f"expected candidates, got: "
            f"{[(e['entity_type'], e['candidate_name']) for e in ex['entities']]}")

        queue = client.get(f"/api/v1/cases/{case_id}/review/queue",
                           headers=auth).json()
        _confirm(client, auth, case_id, "entity",
                 [rajesh["id"], vehicle["id"]])
        rels = queue["candidate_relationships"]
        owns = [x for x in rels
                if {x["source_name"], x["target_name"]}
                == {"Rajesh Kumar", "MH09AB1234"}
                and x["relationship_type"] == "OWNS"]
        assert owns, f"expected an OWNS relationship candidate: {rels}"
        # endpoints are accepted, so the relationship may be confirmed
        _confirm(client, auth, case_id, "relationship", [owns[0]["id"]])

        # -- doc 2: CSV pairs the same vehicle with an initial-form name --
        doc2 = "name,vehicle\nR. Kumar,MH09AB1234\n"
        d2 = _upload(client, auth, case_id, "doc2.csv",
                     doc2.encode(), "text/csv")
        docs = _wait_docs_terminal(client, auth, case_id)
        assert docs[-1]["processing_status"] == "PROCESSED", docs[-1]
        ex2 = client.get(f"/api/v1/documents/{d2['id']}/extraction",
                         headers=auth).json()
        r_kumar = _cand(ex2, "person", "R. Kumar")
        assert r_kumar, (
            f"expected candidate 'R. Kumar', got: "
            f"{[(e['entity_type'], e['candidate_name']) for e in ex2['entities']]}")

        # the extraction's ranked match list contains Rajesh Kumar
        matches = [m for m in ex2["matches"]
                   if m["candidate_id"] == r_kumar["id"]]
        assert matches, "expected match suggestions for R. Kumar"
        matches.sort(key=lambda m: m["rank"])
        assert matches[0]["rank"] == 1
        assert matches[0]["existing_entity_name"] == "Rajesh Kumar"
        # the shared vehicle is cited as a data-supported reason
        top_reasons = " | ".join(matches[0]["reasons"])
        assert "same vehicle" in top_reasons, top_reasons
        assert "mh09ab1234" in top_reasons, top_reasons
        # name similarity (0.82) + vehicle bonus (0.20) = 1.02 -> capped
        assert matches[0]["similarity"] == 0.99

        # the candidate's primary match field is the rank-1 row
        assert r_kumar["match"]["id"] == matches[0]["id"]
        assert r_kumar["match"]["rank"] == 1

        # the review queue shows the ranked item with the cited reason
        queue2 = client.get(f"/api/v1/cases/{case_id}/review/queue",
                            headers=auth).json()
        dups = [x for x in queue2["potential_duplicates"]
                if x["id"] == r_kumar["id"]]
        assert dups, "R. Kumar should appear in potential duplicates"
        assert dups[0]["rank"] == 1
        assert "mh09ab1234" in " | ".join(dups[0]["match_reasons"])

        # nothing was auto-confirmed by the suggestions
        ents = client.get(f"/api/v1/cases/{case_id}/entities",
                          headers=auth).json()
        person_names = [e["canonical_name"] for e in ents
                        if e["entity_type"] == "person"]
        assert "R. Kumar" not in person_names
    finally:
        _delete_case(db, case_id)
        db.close()


def test_multi_suggestions_allowed_for_one_candidate(client, auth):
    """A candidate whose name is an exact match for one confirmed entity
    and a strong partial match for another gets TWO ranked suggestions
    (rank 1..N), best first — the schema and API both support it."""
    case_id = _new_case(client, auth, "multi")["id"]
    db = SessionLocal()
    try:
        # two similar confirmed persons: the short and the extended name
        doc1 = ("SYNTHETIC DEMONSTRATION DATA - phase 2 multi-suggestion.\n"
                "Rajesh Kumar was at Fort on 2026-09-04.\n"
                "The suspect was named Rajesh Kumar Nair in an earlier report.\n")
        d1 = _upload(client, auth, case_id, "m1.txt", doc1.encode(),
                     "text/plain")
        _wait_docs_terminal(client, auth, case_id)
        ex = client.get(f"/api/v1/documents/{d1['id']}/extraction",
                        headers=auth).json()
        b1 = _cand(ex, "person", "Rajesh Kumar")
        b2 = _cand(ex, "person", "Rajesh Kumar Nair")
        assert b1 and b2, [e["candidate_name"] for e in ex["entities"]]
        _confirm(client, auth, case_id, "entity", [b1["id"], b2["id"]])

        # the short name appears again in a second document
        doc2 = ("SYNTHETIC DEMONSTRATION DATA - phase 2 multi doc2.\n"
                "Rajesh Kumar was seen near Fort.\n")
        d2 = _upload(client, auth, case_id, "m2.txt", doc2.encode(),
                     "text/plain")
        _wait_docs_terminal(client, auth, case_id)
        ex2 = client.get(f"/api/v1/documents/{d2['id']}/extraction",
                         headers=auth).json()
        c2 = _cand(ex2, "person", "Rajesh Kumar")
        assert c2, [e["candidate_name"] for e in ex2["entities"]]

        matches = sorted(
            (m for m in ex2["matches"] if m["candidate_id"] == c2["id"]),
            key=lambda m: m["rank"])
        # exact match + the extended-name variant, ranked best first
        assert len(matches) == 2, f"expected 2 ranked suggestions: {matches}"
        assert matches[0]["existing_entity_name"] == "Rajesh Kumar"
        assert matches[0]["similarity"] == 1.0
        assert matches[0]["rank"] == 1
        assert matches[1]["existing_entity_name"] == "Rajesh Kumar Nair"
        assert matches[1]["rank"] == 2
        sims = [m["similarity"] for m in matches]
        assert sims == sorted(sims, reverse=True)
    finally:
        _delete_case(db, case_id)
        db.close()


def test_duplicate_upload_creates_no_duplicate_suggestions(client, auth):
    """Idempotency: re-uploading identical bytes is refused, so no second
    document, no double extraction, no duplicate suggestion rows."""
    case_id = _new_case(client, auth, "idem")["id"]
    db = SessionLocal()
    try:
        doc1 = ("SYNTHETIC DEMONSTRATION DATA - phase 2 idempotency.\n"
                "Deepak Chauhan was at Bhiwandi Godown.\n")
        d1 = _upload(client, auth, case_id, "i1.txt", doc1.encode(),
                     "text/plain")
        _wait_docs_terminal(client, auth, case_id)
        ex = client.get(f"/api/v1/documents/{d1['id']}/extraction",
                        headers=auth).json()
        deepak = _cand(ex, "person", "Deepak Chauhan")
        assert deepak, [e["candidate_name"] for e in ex["entities"]]
        _confirm(client, auth, case_id, "entity", [deepak["id"]])

        # second document with the same name -> one suggestion set
        doc2 = ("SYNTHETIC DEMONSTRATION DATA - phase 2 idempotency 2.\n"
                "Deepak Chauhan was sighted again.\n")
        d2 = _upload(client, auth, case_id, "i2.txt", doc2.encode(),
                     "text/plain")
        _wait_docs_terminal(client, auth, case_id)
        ex2 = client.get(f"/api/v1/documents/{d2['id']}/extraction",
                         headers=auth).json()
        c2 = _cand(ex2, "person", "Deepak Chauhan")
        assert c2, [e["candidate_name"] for e in ex2["entities"]]
        before = len([m for m in ex2["matches"]
                      if m["candidate_id"] == c2["id"]])
        assert before >= 1

        # re-uploading the identical bytes is refused -> no new rows
        rr = client.post(f"/api/v1/cases/{case_id}/documents",
                         files={"file": ("i2-copy.txt", doc2, "text/plain")},
                         headers=auth)
        assert rr.status_code == 409, rr.text
        assert rr.json()["error"]["code"] == "DOCUMENT_DUPLICATE"
        ex3 = client.get(f"/api/v1/documents/{d2['id']}/extraction",
                         headers=auth).json()
        after = len([m for m in ex3["matches"]
                     if m["candidate_id"] == c2["id"]])
        assert after == before
    finally:
        _delete_case(db, case_id)
        db.close()
