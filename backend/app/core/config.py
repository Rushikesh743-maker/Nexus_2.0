"""Platform configuration.

All settings come from environment variables (or `backend/.env` in
development). Nothing sensitive is hardcoded: the Supabase keys and the
database credentials must be provided by the environment, and the
repository ships with `.env.example` as the template.

Authentication: NEXUS uses **Supabase Auth** for identity. The backend does
not store passwords or issue its own login tokens — it verifies the
Supabase-issued access token (a JWT) on each request, resolves the Supabase
user UUID to the NEXUS user, and applies NEXUS RBAC from the database.

Database: Supabase PostgreSQL is the primary database. The app is a plain
SQLAlchemy + psycopg client, so it connects to *any* Postgres endpoint —
point ``DATABASE_URL`` at your Supabase Postgres connection string (with
``?sslmode=require``) and run the Alembic migrations. There is no Docker,
no local-Postgres requirement and no graph database: graph intelligence is
computed in-process with NetworkX over the relational data.
"""

from __future__ import annotations

import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/.env — resolved from this file's location, not the CWD, so the
# settings are identical whether the app starts via run.py or pytest from
# the repository root.
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class Settings(BaseSettings):
    """Application settings, read once per process."""

    model_config = SettingsConfigDict(
        env_file=os.path.join(_BACKEND_DIR, ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # -- application -----------------------------------------------------
    app_name: str = "NEXUS"
    app_version: str = "0.2.0"
    app_env: str = "development"          # development | staging | production

    # -- platform database (Supabase PostgreSQL) ---------------------------
    # Primary database is Supabase PostgreSQL. Set DATABASE_URL to your
    # Supabase Postgres connection string, e.g.
    #   postgresql+psycopg://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres?sslmode=require
    # (use the *session-mode* pooler port 5432 so SQLAlchemy's connection
    #  pooling works normally; see README). The value below is a zero-config
    # LOCAL DEVELOPMENT fallback only — any real deployment sets DATABASE_URL
    # to its Supabase (or other managed Postgres) connection string.
    database_url: str = "postgresql+psycopg://nexus:nexus@127.0.0.1:5432/nexus"

    # -- Supabase project (auth + storage) ----------------------------------
    # SUPABASE_URL is the project URL (https://<ref>.supabase.co). It is the
    # base for (a) verifying Supabase Auth access tokens (issuer + JWKS) and
    # (b) the Supabase Storage S3 endpoint when S3_ENDPOINT_URL is not set
    # explicitly (<SUPABASE_URL>/storage/v1/s3). The service-role/secret key
    # is server-side only and must NEVER be sent to the frontend.
    supabase_url: str = ""
    supabase_anon_key: str = ""           # public/publishable key (client-side use; not used by the backend)
    supabase_service_role_key: str = ""   # elevated, server-side key (bypasses RLS) — NEVER to the frontend

    # -- Supabase Auth (token verification) ---------------------------------
    # NEXUS verifies Supabase-issued access tokens; it does not issue its own.
    #   * Asymmetric projects (RS256/ES256, the recommended default): the
    #     public keys are fetched from <SUPABASE_URL>/auth/v1/.well-known/
    #     jwks.json — no secret is needed here.
    #   * Legacy HS256 projects: set SUPABASE_JWT_SECRET to the project's JWT
    #     secret (Project Settings → JWT) so the backend can verify tokens
    #     locally. The algorithm is auto-detected from each token's header.
    supabase_jwt_secret: str = ""         # only required for HS256 (legacy) projects

    # -- LLM (prepared, not required) ---------------------------------------
    # Empty llm_provider => deterministic rule-based extraction only. When a
    # provider is configured (e.g. an OpenAI-compatible chat endpoint via
    # llm_base_url), extraction uses it behind the same validation contract.
    llm_provider: str = ""                # e.g. "openai", "anthropic", "local"
    llm_api_key: str = ""
    llm_model: str = ""
    llm_base_url: str = ""                # OpenAI-compatible API root (optional)

    # -- document processing (stage 2) ---------------------------------------
    storage_root: str = ""                # empty => backend/storage
    max_upload_mb: int = 10               # upload size limit
    extraction_max_chars: int = 200_000   # cap for stored raw text
    extraction_max_rows: int = 2_000      # cap for stored CSV rows

    # -- storage backend (phase 1) --------------------------------------------
    # "local" (default, development: filesystem under storage_root) or
    # "s3" (any S3-compatible object store — Supabase Storage, MinIO, R2,
    # AWS S3, ...). The application only ever sees object keys — never a
    # local path. For Supabase Storage, set STORAGE_BACKEND=s3,
    # S3_BUCKET=<your private bucket>, SUPABASE_URL=<project url> and the
    # S3 credentials (the service-role/secret key authorises private access);
    # the endpoint is then derived automatically.
    storage_backend: str = "local"        # local | s3
    s3_endpoint_url: str = ""             # explicit S3 endpoint; else derived from SUPABASE_URL
    s3_bucket: str = ""
    s3_prefix: str = ""                   # key prefix inside the bucket
    s3_region: str = ""                   # empty => provider default
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""        # empty => falls back to SUPABASE_SERVICE_ROLE_KEY

    # -- OCR (phase 1) ----------------------------------------------------------
    # OCR of scanned PDF pages / image uploads. Degrades honestly: when
    # tesseract (or the PDF rasterizer) is unavailable, a scanned page
    # fails with a clear message instead of silently producing nothing.
    ocr_enabled: bool = True
    ocr_dpi: int = 200

    # -- background document worker (phase 1) ----------------------------------
    # In development the worker runs inside the API process; in production
    # run it separately (`python -m app.workers.document_worker`) and set
    # WORKER_ENABLED=false on the API nodes if you want them pure web.
    worker_enabled: bool = True
    worker_poll_interval: float = 0.25    # seconds between empty-queue polls
    worker_batch_size: int = 5            # jobs claimed per poll
    worker_stuck_timeout_minutes: int = 15  # honest failure for a dead pipeline

    # -- security (phase 1) ------------------------------------------------------
    # Comma-separated allowed CORS origins. Empty in development => the
    # current permissive behaviour; in production an empty value means NO
    # cross-origin access (explicit origins must be listed).
    cors_origins: str = ""
    # When set, served as the Content-Security-Policy response header.
    security_csp: str = (
        "default-src 'self'; script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
        "font-src 'self' data:; connect-src 'self'; "
        "frame-ancestors 'none'; base-uri 'self'; form-action 'self'")

    # -- observability (phase 1) ---------------------------------------------------
    # "text" (default, human-readable) or "json" (one JSON object per line)
    log_format: str = "text"

    # -- copilot LLM provider (stage 5, optional) ---------------------------
    # Empty gemini_api_key => the copilot runs in fully deterministic mode
    # (offline, no LLM, and it says so in every answer). When configured, the
    # model writes the answer *prose* only: claims, citations and confidence
    # always come from the deterministic layer, the prompt is a bounded
    # context (never the database or graph), and every model output is
    # validated (citations ⊆ retrieved records, neutral language, no unknown
    # names) before it is served — any violation falls back honestly.
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    gemini_timeout_seconds: float = 20.0

    @property
    def supabase_configured(self) -> bool:
        return bool(self.supabase_url)

    @property
    def supabase_auth_issuer(self) -> str:
        """The expected ``iss`` claim of a Supabase access token."""
        return self.supabase_url.rstrip("/") + "/auth/v1"

    @property
    def effective_s3_endpoint_url(self) -> str:
        """The S3 endpoint to use.

        An explicit ``S3_ENDPOINT_URL`` always wins. Otherwise, when a
        Supabase project URL is set, the Supabase Storage S3 protocol
        endpoint is derived from it — so pointing NEXUS at Supabase Storage
        only needs ``SUPABASE_URL`` + ``S3_BUCKET`` + the S3 credentials.
        """
        if self.s3_endpoint_url:
            return self.s3_endpoint_url
        if self.supabase_url:
            base = self.supabase_url.rstrip("/")
            return f"{base}/storage/v1/s3"
        return ""

    @property
    def effective_s3_secret_access_key(self) -> str:
        """The S3 secret. An explicit ``S3_SECRET_ACCESS_KEY`` wins; for a
        Supabase project the server-side service-role/secret key is the
        credential that authorises private-bucket access."""
        if self.s3_secret_access_key:
            return self.s3_secret_access_key
        return self.supabase_service_role_key

    @property
    def gemini_configured(self) -> bool:
        return bool(self.gemini_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
