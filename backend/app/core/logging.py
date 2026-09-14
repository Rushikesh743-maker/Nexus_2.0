"""Backend logging.

Covers application startup, database connection and API errors.
Deliberately never logs passwords, JWT tokens, API keys or request
bodies that may contain credentials — only method, path, status and error
codes.

Production observability (phase 1):

* **Correlation.** Every request carries an ``X-Request-ID`` (supplied by
  the caller or generated here) and every background document job carries a
  job id. Both live in context variables and are attached to every log
  record by :class:`ContextFilter`, so a request or a job can be followed
  through the whole log.
* **Structured output.** ``LOG_FORMAT=json`` switches the root handler to
  a JSON formatter (one JSON object per line) for log shippers; the
  default human format is unchanged.
"""

from __future__ import annotations

import json
import logging
import sys
import time
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone

_CONFIGURED = False

# ------------------------------------------------------------------ context
# Set per request by the middleware, per job by the processing worker.
request_id_ctx: ContextVar[str | None] = ContextVar("nexus_request_id", default=None)
job_id_ctx: ContextVar[int | None] = ContextVar("nexus_job_id", default=None)


def new_request_id() -> str:
    return uuid.uuid4().hex


def set_request_context(request_id: str | None):
    """Set the current request id; returns the contextvar token for reset."""
    return request_id_ctx.set(request_id)


def set_job_context(job_id: int | None):
    """Set the current job id; returns the contextvar token for reset."""
    return job_id_ctx.set(job_id)


class ContextFilter(logging.Filter):
    """Attach request/job correlation ids to every nexus log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        request_id = request_id_ctx.get()
        job_id = job_id_ctx.get()
        record.request_id = request_id  # type: ignore[attr-defined]
        record.job_id = job_id  # type: ignore[attr-defined]
        # For the human-readable formatter: a compact suffix, e.g.
        # "[rid=a1b2… job=7]"; empty when there is nothing to correlate.
        parts = []
        if request_id:
            parts.append(f"rid={request_id[:12]}")
        if job_id is not None:
            parts.append(f"job={job_id}")
        record.context_tag = f" [{', '.join(parts)}]" if parts else ""  # type: ignore[attr-defined]
        return True


# ---------------------------------------------------------------- formatters

class JsonFormatter(logging.Formatter):
    """One JSON object per line, stable key set, never raises on odd data."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": self.formatMessage(record),
        }
        request_id = getattr(record, "request_id", None)
        if request_id:
            entry["request_id"] = request_id
        job_id = getattr(record, "job_id", None)
        if job_id is not None:
            entry["job_id"] = job_id
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False, default=str)


# ------------------------------------------------------------------- setup

def setup_logging(level: int = logging.INFO, json_output: bool = False,
                  service: str = "nexus") -> None:
    """Configure root logging once for the whole application."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    handler = logging.StreamHandler(sys.stdout)
    if json_output:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)-7s %(name)s — %(message)s%(context_tag)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
    handler.addFilter(ContextFilter())

    root = logging.getLogger("nexus")
    root.setLevel(level)
    root.handlers = [handler]
    root.propagate = False

    # Third-party noise we would rather not see in a demo run.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"nexus.{name}")
