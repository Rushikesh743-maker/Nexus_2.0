"""
Shared fixtures.

The graph build reads the whole corpus off disk and runs extraction and
resolution, so it is built once per session and shared. Every test treats it as
read-only — a test that mutated it would silently change the others, and the
engine's own contract is that it never writes to the graph.

Authentication is Supabase Auth. These fixtures verify tokens the way the app
does, offline: they mint HS256 Supabase-format access tokens (signed with the
configured test secret) for a fixed set of NEXUS users, one per role. The
token's ``sub`` is a stable UUID per role; the NEXUS role is always read from
the database, never from the token.
"""

import os
import sys
import uuid

import pytest

# --- Supabase Auth test configuration (before any app import) -------------
# The suite verifies tokens offline against a fixed fake project. These
# defaults stand in for a real Supabase project; a real `.env` can override
# them (mint and verify both read the same configured secret, so they always
# agree).
os.environ.setdefault("SUPABASE_URL", "http://supabase.test")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-supabase-jwt-secret")

import socket


def _is_pg_reachable() -> bool:
    try:
        s = socket.socket()
        s.settimeout(0.4)
        res = s.connect_ex(("127.0.0.1", 5432))
        s.close()
        return res == 0
    except Exception:
        return False


if not _is_pg_reachable():
    test_db = os.path.abspath(os.path.join(os.path.dirname(__file__), "nexus_test.db")).replace("\\", "/")
    os.environ["DATABASE_URL"] = f"sqlite:///{test_db}"

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app.graph.build import build_graph                # noqa: E402
from app.intelligence.contradiction_engine import ContradictionEngine  # noqa: E402
from auth_helpers import ROLE_IDENTITIES, mint_supabase_token, bearer  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_provider_and_settings():
    """Clear lru-cached settings/extraction-provider state around every test.

    `test_extraction._patch_llm` sets LLM_* env vars and clears get_settings
    for the LLM contract tests; without this, a later test in a *different*
    file (e.g. document processing) could inherit the stale LLM provider
    selection. Clearing both caches per test makes the suite order-
    independent. No assertions are weakened — this only resets process-level
    memoization.
    """
    from app.core.config import get_settings
    from app.services.entity_extraction import get_extraction_provider

    get_settings.cache_clear()
    get_extraction_provider.cache_clear()
    yield
    get_settings.cache_clear()
    get_extraction_provider.cache_clear()


@pytest.fixture(scope="session")
def _supabase_test_users():
    """Ensure the fixed NEXUS users (one per role) exist with their UUIDs.

    Creates them if missing; if a row with the same email already exists it is
    aligned to the expected role/UUID so the fixtures stay idempotent across
    reruns.
    """
    from sqlalchemy import select

    from app.core.database import SessionLocal, db_ready, init_database
    from app.models import User

    assert db_ready() or init_database(), "PostgreSQL must be reachable for v1 tests"
    db = SessionLocal()
    try:
        for label, ident in ROLE_IDENTITIES.items():
            user = db.scalars(select(User).where(
                User.email == ident["email"])).first()
            if user is None:
                db.add(User(email=ident["email"], name=f"Test {label.title()}",
                            role=ident["role"], officer_id=None,
                            supabase_id=uuid.UUID(ident["sub"])))
            else:
                user.role = ident["role"]
                user.supabase_id = uuid.UUID(ident["sub"])
                user.is_active = True
        db.commit()
    finally:
        db.close()


@pytest.fixture(scope="session")
def _client(_supabase_test_users):
    """One TestClient for the whole session; startup (DB init + seed) runs once."""
    from fastapi.testclient import TestClient

    from app.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def client(_client):
    return _client


@pytest.fixture(scope="session")
def analyst(_supabase_test_users):
    return bearer(mint_supabase_token(ROLE_IDENTITIES["ANALYST"]["sub"]))


@pytest.fixture(scope="session")
def investigator(_supabase_test_users):
    return bearer(mint_supabase_token(ROLE_IDENTITIES["INVESTIGATOR"]["sub"]))


@pytest.fixture(scope="session")
def investigator_b(_supabase_test_users):
    """A second investigator (distinct identity, same role) for isolation tests."""
    return bearer(mint_supabase_token(ROLE_IDENTITIES["INVESTIGATOR_B"]["sub"]))


@pytest.fixture(scope="session")
def auth(investigator):
    """Alias for `investigator` — the primary non-admin test identity.

    Several test modules name the investigator headers `auth`; this keeps them
    working against the shared Supabase-token fixtures without local fixtures.
    """
    return investigator


@pytest.fixture(scope="session")
def supervisor(_supabase_test_users):
    return bearer(mint_supabase_token(ROLE_IDENTITIES["SUPERVISOR"]["sub"]))


@pytest.fixture(scope="session")
def admin(_supabase_test_users):
    return bearer(mint_supabase_token(ROLE_IDENTITIES["ADMIN"]["sub"]))


# ------------------------------------------------------------- graph fixtures
@pytest.fixture(scope="session")
def case_graph():
    return build_graph()


@pytest.fixture(scope="session")
def engine_result(case_graph):
    engine = ContradictionEngine(case_graph)
    return engine.run_all(), engine.skipped


@pytest.fixture(scope="session")
def findings(engine_result):
    return engine_result[0]


@pytest.fixture(scope="session")
def skipped(engine_result):
    return engine_result[1]


def by_type(findings, ctype):
    return [f for f in findings if f["type"] == ctype]
