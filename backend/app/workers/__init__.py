"""Standalone workers (phase 1, production deployment).

Each worker here is the SAME code that runs in-process with the API in
development — only the process boundary differs. Run with:

    python -m app.workers.document_worker

The worker coordinates with every other worker (including an in-process
one, if any) purely through the database queue, so several copies may run
concurrently without double-processing.
"""
