"""GET /api/v1/health (liveness) and GET /api/v1/readyz (readiness).

* ``/health`` — the service is up, plus an honest status of each
  dependency (database, storage, worker). Degraded dependencies make the
  status "degraded", not "ok". (There is no graph database: graph
  intelligence runs in-process with NetworkX, so there is nothing to
  health-check for it.)
* ``/readyz`` — for load balancers: 200 only when the database AND
  storage are usable (the app cannot serve case data without them),
  503 otherwise. The worker is NOT part of readiness: a deployment with
  a separate worker process (or WORKER_ENABLED=false) is still ready to
  serve reads; queue depth is reported in the body.

Neither endpoint requires authentication and neither returns secrets.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Response

from ...core.config import get_settings
from ...core.database import SessionLocal, db_ready, engine
from ...models.models import DocumentProcessingJob
from ...schemas.v1 import HealthOut
from sqlalchemy import func, select

router = APIRouter(tags=["health"])


def _database_status() -> dict:
    from sqlalchemy import text

    out: dict = {"connected": db_ready(), "driver": "psycopg"}
    try:
        import sqlalchemy

        out["sqlalchemy"] = sqlalchemy.__version__
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        out["reachable"] = True
    except Exception:  # noqa: BLE001 — honest "not reachable"
        out["reachable"] = False
    return out


def _storage_status() -> dict:
    from ...core.storage import StorageError, get_storage

    out: dict = {}
    try:
        import os

        settings = get_settings()
        storage = get_storage()
        out["backend"] = (settings.storage_backend or "local").lower()
        if out["backend"] == "local":
            out["root"] = storage.root  # type: ignore[attr-defined]
            out["reachable"] = os.path.isdir(storage.root)  # type: ignore[attr-defined]
        else:
            # S3: head the bucket to prove credentials/network without
            # touching any object.
            from botocore.exceptions import ClientError
            try:
                storage._client.head_bucket(Bucket=storage._bucket)  # noqa: SLF001
                out["reachable"] = True
            except ClientError:
                out["reachable"] = False
        out["ok"] = bool(out["reachable"])
    except StorageError as exc:
        out = {"backend": (get_settings().storage_backend or "local").lower(),
               "ok": False, "error": exc.__class__.__name__}
    except Exception as exc:  # noqa: BLE001 — e.g. boto3 missing
        out = {"ok": False, "error": f"{exc.__class__.__name__}"}
    return out


def _worker_status() -> dict:
    from ...services import processing_worker

    out = processing_worker.worker_status()
    out["queue"] = _queue_depth()
    return out


def _queue_depth() -> dict:
    """Queued/processing document jobs, from the queue table itself —
    true for in-process and standalone worker deployments alike."""
    try:
        db = SessionLocal()
        try:
            def count(status: str) -> int:
                return db.scalar(
                    select(func.count()).select_from(DocumentProcessingJob)
                    .where(DocumentProcessingJob.status == status)) or 0
            return {"queued": count("QUEUED"), "processing": count("PROCESSING")}
        finally:
            db.close()
    except Exception:  # noqa: BLE001 — no DB => no queue numbers
        return {"queued": None, "processing": None}


def _health_payload() -> HealthOut:
    settings = get_settings()
    database = _database_status()
    storage = _storage_status()
    worker = _worker_status()

    degraded = (not database.get("reachable", db_ready())
                or not storage.get("ok", False))
    return HealthOut(
        status="ok" if not degraded else "degraded",
        version=settings.app_version,
        environment=settings.app_env,
        time=datetime.now(timezone.utc),
        database=database,
        synthetic_data_only=True,
        storage=storage,
        worker=worker,
    )


@router.get("/health", response_model=HealthOut, summary="Service + infrastructure health")
def health() -> HealthOut:
    return _health_payload()


@router.get("/readyz", summary="Readiness for load balancers (no auth)")
def readyz(response: Response) -> dict:
    """200 when the app can serve case data; 503 otherwise.

    Readiness = database reachable + storage usable. The worker is
    reported but does not block readiness (it may live in another
    process).
    """
    database = _database_status()
    storage = _storage_status()
    ready = bool(database.get("reachable")) and bool(storage.get("ok"))
    if not ready:
        response.status_code = 503
    return {
        "ready": ready,
        "database": {"reachable": database.get("reachable")},
        "storage": {"ok": storage.get("ok"),
                    "backend": storage.get("backend")},
        "queue": _worker_status().get("queue", {}),
    }
