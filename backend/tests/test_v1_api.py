"""Tests for the v1 platform API (health, auth, cases).

These run against the development PostgreSQL (DATABASE_URL in backend/.env).
Authentication is Supabase Auth: the shared conftest mints HS256 Supabase
tokens for a fixed user per role. The `client` and role fixtures
(`investigator`, `analyst`, `supervisor`, `admin`) come from conftest. The
analysis tests in this directory run independently; both suites share one
session-scoped app so the pipeline is built once.
"""

import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app.core.database import SessionLocal  # noqa: E402
from auth_helpers import ROLE_IDENTITIES, bearer, mint_supabase_token  # noqa: E402


# --------------------------------------------------------------------- health

class TestHealth:
    def test_health_200_and_shape(self, client):
        r = client.get("/api/v1/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] in ("ok", "degraded")
        assert body["version"]
        assert body["synthetic_data_only"] is True
        assert body["database"]["connected"] is True

    def test_health_has_no_graph_database_dependency(self, client):
        """NEXUS no longer depends on a graph database (Neo4j was removed);
        graph intelligence runs in-process with NetworkX. The health
        payload must not expose a neo4j status key."""
        body = client.get("/api/v1/health").json()
        assert "neo4j" not in body


# ----------------------------------------------------------------------- auth

class TestAuth:
    def test_login_endpoint_removed(self, client):
        # NEXUS no longer issues its own login tokens — authentication is
        # Supabase Auth, so the credential login endpoint must be gone.
        r = client.post("/api/v1/auth/login",
                        json={"email": "a@b.c", "password": "whatever"})
        assert r.status_code in (404, 405)

    def test_me_without_token(self, client):
        r = client.get("/api/v1/auth/me")
        assert r.status_code == 401
        assert r.json()["error"]["code"] == "UNAUTHENTICATED"

    def test_me_with_garbage_token(self, client):
        r = client.get("/api/v1/auth/me",
                       headers={"Authorization": "Bearer not.a.jwt"})
        assert r.status_code == 401
        assert r.json()["error"]["code"] == "UNAUTHENTICATED"

    def test_me_with_wrong_secret_token_rejected(self, client):
        # Signed with a different secret: the signature does not verify.
        token = mint_supabase_token(ROLE_IDENTITIES["INVESTIGATOR"]["sub"],
                                    secret="a-different-secret")
        assert client.get("/api/v1/auth/me",
                          headers=bearer(token)).status_code == 401

    def test_me_with_wrong_issuer_token_rejected(self, client):
        token = mint_supabase_token(ROLE_IDENTITIES["INVESTIGATOR"]["sub"],
                                    issuer="https://evil.example/auth/v1")
        assert client.get("/api/v1/auth/me",
                          headers=bearer(token)).status_code == 401

    def test_me_with_expired_token_rejected(self, client):
        token = mint_supabase_token(ROLE_IDENTITIES["INVESTIGATOR"]["sub"],
                                    ttl_seconds=-10)
        assert client.get("/api/v1/auth/me",
                          headers=bearer(token)).status_code == 401

    def test_me_with_valid_token_returns_db_role(self, client, investigator):
        r = client.get("/api/v1/auth/me", headers=investigator)
        assert r.status_code == 200
        assert r.json()["email"] == ROLE_IDENTITIES["INVESTIGATOR"]["email"]
        # The role is the NEXUS role from the database.
        assert r.json()["role"] == "INVESTIGATOR"

    def test_token_role_claim_has_no_effect(self, client):
        # A token that CLAIMS role=ADMIN but whose sub is the ANALYST test
        # user must resolve to the DB role (ANALYST), not the claimed role —
        # a client cannot escalate by tampering with the token.
        token = mint_supabase_token(ROLE_IDENTITIES["ANALYST"]["sub"], role="ADMIN")
        r = client.get("/api/v1/auth/me", headers=bearer(token))
        assert r.status_code == 200
        assert r.json()["role"] == "ANALYST"
        # ...and it must not gain supervisor rights.
        assert client.get("/api/v1/users",
                          headers=bearer(token)).status_code == 403

    def test_unknown_supabase_identity_rejected(self, client):
        # A validly-signed token for a Supabase UUID with no NEXUS profile.
        token = mint_supabase_token("00000000-0000-4000-8000-000000000000")
        assert client.get("/api/v1/auth/me",
                          headers=bearer(token)).status_code == 401

    def test_users_requires_supervisor(self, client, investigator, supervisor, admin):
        assert client.get("/api/v1/users", headers=investigator).status_code == 403
        for headers in (supervisor, admin):
            r = client.get("/api/v1/users", headers=headers)
            assert r.status_code == 200
            emails = {u["email"] for u in r.json()}
            # The four fixed test users must all be visible to a supervisor.
            assert {ident["email"] for ident in ROLE_IDENTITIES.values()} <= emails


# ---------------------------------------------------------------------- cases

class TestCases:
    def test_list_contains_seeded_cases(self, client, investigator):
        r = client.get("/api/v1/cases", headers=investigator)
        assert r.status_code == 200
        numbers = {c["case_number"] for c in r.json()}
        assert {"CASE-2026-001", "CASE-2026-002", "CASE-2026-003"} <= numbers
        for item in r.json():
            assert item["is_synthetic"] is True
            # the stage-4 smoke-verification demo case is intentionally
            # empty (INSUFFICIENT_CONFIRMED_DATA demonstration)
            if item["case_number"] == "CASE-DEMO-EMPTY-01":
                assert item["counts"]["entities"] == 0
                continue
            assert item["counts"]["entities"] > 0

    def test_detail_shape(self, client, investigator):
        r = client.get("/api/v1/cases", headers=investigator)
        first = r.json()[0]
        d = client.get(f"/api/v1/cases/{first['id']}", headers=investigator)
        assert d.status_code == 200
        body = d.json()
        for key in ("counts", "key_entities", "cross_case_links", "latest_events"):
            assert key in body
        assert body["counts"]["relationships"] > 0

    def test_unknown_case_404_structured(self, client, investigator):
        r = client.get("/api/v1/cases/999999", headers=investigator)
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "CASE_NOT_FOUND"

    def test_case_requires_auth(self, client):
        assert client.get("/api/v1/cases").status_code == 401

    def test_create_case_as_investigator(self, client, investigator):
        r = client.post("/api/v1/cases", headers=investigator, json={
            "case_number": "TEST-2026-9001", "title": "Test case (automated)",
            "priority": "LOW"})
        assert r.status_code == 201, r.text
        assert r.json()["case_number"] == "TEST-2026-9001"
        # clean up so reruns stay green
        self._delete(client, investigator, r.json()["id"])

    def test_create_case_rejects_bad_number(self, client, investigator):
        r = client.post("/api/v1/cases", headers=investigator,
                        json={"case_number": "bad number", "title": "x" * 5})
        assert r.status_code == 422

    def test_create_case_as_analyst_forbidden(self, client, analyst):
        r = client.post("/api/v1/cases", headers=analyst, json={
            "case_number": "TEST-2026-9002", "title": "Analysts may not open cases"})
        assert r.status_code == 403
        assert r.json()["error"]["code"] == "FORBIDDEN"

    def test_duplicate_case_number_conflict(self, client, investigator):
        r1 = client.post("/api/v1/cases", headers=investigator, json={
            "case_number": "TEST-2026-9003", "title": "First"})
        assert r1.status_code == 201
        try:
            r2 = client.post("/api/v1/cases", headers=investigator, json={
                "case_number": "TEST-2026-9003", "title": "Duplicate"})
            assert r2.status_code == 409
            assert r2.json()["error"]["code"] == "CASE_EXISTS"
        finally:
            self._delete(client, investigator, r1.json()["id"])

    def test_case_sub_resources(self, client, investigator):
        r = client.get("/api/v1/cases", headers=investigator)
        case = next(c for c in r.json() if c["case_number"] == "CASE-2026-001")
        for resource, minimum in (("documents", 2), ("entities", 5),
                                  ("relationships", 3), ("evidence", 3),
                                  ("timeline", 3), ("locations", 2),
                                  ("hypotheses", 1), ("contradictions", 1),
                                  ("gaps", 1)):
            rr = client.get(f"/api/v1/cases/{case['id']}/{resource}",
                            headers=investigator)
            assert rr.status_code == 200, resource
            assert len(rr.json()) >= minimum, f"{resource} has {len(rr.json())}"

    def test_relationships_carry_labels(self, client, investigator):
        r = client.get("/api/v1/cases", headers=investigator)
        case = next(c for c in r.json() if c["case_number"] == "CASE-2026-001")
        rels = client.get(f"/api/v1/cases/{case['id']}/relationships",
                          headers=investigator).json()
        assert rels[0]["source_label"] and rels[0]["target_label"]

    def test_create_simulation(self, client, investigator):
        r = client.get("/api/v1/cases", headers=investigator)
        case = next(c for c in r.json() if c["case_number"] == "CASE-2026-001")
        r = client.post(f"/api/v1/cases/{case['id']}/simulations", headers=investigator,
                        json={"name": "Automated test simulation",
                              "description": "Created by pytest; safe to delete."})
        assert r.status_code == 201
        assert r.json()["name"] == "Automated test simulation"

    def test_meridian_import_present(self, client, investigator):
        """The existing analysis corpus must be projected into the new model."""
        r = client.get("/api/v1/cases", headers=investigator)
        mer = [c for c in r.json() if c["case_number"] == "CASE-2026-021"]
        if not mer:
            pytest.skip("data/raw corpus absent in this environment")
        m = mer[0]
        assert m["counts"]["entities"] >= 15
        assert m["counts"]["relationships"] >= 100
        assert m["counts"]["contradictions"] >= 1
        assert m["counts"]["hypotheses"] >= 1
        assert m["counts"]["gaps"] >= 1

    def test_cross_case_links(self, client, investigator):
        """Cases sharing entity names must be surfaced as cross-case links."""
        r = client.get("/api/v1/cases", headers=investigator)
        case = next(c for c in r.json() if c["case_number"] == "CASE-2026-001")
        body = client.get(f"/api/v1/cases/{case['id']}", headers=investigator).json()
        linked_numbers = {l["case_number"] for l in body["cross_case_links"]}
        assert "CASE-2026-003" in linked_numbers  # Rohan Deshmukh overlap

    @staticmethod
    def _delete(client: TestClient, headers: dict, case_id: int) -> None:
        from sqlalchemy import delete

        from app.models import Case

        db = SessionLocal()
        try:
            db.execute(delete(Case).where(Case.id == case_id))
            db.commit()
        finally:
            db.close()


# -------------------------------------------------------------------- copilot

class TestCopilot:
    def test_status_is_honest(self, client, investigator):
        r = client.get("/api/v1/copilot", headers=investigator)
        assert r.status_code == 200
        body = r.json()
        # stage 5: the copilot is live — the capability statement must
        # say so (it previously said "foundation / lands later")
        assert body["stage"] == "stage-5"
        assert body["planned"]
        assert any("natural-language" in a for a in body["available"])
