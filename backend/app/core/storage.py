"""Storage for uploaded documents: an abstraction, never a hard-coded path.

Phase 1 production foundation. The application only ever deals in *object
keys* (e.g. ``documents/12/34_fir.pdf``); the backend that resolves a key
to bytes is pluggable:

* ``local`` (default) — the local filesystem under ``STORAGE_ROOT``
  (development). Behaviour is unchanged from stage 2: files are DATA,
  written under a server-generated name (never the user-supplied
  filename), which makes path traversal impossible by construction.
* ``s3`` — any S3-compatible object store (AWS S3, MinIO, Cloudflare R2,
  ...) via ``boto3``. Selected with ``STORAGE_BACKEND=s3`` + the
  ``S3_*`` settings. When ``boto3`` is not installed, selecting S3 fails
  loudly at startup/use with a clear error — it is never silently faked.

The upload validation in :func:`validate_upload` is backend-agnostic and
unchanged in behaviour: extension allow-list, streaming size limit,
sha256, and content magic-byte checks.
"""

from __future__ import annotations

import hashlib
import io
import os
import re
import shutil
from abc import ABC, abstractmethod
from dataclasses import dataclass

from fastapi import UploadFile

from .config import get_settings

# Only these extensions are ever accepted (stage 2 + phase 1 OCR images).
SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".csv", ".png", ".jpg", ".jpeg",
                        ".tif", ".tiff"}
SUPPORTED_MIME = {
    ".pdf": {"application/pdf"},
    ".txt": {"text/plain", "text/x-python", "text/x-plain", ""},
    ".csv": {"text/csv", "application/vnd.ms-excel", "application/csv",
             "text/plain", ""},
    # Phase 1: scanned-image uploads (OCR path)
    ".png": {"image/png"},
    ".jpg": {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
    ".tif": {"image/tiff"},
    ".tiff": {"image/tiff"},
}


class DocumentInvalidError(Exception):
    """Upload rejected during validation (safe to show to the user)."""

    def __init__(self, message: str, code: str = "DOCUMENT_INVALID"):
        super().__init__(message)
        self.code = code


class StorageError(Exception):
    """The storage backend failed (surfaced as a user-safe 500 reason)."""


@dataclass
class ValidatedUpload:
    """Everything the service needs after validation, before persistence."""

    filename: str          # original name, for display metadata only
    extension: str         # e.g. ".pdf"
    mime_type: str | None
    size: int
    sha256: str
    data: bytes            # full bytes (uploads are capped at max_upload_mb)
    safe_name: str         # server-generated, safe for any backend


# ------------------------------------------------------------------ backends

class ObjectStorage(ABC):
    """A key -> bytes store. Keys are app-defined (no user input)."""

    @abstractmethod
    def save(self, key: str, data: bytes) -> int:
        """Store ``data`` under ``key``; returns the byte count."""

    @abstractmethod
    def open(self, key: str) -> io.BytesIO:
        """Return the object's bytes. Raises StorageError when missing."""

    @abstractmethod
    def delete(self, key: str) -> None:
        """Delete ``key`` (no-op when absent)."""

    @abstractmethod
    def exists(self, key: str) -> bool: ...

    @abstractmethod
    def size(self, key: str) -> int | None: ...


class LocalObjectStorage(ObjectStorage):
    """The local filesystem (development default).

    ``root`` is the storage root; keys are relative to it. The final path
    is verified to stay inside the root (defense in depth).
    """

    def __init__(self, root: str):
        self.root = os.path.abspath(root)
        os.makedirs(os.path.join(self.root, "documents"), exist_ok=True)

    def _path(self, key: str) -> str:
        target = os.path.join(self.root, key)
        if not os.path.realpath(target).startswith(
                os.path.realpath(self.root) + os.sep):
            raise StorageError("storage key escaped the storage root")
        return target

    def save(self, key: str, data: bytes) -> int:
        target = self._path(key)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        tmp = target + ".part"
        with open(tmp, "wb") as out:
            out.write(data)
        os.replace(tmp, target)
        return len(data)

    def open(self, key: str) -> io.BytesIO:
        target = self._path(key)
        if not os.path.isfile(target):
            raise StorageError(f"stored file is missing: {key}")
        with open(target, "rb") as fh:
            return io.BytesIO(fh.read())

    def delete(self, key: str) -> None:
        target = self._path(key)
        if os.path.isfile(target):
            os.remove(target)
        case_dir = os.path.dirname(target)
        try:
            if os.path.isdir(case_dir) and not os.listdir(case_dir):
                shutil.rmtree(case_dir, ignore_errors=True)
        except OSError:  # pragma: no cover — best effort
            pass

    def exists(self, key: str) -> bool:
        return os.path.isfile(self._path(key))

    def size(self, key: str) -> int | None:
        target = self._path(key)
        return os.path.getsize(target) if os.path.isfile(target) else None


class S3ObjectStorage(ObjectStorage):
    """Any S3-compatible object store via boto3 (production).

    ``prefix`` (optional) namespaces all NEXUS keys inside the bucket.
    Fails loudly when boto3 is absent or the object store is
    unreachable — never fakes a save/read.
    """

    def __init__(self, bucket: str, endpoint_url: str = "",
                 prefix: str = "", region: str = "",
                 access_key_id: str = "", secret_access_key: str = ""):
        try:
            import boto3
        except ImportError as exc:
            raise StorageError(
                "STORAGE_BACKEND=s3 requires the 'boto3' package "
                "(pip install boto3).") from exc
        if not bucket:
            raise StorageError("STORAGE_BACKEND=s3 requires S3_BUCKET.")
        kwargs: dict = {}
        if endpoint_url:
            kwargs["endpoint_url"] = endpoint_url
        if region:
            kwargs["region_name"] = region
        if access_key_id and secret_access_key:
            kwargs["aws_access_key_id"] = access_key_id
            kwargs["aws_secret_access_key"] = secret_access_key
        self._bucket = bucket
        self._prefix = prefix.strip("/")
        self._client = boto3.client("s3", **kwargs)

    def _key(self, key: str) -> str:
        return f"{self._prefix}/{key}" if self._prefix else key

    def save(self, key: str, data: bytes) -> int:
        try:
            self._client.put_object(Bucket=self._bucket,
                                    Key=self._key(key), Body=data)
        except Exception as exc:  # noqa: BLE001 — boto3 raises many types
            raise StorageError(f"object store save failed: {exc.__class__.__name__}") from exc
        return len(data)

    def open(self, key: str) -> io.BytesIO:
        from botocore.exceptions import ClientError
        try:
            obj = self._client.get_object(Bucket=self._bucket,
                                          Key=self._key(key))
            return io.BytesIO(obj["Body"].read())
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in ("NoSuchKey", "404"):
                raise StorageError(f"stored file is missing: {key}") from exc
            raise StorageError(f"object store read failed: {exc.__class__.__name__}") from exc

    def delete(self, key: str) -> None:
        try:
            self._client.delete_object(Bucket=self._bucket,
                                       Key=self._key(key))
        except Exception:  # noqa: BLE001 — delete is best-effort
            pass

    def exists(self, key: str) -> bool:
        from botocore.exceptions import ClientError
        try:
            self._client.head_object(Bucket=self._bucket, Key=self._key(key))
            return True
        except ClientError:
            return False

    def size(self, key: str) -> int | None:
        from botocore.exceptions import ClientError
        try:
            head = self._client.head_object(Bucket=self._bucket,
                                            Key=self._key(key))
            return head.get("ContentLength")
        except ClientError:
            return None


# ------------------------------------------------------------------- factory

_storage_cache: ObjectStorage | None = None


def storage_root() -> str:
    """The local storage root (still used for the local backend and for
    the health probe). Kept for compatibility."""
    settings = get_settings()
    if settings.storage_root:
        root = os.path.abspath(settings.storage_root)
    else:
        # backend/storage — resolved from this file, not the CWD.
        root = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__)))), "storage")
    os.makedirs(os.path.join(root, "documents"), exist_ok=True)
    return root


def get_storage() -> ObjectStorage:
    """The configured storage backend (cached per process)."""
    global _storage_cache
    if _storage_cache is not None:
        return _storage_cache
    settings = get_settings()
    backend = (settings.storage_backend or "local").lower()
    if backend == "local":
        _storage_cache = LocalObjectStorage(storage_root())
    elif backend == "s3":
        # Supabase-aware: the endpoint and secret resolve from SUPABASE_URL /
        # SUPABASE_SERVICE_ROLE_KEY when the explicit S3_* values are empty.
        _storage_cache = S3ObjectStorage(
            bucket=settings.s3_bucket,
            endpoint_url=settings.effective_s3_endpoint_url,
            prefix=settings.s3_prefix,
            region=settings.s3_region,
            access_key_id=settings.s3_access_key_id,
            secret_access_key=settings.effective_s3_secret_access_key)
    else:
        raise StorageError(f"unknown STORAGE_BACKEND: {settings.storage_backend!r}")
    return _storage_cache


def reset_storage_cache() -> None:
    """Test hook: drop the cached backend (settings changed)."""
    global _storage_cache
    _storage_cache = None


# ------------------------------------------------------------- upload rules

def _safe_stem(name: str) -> str:
    """Reduce an arbitrary filename stem to [A-Za-z0-9._-], capped in length.

    The result is decorative: the authoritative name is
    `{document_id}_{safe_stem}{ext}`, and the id is what the app resolves.
    """
    stem = os.path.splitext(os.path.basename(name or ""))[0]
    stem = re.sub(r"[^A-Za-z0-9._-]", "_", stem)
    stem = re.sub(r"_+", "_", stem).strip("._-")
    return stem[:80] or "document"


def validate_upload(upload: UploadFile, max_bytes: int) -> ValidatedUpload:
    """Validate extension, size, emptiness and (where meaningful) content.

    Raises DocumentInvalidError with a user-safe message on any problem.
    """
    filename = upload.filename or ""
    if not filename or "\x00" in filename or len(filename) > 255:
        raise DocumentInvalidError("Invalid file name.",
                                   code="DOCUMENT_INVALID")
    ext = os.path.splitext(filename)[1].lower()

    if ext not in SUPPORTED_EXTENSIONS:
        raise DocumentInvalidError(
            f"Unsupported file type '{ext or 'unknown'}'. "
            f"Supported: PDF, TXT, CSV, PNG, JPG, JPEG, TIFF.",
            code="DOCUMENT_UNSUPPORTED_TYPE")

    # Stream through to validate size + hash (uploads are capped, so the
    # in-memory bytes are bounded by MAX_UPLOAD_MB).
    digest = hashlib.sha256()
    chunks: list[bytes] = []
    size = 0
    while chunk := upload.file.read(1024 * 1024):
        size += len(chunk)
        if size > max_bytes:
            raise DocumentInvalidError(
                f"File exceeds the {max_bytes // (1024 * 1024)} MB limit.",
                code="DOCUMENT_TOO_LARGE")
        digest.update(chunk)
        chunks.append(chunk)

    if size == 0:
        raise DocumentInvalidError("The uploaded file is empty.",
                                   code="DOCUMENT_INVALID")

    data = b"".join(chunks)

    # Content sanity checks (never trust the extension or the MIME alone).
    head = data[:8]
    if ext == ".pdf" and not head.startswith(b"%PDF"):
        raise DocumentInvalidError(
            "File does not start with a valid PDF header.",
            code="DOCUMENT_INVALID")
    # Phase 1: image magic bytes (PNG / JPEG / TIFF)
    if ext in (".png", ".jpg", ".jpeg", ".tif", ".tiff"):
        is_png = head.startswith(b"\x89PNG")
        is_jpeg = head.startswith(b"\xff\xd8\xff")
        is_tiff = head.startswith((b"II\x2a\x00", b"MM\x00\x2a"))
        if not (is_png or is_jpeg or is_tiff):
            raise DocumentInvalidError(
                "File does not start with a valid image header.",
                code="DOCUMENT_INVALID")
    if ext in (".txt", ".csv"):
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            # latin-1 would always decode; check for NUL bytes instead of
            # forcing an opinion — binary blobs are not text documents.
            if b"\x00" in data:
                raise DocumentInvalidError(
                    "File appears to be binary, not a text document.",
                    code="DOCUMENT_INVALID")
        else:
            text = data.decode("utf-8")
            if ext == ".csv":
                stripped = text.lstrip("\ufeff").splitlines()
                if not stripped or "," not in (stripped[0] or ""):
                    raise DocumentInvalidError(
                        "CSV file has no header row with columns.",
                        code="DOCUMENT_INVALID")

    mime = (upload.content_type or "").lower() or None
    allowed = SUPPORTED_MIME[ext]
    if mime and mime not in allowed and mime != "application/octet-stream":
        # A strongly contradicting declared MIME (e.g. text/html on a .pdf)
        # is treated as invalid; octet-stream is treated as "not provided".
        raise DocumentInvalidError(
            f"Declared content type '{mime}' does not match a "
            f"{ext.lstrip('.').upper()} file.",
            code="DOCUMENT_INVALID")

    return ValidatedUpload(
        filename=filename,
        extension=ext,
        mime_type=mime,
        size=size,
        sha256=digest.hexdigest(),
        data=data,
        safe_name=f"{_safe_stem(filename)}{ext}",
    )


# ------------------------------------------------- compatibility helpers
# These keep the stage-2 calling sites (document_service) working while the
# bytes actually flow through the configured ObjectStorage backend.

def store_file(validated: ValidatedUpload, case_id: int, document_id: int) -> str:
    """Write the file to the configured backend; returns the object key.

    The final name includes the document id, so the key can never collide
    with or point at anything the user named.
    """
    relative = os.path.join(
        "documents", str(case_id), f"{document_id}_{validated.safe_name}")
    try:
        get_storage().save(relative, validated.data)
    except StorageError as exc:
        raise OSError(str(exc)) from exc
    return relative


def delete_file(key: str | None) -> None:
    if not key:
        return
    get_storage().delete(key)
