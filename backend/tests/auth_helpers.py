"""Supabase Auth test helpers.

NEXUS authenticates with Supabase Auth. These helpers mint HS256
Supabase-format access tokens for the test suite and define a fixed identity
per NEXUS role. They are imported by ``conftest.py`` (to build the role
fixtures) and by individual tests (to mint special tokens, e.g. one signed
with the wrong secret, to prove it is rejected).

The token's ``sub`` is the Supabase user UUID; the NEXUS role is whatever the
database assigns to that user — never what the token claims.
"""

from __future__ import annotations

import time

import jwt as pyjwt

# Stable identity per NEXUS role. `sub` (the Supabase user UUID) is fixed so a
# token is reproducible. The corresponding NEXUS users are created by the
# conftest `_supabase_test_users` fixture. There are two investigators so
# tests can verify isolation between same-role users (a case is visible to its
# owner + platform cases, not to every investigator).
ROLE_IDENTITIES = {
    "ANALYST":        {"sub": "a1111111-1111-4111-8111-111111111111",
                       "email": "test-analyst@nexus.local",
                       "role": "ANALYST"},
    "INVESTIGATOR":   {"sub": "a2222222-2222-4222-8222-222222222222",
                       "email": "test-investigator@nexus.local",
                       "role": "INVESTIGATOR"},
    "INVESTIGATOR_B": {"sub": "a2333333-3333-4333-8333-333333333333",
                       "email": "test-investigator-b@nexus.local",
                       "role": "INVESTIGATOR"},
    "SUPERVISOR":     {"sub": "a3333333-3333-4333-8333-333333333333",
                       "email": "test-supervisor@nexus.local",
                       "role": "SUPERVISOR"},
    "ADMIN":          {"sub": "a4444444-4444-4444-8444-444444444444",
                       "email": "test-admin@nexus.local",
                       "role": "ADMIN"},
}


def mint_supabase_token(sub, *, role="authenticated", secret=None,
                        audience=None, issuer=None, ttl_seconds=3600, extra=None):
    """Mint a Supabase-format access token (HS256).

    By default it is signed with the configured Supabase JWT secret and carries
    the standard Supabase claims (``iss`` from the configured project URL,
    ``aud="authenticated"``). Pass a different ``secret`` / ``issuer`` /
    ``audience`` to mint a token the app must reject.
    """
    from app.core.config import get_settings

    settings = get_settings()
    secret = secret if secret is not None else settings.supabase_jwt_secret
    audience = audience or "authenticated"
    issuer = issuer or (settings.supabase_url.rstrip("/") + "/auth/v1")
    now = int(time.time())
    payload = {
        "sub": sub, "aud": audience, "iss": issuer, "role": role,
        "iat": now, "exp": now + ttl_seconds,
    }
    if extra:
        payload.update(extra)
    return pyjwt.encode(payload, secret, algorithm="HS256")


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def role_headers(role: str) -> dict:
    """Bearer headers for the fixed test user of the given NEXUS role."""
    ident = ROLE_IDENTITIES[role]
    return bearer(mint_supabase_token(ident["sub"]))
