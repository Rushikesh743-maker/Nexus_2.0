"""Supabase Auth token verification.

NEXUS does not issue its own login tokens and stores no passwords. Identity
is provided by **Supabase Auth**: the React client authenticates with
Supabase, and every protected request carries the Supabase access token (a
JWT) in the ``Authorization: Bearer <token>`` header. This module verifies
that token and returns its claims.

Two signing schemes are supported, **auto-detected from each token's
header**:

* **Asymmetric** (RS256 / ES256 / EdDSA) — the recommended Supabase default.
  The project's public keys are fetched once and cached from
  ``<SUPABASE_URL>/auth/v1/.well-known/jwks.json``; no secret is required.
* **Symmetric** (HS256) — legacy projects. Verified with
  ``SUPABASE_JWT_SECRET`` (the project's JWT secret).

In every case the standard Supabase claims are enforced:

* ``iss`` == ``<SUPABASE_URL>/auth/v1``
* ``aud`` == ``"authenticated"``
* a valid, unexpired ``exp``
* a non-empty ``sub`` (the Supabase user UUID — the stable identity)

The **NEXUS role is never read from the token.** The token's ``role`` claim
is the *Postgres* role (always ``"authenticated"``), which is not the NEXUS
role. The NEXUS role is loaded from the database by the caller, so a client
cannot grant itself a role by tampering with the token or a request header.
"""

from __future__ import annotations

import logging
from typing import Any

import jwt

from ..core.config import get_settings
from ..core.errors import unauthenticated

logger = logging.getLogger("nexus.auth")

# Algorithms we are willing to verify. Anything else is rejected outright
# (this also blocks algorithm-confusion attacks, since the token header's
# ``alg`` is only used to *select* the key, then re-checked against this set).
_SUPPORTED_ALGS = {"HS256", "RS256", "ES256", "EdDSA"}

# Cache of JWKS clients, keyed by the JWKS URL (i.e. by Supabase project).
# PyJWKClient itself caches the fetched key set for a bounded interval.
_jwks_clients: dict[str, Any] = {}


def extract_bearer_token(authorization: str | None) -> str | None:
    """Pull the token out of an ``Authorization: Bearer <token>`` header.

    Returns ``None`` when the header is absent, not a bearer scheme, or
    carries no token.
    """
    if not authorization:
        return None
    parts = authorization.strip().split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1].strip()
    return token or None


def _jwks_client(jwks_uri: str):
    client = _jwks_clients.get(jwks_uri)
    if client is None:
        client = jwt.PyJWKClient(jwks_uri, cache_keys=True)
        _jwks_clients[jwks_uri] = client
    return client


def clear_jwks_cache() -> None:
    """Drop cached JWKS clients (tests, or a settings/SUPABASE_URL change)."""
    _jwks_clients.clear()


def verify_supabase_token(token: str) -> dict:
    """Verify a Supabase access token; return its claims or raise 401.

    Raises the structured 401 (``UNAUTHENTICATED``) on any failure — missing
    Supabase config, malformed token, bad signature, wrong issuer/audience,
    or expiry. A valid token yields its decoded claims (``sub`` is the
    Supabase user UUID).
    """
    settings = get_settings()
    if not settings.supabase_url:
        # Supabase is not configured at all: authentication is impossible.
        # (Never fall back to trusting anything — fail closed.)
        unauthenticated()

    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError:
        unauthenticated()

    alg = header.get("alg")
    if alg not in _SUPPORTED_ALGS:
        unauthenticated()

    try:
        if alg == "HS256":
            if not settings.supabase_jwt_secret:
                # HS256 token but no shared secret configured: cannot verify.
                unauthenticated()
            key: Any = settings.supabase_jwt_secret
        else:
            jwks_uri = (settings.supabase_url.rstrip("/")
                        + "/auth/v1/.well-known/jwks.json")
            key = _jwks_client(jwks_uri).get_signing_key_from_jwt(token).key

        payload = jwt.decode(
            token,
            key,
            algorithms=[alg],
            audience="authenticated",
            issuer=settings.supabase_auth_issuer,
            options={"require": ["exp", "sub", "aud", "iss"]},
        )
    except jwt.PyJWTError as exc:
        logger.info("JWT verification failed: %s (%s)", exc.__class__.__name__, exc)
        unauthenticated()
    except Exception as exc:  # noqa: BLE001 — any JWKS/decoding failure = 401
        logger.info("Supabase token verification failed: %s (%s)", exc.__class__.__name__, exc)
        unauthenticated()

    if not payload.get("sub"):
        unauthenticated()
    return payload


def verify_supabase_bearer(authorization: str | None) -> dict:
    token = extract_bearer_token(authorization)
    logger.debug('Authorization header present: %s', bool(authorization))
    logger.debug('Bearer token extracted: %s', bool(token))
    logger.debug('Bearer token length: %d', len(token) if token else 0)
    if not token:
        unauthenticated()
    # Verify token and get claims
    claims = verify_supabase_token(token)
    # Log safe claim details
    logger.debug('JWT verification SUCCESS')
    logger.debug('JWT claims sub: %s', claims.get('sub'))
    logger.debug('JWT claims iss: %s', claims.get('iss'))
    logger.debug('JWT claims aud: %s', claims.get('aud'))
    logger.debug('JWT claims exp: %s', claims.get('exp'))
    return claims

