"""Phase 1 — production foundation tests.

Covers the pieces added on top of the Stage 6/7 platform:

* background document-processing jobs (upload -> job -> worker -> result)
* OCR (image uploads + scanned PDF pages; honest failure when disabled or
  when the OCR dependency is unavailable — never a silent empty result)
* storage abstraction (local filesystem + S3-compatible object store,
  upload validation incl. image magic bytes)
* Alembic migrations (fresh database + existing database, data preserved)
* security (login rate limiting, security headers, CORS config, no real
  credentials in .env.example)
* observability (request ids, /health with db+storage+worker, /readyz)
* pagination (opt-in limit/offset + X-Total-Count headers)

Everything runs against the real development PostgreSQL, like the rest of
the suite. Synthetic fixtures are generated locally (fictional names and
numbers, labelled SYNTHETIC DEMONSTRATION DATA).
"""

import io
import json
import os
import subprocess
import sys
import time
import uuid

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.database import SessionLocal, engine  # noqa: E402

FIXTURES = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "documents"))

RUN = time.strftime("%Y%m%d%H%M%S") + uuid.uuid4().hex[:6]


# ------------------------------------------------------------------ fixtures
# `client` and `auth` come from conftest (Supabase tokens).


def _new_case(client, headers, tag):
    """Create a throwaway case (case_number must match the platform's
    ^[A-Z]{2,8}-\\d{4}-\\d{3,}$ pattern); retry on the (astronomically
    unlikely) number collision."""
    for _ in range(3):
        case_number = f"PRD-2026-{uuid.uuid4().int % 10**9:09d}"
        r = client.post("/api/v1/cases",
                        json={"case_number": case_number,
                              "title": f"phase-1 test {tag} {RUN}"},
                        headers=headers)
        if r.status_code == 201:
            return r.json()["id"]
        assert r.status_code != 409, f"case number collision: {r.text}"
    raise AssertionError(f"could not create a case: {r.text}")


def _delete_case(db, case_id):
    from sqlalchemy import text
    db.execute(text('DELETE FROM "case" WHERE id = :i'), {"i": case_id})
    db.commit()


def _wait_processed(client, headers, case_id, timeout=120):
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


def _make_scan_fixtures() -> tuple[str, str, str]:
    """PNG image + image-only (no text layer) PDF + TXT with the same
    fictional content. Returns (png_path, pdf_path, txt_path). The files
    are written to the shared fixtures directory (idempotent)."""
    png = os.path.join(FIXTURES, "scan_fixture.png")
    pdf = os.path.join(FIXTURES, "scan_fixture.pdf")
    txt = os.path.join(FIXTURES, "scan_fixture.txt")
    lines = [
        "FIR (scanned copy) - SYNTHETIC DEMONSTRATION DATA",
        "On 2026-09-03 10:00, Suresh Yadav was seen at Chembur.",
        "On 2026-09-03 10:20, Suresh Yadav was seen at Kurla.",
        "Mobile 9000000955 was recovered from the scene.",
        "Vehicle MH09AB1234 was parked nearby.",
    ]
    if not (os.path.isfile(png) and os.path.isfile(pdf)
            and os.path.isfile(txt)):
        from PIL import Image, ImageDraw, ImageFont

        img = Image.new("RGB", (1400, 700), "white")
        d = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 40)
        except OSError:
            font = ImageFont.load_default(size=32)
        y = 60
        for ln in lines:
            d.text((80, y), ln, fill="black", font=font)
            y += 110
        os.makedirs(FIXTURES, exist_ok=True)
        img.save(png)

        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        c = canvas.Canvas(pdf, pagesize=A4)
        c.drawImage(png, 60, 300, width=480, height=240)
        c.save()

        with open(txt, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
    return png, pdf, txt


@pytest.fixture(scope="session")
def scan_fixtures():
    return _make_scan_fixtures()


# ------------------------------------------------------------ 1. job lifecycle

def test_upload_creates_real_processing_job(client, auth):
    """An upload creates a QUEUED job and returns immediately; the worker
    completes it. No BackgroundTasks magic — a job row is the source of
    truth."""
    cid = _new_case(client, auth, "job")
    db = SessionLocal()
    try:
        body = f"# phase-1 job test {RUN}\nVikram Sethi was seen at Worli.\n"
        r = client.post(f"/api/v1/cases/{cid}/documents",
                        files={"file": ("job_test.txt", body.encode(),
                                        "text/plain")},
                        headers=auth)
        assert r.status_code == 201, r.text
        doc = r.json()
        assert doc["processing_status"] in ("UPLOADED", "PROCESSING",
                                            "PROCESSED")
        job = doc["processing_job"]
        assert job is not None and job["id"]
        assert job["status"] in ("QUEUED", "PROCESSING", "COMPLETED")
        assert job["attempts"] >= 0  # 0 until the worker claims it

        docs = _wait_processed(client, auth, cid)
        assert len(docs) == 1
        assert docs[0]["processing_status"] == "PROCESSED", docs[0]
        # the same job row ended COMPLETED with a real attempt count
        assert docs[0]["processing_job"]["status"] == "COMPLETED"
        assert docs[0]["processing_job"]["attempts"] >= 1

        # extraction produced CANDIDATES (not confirmed facts)
        ex = client.get(f"/api/v1/documents/{docs[0]['id']}/extraction",
                        headers=auth)
        assert ex.status_code == 200
        names = [e["candidate_name"] for e in ex.json()["entities"]]
        assert any("Vikram Sethi" in n for n in names)
        # nothing was auto-confirmed
        ents = client.get(f"/api/v1/cases/{cid}/entities",
                          headers=auth).json()
        assert ents == []
    finally:
        _delete_case(db, cid)
        db.close()


def test_duplicate_upload_is_rejected(client, auth, scan_fixtures):
    """Same bytes (sha256) in the same case => 409, not a second copy."""
    png = scan_fixtures[0]
    cid = _new_case(client, auth, "dup")
    db = SessionLocal()
    try:
        data = open(png, "rb").read()
        r1 = client.post(f"/api/v1/cases/{cid}/documents",
                         files={"file": ("a.png", data, "image/png")},
                         headers=auth)
        assert r1.status_code == 201, r1.text
        r2 = client.post(f"/api/v1/cases/{cid}/documents",
                         files={"file": ("b.png", data, "image/png")},
                         headers=auth)
        assert r2.status_code == 409, r2.text
        assert r2.json()["error"]["code"] == "DOCUMENT_DUPLICATE"
    finally:
        _delete_case(db, cid)
        db.close()


def test_retry_reuses_the_same_job_row(client, auth):
    """Retrying a failed document reuses its job row (attempts++) — the
    idempotency contract: one document, one job row, ever."""
    cid = _new_case(client, auth, "retry")
    db = SessionLocal()
    try:
        # A .pdf named file with a non-PDF body: passes the extension
        # check? No — the content check rejects it at upload (400). To get
        # a FAILED job we upload a valid-but-OCR-less blank image.
        from PIL import Image
        blank = Image.new("RGB", (800, 200), "white")
        buf = io.BytesIO()
        blank.save(buf, format="PNG")
        r = client.post(f"/api/v1/cases/{cid}/documents",
                        files={"file": ("blank.png", buf.getvalue(),
                                        "image/png")},
                        headers=auth)
        assert r.status_code == 201, r.text
        doc = r.json()
        first_job_id = doc["processing_job"]["id"]
        docs = _wait_processed(client, auth, cid)
        assert docs[0]["processing_status"] == "FAILED"
        assert "readable text" in (docs[0]["processing_error"] or "")

        r = client.post(f"/api/v1/documents/{doc['id']}/process",
                        headers=auth)
        assert r.status_code == 202, r.text
        doc2 = r.json()
        # the SAME job row is reused — requeued, not a second row
        assert doc2["processing_job"]["id"] == first_job_id
        assert doc2["processing_job"]["status"] == "QUEUED"
        assert doc2["processing_job"]["attempts"] >= 1
        # Poll the JOB (not the document — the document keeps its FAILED
        # status until the worker re-claims it): it must go through a
        # second claim, so attempts reaches >= 2 on the same row.
        deadline = time.time() + 60
        job = doc2["processing_job"]
        while time.time() < deadline:
            docs2 = client.get(f"/api/v1/cases/{cid}/documents",
                               headers=auth).json()
            job = docs2[0]["processing_job"]
            if job["status"] in ("COMPLETED", "FAILED") and job["attempts"] >= 2:
                break
            time.sleep(0.5)
        assert job["id"] == first_job_id
        assert job["attempts"] >= 2, job
        assert job["status"] == "FAILED", job
        # still exactly one job row for this document
        from app.models.models import DocumentProcessingJob
        rows = db.query(DocumentProcessingJob).filter_by(
            document_id=doc["id"]).all()
        assert len(rows) == 1
    finally:
        _delete_case(db, cid)
        db.close()


# ------------------------------------------------------------------------ OCR

def test_ocr_image_upload(client, auth, scan_fixtures):
    """A scanned image is OCR'd: PROCESSED, ocr provenance in the stats,
    and the fictional names/phones are extractable as candidates."""
    png = scan_fixtures[0]
    cid = _new_case(client, auth, "ocr-img")
    db = SessionLocal()
    try:
        data = open(png, "rb").read()
        r = client.post(f"/api/v1/cases/{cid}/documents",
                        files={"file": ("scan.png", data, "image/png")},
                        headers=auth)
        assert r.status_code == 201, r.text
        docs = _wait_processed(client, auth, cid)
        d = docs[0]
        assert d["processing_status"] == "PROCESSED", d["processing_error"]
        assert d["processing_method"].endswith("+ocr"), d["processing_method"]
        assert d["page_count"] == 1

        ex = client.get(f"/api/v1/documents/{d['id']}/extraction",
                        headers=auth).json()
        names = [e["candidate_name"] for e in ex["entities"]]
        assert any("Suresh Yadav" in n for n in names)
        assert any("9000000955" in n for n in names)
    finally:
        _delete_case(db, cid)
        db.close()


def test_ocr_scanned_pdf_page(client, auth, scan_fixtures):
    """A PDF with no text layer is OCR'd page by page, with per-page OCR
    metadata (engine + languages) preserved for provenance."""
    pdf = scan_fixtures[1]
    cid = _new_case(client, auth, "ocr-pdf")
    db = SessionLocal()
    try:
        data = open(pdf, "rb").read()
        r = client.post(f"/api/v1/cases/{cid}/documents",
                        files={"file": ("scan.pdf", data,
                                        "application/pdf")},
                        headers=auth)
        assert r.status_code == 201, r.text
        docs = _wait_processed(client, auth, cid)
        d = docs[0]
        assert d["processing_status"] == "PROCESSED", d["processing_error"]
        assert d["processing_method"].endswith("+ocr")

        # per-page OCR metadata + stats are stored with the extraction
        from app.models.models import DocumentExtraction
        ext = db.query(DocumentExtraction).filter_by(document_id=d["id"]).first()
        assert ext is not None
        assert ext.pages, "expected page metadata with OCR provenance"
        assert ext.pages[0].get("ocr", {}).get("engine") == "tesseract"
        assert (ext.stats or {}).get("ocr_pages") == 1, ext.stats
    finally:
        _delete_case(db, cid)
        db.close()


def test_ocr_disabled_fails_honestly(client, auth, scan_fixtures, monkeypatch):
    """OCR_ENABLED=false + a scanned document => a clear processing
    error, never a silent PROCESSED-with-nothing."""
    pdf = scan_fixtures[1]
    monkeypatch.setenv("OCR_ENABLED", "false")
    from app.core.config import get_settings
    get_settings.cache_clear()
    try:
        cid = _new_case(client, auth, "ocr-off")
        db = SessionLocal()
        try:
            data = open(pdf, "rb").read()
            r = client.post(f"/api/v1/cases/{cid}/documents",
                            files={"file": ("scan.pdf", data,
                                            "application/pdf")},
                            headers=auth)
            assert r.status_code == 201, r.text
            docs = _wait_processed(client, auth, cid)
            d = docs[0]
            assert d["processing_status"] == "FAILED", d
            assert "OCR is disabled" in (d["processing_error"] or ""), d
        finally:
            _delete_case(db, cid)
            db.close()
    finally:
        get_settings.cache_clear()


def test_ocr_dependency_missing_fails_honestly(client, auth, scan_fixtures,
                                               monkeypatch):
    """When the OCR engine itself is unavailable (tesseract missing), the
    document FAILS with a clear message instead of producing nothing."""
    png = scan_fixtures[0]
    import app.pipeline.ocr as ocr_mod

    monkeypatch.setattr(
        ocr_mod, "capabilities",
        lambda: {"available": False, "engine": "tesseract",
                 "version": None, "languages": []})
    cid = _new_case(client, auth, "ocr-missing")
    db = SessionLocal()
    try:
        data = open(png, "rb").read()
        r = client.post(f"/api/v1/cases/{cid}/documents",
                        files={"file": ("scan.png", data, "image/png")},
                        headers=auth)
        assert r.status_code == 201, r.text
        docs = _wait_processed(client, auth, cid)
        d = docs[0]
        assert d["processing_status"] == "FAILED", d
        assert "OCR is unavailable" in (d["processing_error"] or ""), d
    finally:
        _delete_case(db, cid)
        db.close()


def test_text_pdf_does_not_use_ocr(client, auth):
    """A normal text PDF goes through plain text extraction — OCR is not
    invoked (method has no +ocr, no ocr stats)."""
    import os.path as _p
    pdf = _p.join(FIXTURES, "synthetic_fir.pdf")
    cid = _new_case(client, auth, "pdf-text")
    db = SessionLocal()
    try:
        data = open(pdf, "rb").read()
        r = client.post(f"/api/v1/cases/{cid}/documents",
                        files={"file": ("fir.pdf", data,
                                        "application/pdf")},
                        headers=auth)
        assert r.status_code == 201, r.text
        docs = _wait_processed(client, auth, cid)
        d = docs[0]
        assert d["processing_status"] == "PROCESSED", d["processing_error"]
        assert "+ocr" not in (d["processing_method"] or "")
        stats = d.get("processing_stats") or {}
        assert "ocr_pages" not in stats
    finally:
        _delete_case(db, cid)
        db.close()


# ------------------------------------------------------------------- storage

def test_upload_rejects_bad_image_magic(client, auth):
    """.png extension but not PNG bytes => 400 (never trust the name)."""
    cid = _new_case(client, auth, "badimg")
    db = SessionLocal()
    try:
        r = client.post(f"/api/v1/cases/{cid}/documents",
                        files={"file": ("fake.png",
                                        b"this is not a png at all",
                                        "image/png")},
                        headers=auth)
        assert r.status_code == 400, r.text
        assert r.json()["error"]["code"] == "DOCUMENT_INVALID"
    finally:
        _delete_case(db, cid)
        db.close()


def test_upload_rejects_unsupported_type(client, auth):
    cid = _new_case(client, auth, "badtype")
    db = SessionLocal()
    try:
        r = client.post(f"/api/v1/cases/{cid}/documents",
                        files={"file": ("tool.exe", b"MZ...binary",
                                        "application/octet-stream")},
                        headers=auth)
        assert r.status_code == 400, r.text
        assert r.json()["error"]["code"] == "DOCUMENT_UNSUPPORTED_TYPE"
    finally:
        _delete_case(db, cid)
        db.close()


def test_storage_local_roundtrip(tmp_path, monkeypatch):
    from app.core import storage as st
    from app.core.config import get_settings

    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "store"))
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    get_settings.cache_clear()
    st.reset_storage_cache()
    try:
        store = st.get_storage()
        assert isinstance(store, st.LocalObjectStorage)
        payload = b"%PDF-1.4 test"
        n = store.save("documents/1/1_a.pdf", payload)
        assert n == len(payload)
        assert store.exists("documents/1/1_a.pdf")
        assert store.size("documents/1/1_a.pdf") == len(payload)
        assert store.open("documents/1/1_a.pdf").read() == b"%PDF-1.4 test"
        store.delete("documents/1/1_a.pdf")
        assert not store.exists("documents/1/1_a.pdf")
        # path traversal via a hostile key is refused
        with pytest.raises(st.StorageError):
            store.open("../.env")
    finally:
        st.reset_storage_cache()
        get_settings.cache_clear()


def test_storage_s3_roundtrip(monkeypatch):
    """The S3 backend against an in-memory S3 (moto): save/read/delete/
    exists/size + key prefix + honest missing-key error."""
    from moto import mock_aws

    with mock_aws():
        import boto3
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket="nexus-test")
        from app.core.storage import S3ObjectStorage, StorageError

        store = S3ObjectStorage(bucket="nexus-test", region="us-east-1",
                                prefix="nexus")
        payload = b"imagedata"
        n = store.save("documents/7/7_scan.png", payload)
        assert n == len(payload)
        assert store.exists("documents/7/7_scan.png")
        assert store.size("documents/7/7_scan.png") == len(payload)
        assert store.open("documents/7/7_scan.png").read() == payload
        # the prefix really is applied on the wire
        keys = [o["Key"]
                for o in client.list_objects_v2(Bucket="nexus-test")["Contents"]]
        assert keys == ["nexus/documents/7/7_scan.png"]
        store.delete("documents/7/7_scan.png")
        assert not store.exists("documents/7/7_scan.png")
        with pytest.raises(StorageError):
            store.open("documents/7/7_scan.png")


# ------------------------------------------------------------------ alembic

def test_alembic_version_stamped_on_live_db():
    """The development database carries an Alembic version (the startup
    migration path ran)."""
    from sqlalchemy import text
    with engine.connect() as conn:
        row = conn.execute(text("SELECT version_num FROM alembic_version")) \
                   .first()
    assert row is not None, "alembic_version table missing"
    assert row[0]


def test_alembic_upgrade_head_is_idempotent():
    """Running `alembic upgrade head` again changes nothing (no error,
    same version, no data touched)."""
    from sqlalchemy import text
    with engine.connect() as conn:
        before = conn.execute(text(
            'SELECT count(*) FROM document')).scalar()
    proc = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=os.path.abspath(os.path.join(os.path.dirname(__file__), "..")),
        capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr[-800:]
    with engine.connect() as conn:
        after = conn.execute(text('SELECT count(*) FROM document')).scalar()
    assert before == after


def test_alembic_fresh_database_migrates_to_head():
    """A brand-new empty database reaches head via `alembic upgrade head`
    with the full schema — the fresh-install path. Requires local
    superuser access to create a throwaway database; skipped otherwise.
    """
    # create a throwaway db via the local postgres superuser
    dbname = f"nexus_mig_{uuid.uuid4().hex[:10]}"
    try:
        created = subprocess.run(
            ["sudo", "-n", "su", "-", "postgres", "-c",
             f'psql -tAc "CREATE DATABASE {dbname} OWNER nexus;"'],
            capture_output=True, text=True, timeout=60)
        if created.returncode != 0:
            pytest.skip("cannot create a throwaway database here")
        url = (f"postgresql+psycopg://nexus:nexus_dev_2026@127.0.0.1:5432/"
               f"{dbname}")
        proc = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=os.path.abspath(os.path.join(os.path.dirname(__file__), "..")),
            env={**os.environ, "DATABASE_URL": url},
            capture_output=True, text=True, timeout=180)
        assert proc.returncode == 0, proc.stderr[-800:]
        import psycopg
        conn = psycopg.connect(url.replace("postgresql+psycopg://",
                                           "postgresql://"))
        tables = {r[0] for r in conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='public'")}
        assert {"case", "document", "document_processing_job",
                "alembic_version"} <= tables
        n_tables = len(tables)
        conn.close()
        assert n_tables >= 23
    finally:
        subprocess.run(
            ["sudo", "-n", "su", "-", "postgres", "-c",
             f'psql -tAc "DROP DATABASE IF EXISTS {dbname};"'],
            capture_output=True, text=True, timeout=60)


def test_alembic_existing_database_preserves_data():
    """Migration on the live (data-filled) database never destroys rows:
    the count before == after an upgrade run. (upgrade head is covered
    above; this asserts the data-preservation half explicitly.)"""
    from sqlalchemy import text
    with engine.connect() as conn:
        before = {t: conn.execute(
            text(f'SELECT count(*) FROM "{t}"')).scalar()
            for t in ("case", "document", "entity", "user")}
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=os.path.abspath(os.path.join(os.path.dirname(__file__), "..")),
        capture_output=True, text=True, timeout=120)
    with engine.connect() as conn:
        after = {t: conn.execute(
            text(f'SELECT count(*) FROM "{t}"')).scalar()
            for t in ("case", "document", "entity", "user")}
    assert before == after


# ----------------------------------------------------------------- security

def test_login_endpoint_removed(client):
    """Credential login is gone: authentication is Supabase Auth, so the
    backend has no /auth/login to rate-limit or brute-force."""
    r = client.post("/api/v1/auth/login",
                    json={"email": "a@b.c", "password": "whatever"})
    assert r.status_code in (404, 405)


def test_security_headers_present(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    h = {k.lower(): v for k, v in r.headers.items()}
    assert "default-src 'self'" in h.get("content-security-policy", "")
    assert h.get("x-content-type-options") == "nosniff"
    assert h.get("x-frame-options") == "DENY"
    assert h.get("referrer-policy") == "no-referrer"


def test_request_id_generated_and_echoed(client):
    r1 = client.get("/api/v1/health")
    rid1 = r1.headers.get("X-Request-ID")
    assert rid1 and len(rid1) >= 8
    r2 = client.get("/api/v1/health", headers={"X-Request-ID": "trace-abc-123"})
    assert r2.headers.get("X-Request-ID") == "trace-abc-123"
    r3 = client.get("/api/v1/health")
    assert r3.headers.get("X-Request-ID")  # fresh id per request
    assert r3.headers.get("X-Request-ID") != "trace-abc-123"


def test_env_example_has_no_real_credentials():
    path = os.path.abspath(os.path.join(
        os.path.dirname(__file__), "..", ".env.example"))
    text = open(path, encoding="utf-8").read()
    for secret in ("nexus_dev_2026", "neo4j_dev_2026", "dev-only-change-me"):
        assert secret not in text, f"real/dev credential {secret!r} shipped"
    # the required secrets are placeholders or empty
    assert "DATABASE_URL=postgresql+psycopg://" in text
    assert "<db-password>" in text or "<" in text.split("DATABASE_URL=")[1]
    # Supabase-first configuration is present, with no local/Neo4j servers.
    # Authentication is Supabase Auth: no NEXUS-issued JWT secret is required
    # (asymmetric projects verify via JWKS); only the optional HS256 secret.
    assert "SUPABASE_URL=" in text
    assert "SUPABASE_JWT_SECRET=" in text
    assert "JWT_SECRET" not in text
    assert "NEO4J" not in text.upper()


def test_cors_config_driven(monkeypatch):
    """CORS_ORIGINS is honoured (dev: empty => permissive; explicit list
    => only those origins)."""
    from app.main import _cors_origins
    from app.core.config import get_settings

    monkeypatch.setenv("CORS_ORIGINS", "https://a.example, https://b.example")
    get_settings.cache_clear()
    try:
        assert _cors_origins() == ["https://a.example", "https://b.example"]
    finally:
        get_settings.cache_clear()
    # production with an empty list => no cross-origin access
    monkeypatch.setenv("CORS_ORIGINS", "")
    monkeypatch.setenv("APP_ENV", "production")
    get_settings.cache_clear()
    try:
        assert _cors_origins() == []
    finally:
        monkeypatch.setenv("APP_ENV", "development")
        get_settings.cache_clear()


# -------------------------------------------------------------- observability

def test_health_reports_dependencies(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("ok", "degraded")
    assert body["database"]["reachable"] is True
    assert body["storage"]["backend"] == "local"
    assert body["storage"]["ok"] is True
    assert "queue" in body["worker"]
    assert "neo4j" not in body  # graph database dependency removed


def test_readyz(client):
    r = client.get("/api/v1/readyz")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ready"] is True
    assert body["database"]["reachable"] is True
    assert body["storage"]["ok"] is True


# ---------------------------------------------------------------- pagination

def test_pagination_on_cases(client, auth):
    base = client.get("/api/v1/cases", headers=auth)
    assert base.status_code == 200
    total = int(base.headers["X-Total-Count"])
    assert len(base.json()) == total  # default: full list (contract kept)

    p = client.get("/api/v1/cases?limit=2&offset=0", headers=auth)
    assert p.status_code == 200
    assert len(p.json()) == 2
    assert int(p.headers["X-Total-Count"]) == total
    assert p.headers["X-Offset"] == "0"
    assert p.headers["X-Limit"] == "2"

    p2 = client.get(f"/api/v1/cases?limit={total}", headers=auth)
    assert len(p2.json()) == total  # a full-width page == the full list


def test_pagination_on_case_entities(client, auth):
    # find a case with confirmed entities (the seeded demo case)
    cases = client.get("/api/v1/cases", headers=auth).json()
    target = None
    for c in cases:
        ents = client.get(f"/api/v1/cases/{c['id']}/entities",
                          headers=auth)
        if ents.json():
            target = (c["id"], ents.json())
            break
    assert target is not None, "no case with confirmed entities found"
    cid, full = target
    assert len(full) >= 2, "demo case should have several entities"

    p = client.get(f"/api/v1/cases/{cid}/entities?limit=1&offset=1",
                   headers=auth)
    assert p.status_code == 200
    assert len(p.json()) == 1
    assert int(p.headers["X-Total-Count"]) == len(full)
    assert p.json()[0]["id"] == full[1]["id"]

    # limit above the total returns everything
    p = client.get(f"/api/v1/cases/{cid}/entities?limit=1000",
                   headers=auth)
    assert len(p.json()) == len(full)


def test_validation_bounds_on_pagination(client, auth):
    r = client.get("/api/v1/cases?limit=100000", headers=auth)
    assert r.status_code == 422  # le=1000 enforced
    r = client.get("/api/v1/cases?offset=-1", headers=auth)
    assert r.status_code == 422
