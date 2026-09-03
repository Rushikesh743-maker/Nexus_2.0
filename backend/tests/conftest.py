"""
Shared fixtures.

The graph build reads the whole corpus off disk and runs extraction and
resolution, so it is built once per session and shared. Every test treats it as
read-only — a test that mutated it would silently change the others, and the
engine's own contract is that it never writes to the graph.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.graph.build import build_graph                     # noqa: E402
from app.intelligence.contradiction_engine import ContradictionEngine  # noqa: E402


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
