"""Unit tests for the deterministic extraction and resolution layer.

No database and no network: the rule provider runs in-process and every
expectation is a documented behaviour (confidence values, provenance
locations, the relationship trigger phrases). The LLM path is tested only
for its validation contract — malformed output must be rejected, never
persisted.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.document_processor import ProcessingError  # noqa: E402
from app.services.entity_extraction import (  # noqa: E402
    DocumentContent, ExtractionError, LLMExtractionProvider,
    RuleBasedExtractionProvider, SourceRef)
from app.services.entity_resolution import best_match, score_pair  # noqa: E402


def _txt(doc_id: int, *lines: str) -> DocumentContent:
    return DocumentContent(
        document_id=doc_id, kind="txt",
        raw_text="\n".join(lines),
        lines=[(i, line) for i, line in enumerate(lines, start=1)],
    )


FIR_LINES = [
    "SYNTHETIC DEMONSTRATION DATA",
    "The complainant, Mr. Vikram Rao, stated that a vehicle MH01GH9876 was seen.",
    "The suspect was named Suresh Kulkarni.",
    "The vehicle MH01GH9876 owned by Suresh Kulkarni was parked there.",
    "Vikram Rao called 9822044117 to report the incident.",
    "Ms. Neha Patil arrived in vehicle MH12AB1234.",
    "A transfer of Rs. 20000 was made from AXIS501104 to SBI123456.",
    "03/05/2026 - The complainant noticed suspicious activity.",
    "Reference CASE-2026-001.",
]

# The case's confirmed vocabulary: "Vikram Rao" is already a confirmed
# person entity in this case, so the gazetteer path is exercised too.
CASE_ENTITIES = {"person": ["Vikram Rao"]}


@pytest.fixture(scope="module")
def fir_result():
    provider = RuleBasedExtractionProvider()
    return provider.extract(_txt(1, *FIR_LINES), CASE_ENTITIES)


# ----------------------------------------------------------------- entities

class TestTextEntities:
    def test_case_reference(self, fir_result):
        e = next(x for x in fir_result.entities if x.type == "case")
        assert e.name == "CASE-2026-001"
        assert e.confidence == 0.98
        assert e.method == "pattern:case_reference"
        assert e.source.line == 9

    def test_phone_number(self, fir_result):
        e = next(x for x in fir_result.entities if x.type == "phone")
        assert e.name == "9822044117"
        assert e.confidence == 0.95
        assert e.source.line == 5

    def test_vehicle(self, fir_result):
        vs = [x for x in fir_result.entities if x.type == "vehicle"]
        assert {v.name for v in vs} == {"MH01GH9876", "MH12AB1234"}
        assert all(v.confidence == 0.95 for v in vs)

    def test_accounts(self, fir_result):
        a = {x.name for x in fir_result.entities if x.type == "account"}
        assert a == {"AXIS501104", "SBI123456"}
        assert all(x.confidence == 0.80 for x in fir_result.entities
                   if x.type == "account")

    def test_named_person_with_title(self, fir_result):
        names = {x.name for x in fir_result.entities if x.type == "person"}
        assert {"Vikram Rao", "Neha Patil", "Suresh Kulkarni"} <= names
        suresh = next(x for x in fir_result.entities
                      if x.type == "person" and x.name == "Suresh Kulkarni")
        assert suresh.method == "pattern:named"
        assert suresh.confidence == 0.70

    def test_event_with_timestamp(self, fir_result):
        e = next(x for x in fir_result.entities if x.type == "event")
        assert e.name.startswith("03/05/2026")
        assert e.confidence == 0.80
        assert e.source.value == "03/05/2026"
        assert e.source.line == 8
        assert "03/05/2026" not in e.name.split(" — ", 1)[1]

    def test_in_document_dedupe(self, fir_result):
        """Vikram Rao is mentioned on lines 2 and 5. On line 2 both the
        title pattern (0.60) and the case gazetteer (0.90) match: exactly
        one candidate survives per (type, name, line), at the higher
        confidence."""
        vikram = [x for x in fir_result.entities
                  if x.type == "person" and x.name == "Vikram Rao"]
        assert {x.source.line for x in vikram} == {2, 5}
        assert all(x.confidence == 0.90 and x.method == "gazetteer:case"
                   for x in vikram)
        line2 = [x for x in vikram if x.source.line == 2]
        assert len(line2) == 1  # the 0.60 title-pattern twin was deduped

    def test_provenance_never_invented(self, fir_result):
        for e in fir_result.entities:
            assert e.source is not None
            assert e.source.line is not None
            assert e.source.snippet


# ------------------------------------------------------------- relationships

class TestTextRelationships:
    def _by_type(self, fir_result, rel_type):
        return [r for r in fir_result.relationships
                if r.relationship_type == rel_type]

    def test_called(self, fir_result):
        rels = self._by_type(fir_result, "CALLED")
        assert rels and rels[0].source_name == "Vikram Rao"
        assert rels[0].target_name == "9822044117"
        assert rels[0].confidence == 0.80

    def test_owns_vehicle(self, fir_result):
        rels = self._by_type(fir_result, "OWNS")
        assert rels
        r = rels[0]
        assert (r.source_name, r.target_name) == ("Suresh Kulkarni", "MH01GH9876")
        assert r.confidence == 0.85

    def test_used_vehicle(self, fir_result):
        rels = self._by_type(fir_result, "USED")
        assert rels
        r = rels[0]
        assert (r.source_name, r.target_name) == ("Neha Patil", "MH12AB1234")
        assert r.confidence == 0.75

    def test_transferred_to(self, fir_result):
        rels = self._by_type(fir_result, "TRANSFERRED_TO")
        assert rels
        r = rels[0]
        assert (r.source_name, r.target_name) == ("AXIS501104", "SBI123456")
        assert r.confidence == 0.85

    def test_no_relationship_without_connective(self):
        """Co-occurrence in the same line is not a basis: a person and a
        vehicle on one line without a stated link must not yield a pair."""
        provider = RuleBasedExtractionProvider()
        result = provider.extract(
            _txt(2, "The person Rajan Dhar and the car KA01TR1111 were noted."),
            {})
        assert result.relationships == []

    def test_every_relationship_carries_support(self, fir_result):
        for r in fir_result.relationships:
            assert r.supporting is not None
            assert r.supporting.snippet
            assert 0.0 < r.confidence <= 1.0
            assert r.method.startswith("rule:")


# --------------------------------------------------------------------- CSV

def _csv(columns, rows):
    return DocumentContent(
        document_id=3, kind="csv", raw_text="",
        csv_columns=list(columns),
        csv_rows=[(i, dict(zip(columns, row))) for i, row in enumerate(rows, 1)],
    )


class TestCsvExtraction:
    def test_cdr_row(self):
        provider = RuleBasedExtractionProvider()
        content = _csv(
            ["call_id", "timestamp", "caller", "caller_name", "callee",
             "callee_name", "duration_s", "cell_tower", "case_ref"],
            [["CDR-001", "03/05/2026 08:41:12", "9822044117", "Vikram Rao",
              "9000000001", "Suresh Kulkarni", "124", "Kurla Tower 4",
              "CASE-2026-001"]],
        )
        result = provider.extract(content, {})
        types = {(e.type, e.name) for e in result.entities}
        assert ("phone", "9822044117") in types
        assert ("person", "Vikram Rao") in types
        assert ("location", "Kurla Tower 4") in types
        assert ("case", "CASE-2026-001") in types
        # provenance is row + column, never a page
        person = next(e for e in result.entities if e.name == "Vikram Rao")
        assert person.source.row == 1
        assert person.source.column == "caller_name"
        rel_types = {r.relationship_type for r in result.relationships}
        assert {"CALLED", "OWNS", "LOCATED_AT", "INVOLVED_IN"} <= rel_types
        for r in result.relationships:
            assert r.supporting.row == 1

    def test_unknown_columns_ignored(self):
        provider = RuleBasedExtractionProvider()
        content = _csv(["id", "person", "phone", "nonsense_col"],
                       [["1", "Asha Borkar", "9988776655", "???"]])
        result = provider.extract(content, {})
        names = {e.name for e in result.entities if e.type == "person"}
        assert "Asha Borkar" in names
        # the unknown column contributes nothing
        assert all("???" != e.name for e in result.entities)

    def test_transfer_columns(self):
        provider = RuleBasedExtractionProvider()
        content = _csv(["date", "from_account", "to_name", "to_account", "amount"],
                       [["01/05/2026", "AXIS501104", "Suresh Kulkarni",
                         "SBI123456", "20000"]])
        result = provider.extract(content, {})
        assert any(r.relationship_type == "TRANSFERRED_TO"
                   for r in result.relationships)


# ---------------------------------------------------------- case gazetteer

class TestCaseGazetteer:
    def test_case_entity_names_are_first_class(self):
        provider = RuleBasedExtractionProvider()
        content = _txt(4, "The officer noticed Vikram Rao near the gate.")
        result = provider.extract(content, {"person": ["Vikram Rao"]})
        vikram = [e for e in result.entities
                  if e.type == "person" and e.name == "Vikram Rao"]
        assert vikram
        # highest confidence wins (gazetteer:case 0.90 > pattern 0.70)
        assert vikram[0].confidence == 0.90
        assert vikram[0].method == "gazetteer:case"

    def test_located_at_needs_known_location(self):
        provider = RuleBasedExtractionProvider()
        line = "The officer found Mr. Vikram Rao standing near Dadar."
        with_loc = provider.extract(
            _txt(5, line), {"location": ["Dadar"]})
        located = [r for r in with_loc.relationships
                   if r.relationship_type == "LOCATED_AT"]
        assert located
        assert (located[0].source_name, located[0].target_name) == \
            ("Vikram Rao", "Dadar")
        without = provider.extract(_txt(6, line), {})
        assert not any(r.relationship_type == "LOCATED_AT"
                       for r in without.relationships)


# ---------------------------------------------------------------- resolution

class TestResolution:
    def test_exact_match(self):
        name, sim, reasons = best_match("Vikram Rao", ["Vikram Rao"])
        assert (name, sim) == ("Vikram Rao", 1.0)
        assert reasons

    def test_initial_plus_surname(self):
        name, sim, reasons = best_match("V. Rao", ["Vikram Rao"])
        assert name == "Vikram Rao"
        assert 0.8 <= sim <= 0.9
        assert any("initial" in r for r in reasons)

    def test_token_overlap(self):
        name, sim, reasons = best_match("Neha P. Patil", ["Neha Patil"])
        assert name == "Neha Patil"
        assert sim >= 0.55
        assert reasons

    def test_below_threshold_is_no_match(self):
        name, sim, _ = best_match("Suresh Kulkarni", ["Vikram Rao"])
        assert name is None and sim == 0.0

    def test_best_of_many(self):
        name, sim, _ = best_match("Vikram Rao", ["Kabir Shah", "Vikram Rao"])
        assert name == "Vikram Rao" and sim == 1.0

    def test_phone_identifiers_are_exact_only(self):
        # One digit of difference is a different phone, not a typo.
        name, sim, _ = best_match("9000000102", ["9000000101"])
        assert name is None and sim == 0.0
        name, sim, _ = best_match("9000000102", ["9000000102"])
        assert name == "9000000102" and sim == 1.0

    def test_vehicle_registration_is_exact_only(self):
        name, sim, _ = best_match("MH01AB1235", ["MH01AB1234"])
        assert name is None and sim == 0.0

    def test_reasons_are_data_supported(self):
        _, _, reasons = best_match("V. Rao", ["Vikram Rao"])
        for r in reasons:
            assert isinstance(r, str) and r
            assert "because the model guessed" not in r


# ------------------------------------------------------------- LLM contract

def _patch_llm(monkeypatch, llm_json: str):
    """Point the LLM provider at a stubbed endpoint returning `llm_json`."""
    import httpx

    from app.core.config import get_settings

    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_PROVIDER", "openai-compatible")
    get_settings.cache_clear()

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": llm_json}}]}

    monkeypatch.setattr(httpx, "post", lambda *a, **k: _Resp())
    return LLMExtractionProvider()


class TestLLMContract:
    def test_malformed_json_rejected(self, monkeypatch):
        provider = _patch_llm(monkeypatch, "not json at all")
        content = _txt(6, "Some text.")
        with pytest.raises(ExtractionError):
            provider.extract(content, {})

    def test_invalid_entity_type_rejected(self, monkeypatch):
        payload = ('{"entities": [{"name": "X", "type": "Alien", '
                   '"confidence": 0.9, "source": {"snippet": "x"}}], '
                   '"relationships": []}')
        provider = _patch_llm(monkeypatch, payload)
        content = _txt(7, "Some text.")
        with pytest.raises(ExtractionError):
            provider.extract(content, {})

    def test_valid_payload_is_accepted(self, monkeypatch):
        payload = ('{"entities": [{"name": "Vikram Rao", "type": "person", '
                   '"confidence": 0.9, "method": "llm", '
                   '"source": {"snippet": "the complainant"}}], '
                   '"relationships": [], "warnings": []}')
        provider = _patch_llm(monkeypatch, payload)
        content = _txt(8, "Some text.")
        result = provider.extract(content, {})
        assert len(result.entities) == 1
        assert result.entities[0].method == "llm"
        assert result.entities[0].source.document_id == 8
