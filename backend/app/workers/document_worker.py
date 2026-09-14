"""Standalone document processing worker.

Production deployment shape: the API nodes stay pure web servers
(``WORKER_ENABLED=false``) and one or more of these processes drain the
``document_processing_job`` queue. In development the same worker runs
inside the API process, so this entry point is optional there.

    python -m app.workers.document_worker
"""

from __future__ import annotations

import logging
import signal
import sys

from ..core.config import get_settings
from ..core.database import db_ready, init_database
from ..core.logging import setup_logging
from ..services.processing_worker import (DocumentProcessingWorker,
                                          register_standalone_worker)


def main() -> int:
    settings = get_settings()
    setup_logging(json_output=(settings.log_format == "json"))
    log = logging.getLogger("nexus.worker.standalone")

    if not (db_ready() or init_database()):
        log.error("Cannot reach the platform database — the worker has "
                  "nothing to do. Exiting.")
        return 1

    worker = DocumentProcessingWorker()
    register_standalone_worker(worker)
    worker.start()
    log.info("Standalone document worker running (pid=%s). "
             "Send SIGTERM to stop.", __import__("os").getpid())

    # Block until the OS asks us to stop; SIGTERM/SIGINT -> clean exit.
    import threading
    stop = threading.Event()

    def _handle(signum, _frame):  # noqa: ANN001
        log.info("Signal %s received — stopping", signum)
        stop.set()

    signal.signal(signal.SIGTERM, _handle)
    signal.signal(signal.SIGINT, _handle)
    stop.wait()

    worker.stop()
    log.info("Standalone document worker stopped cleanly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
