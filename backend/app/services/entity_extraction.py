"""Entity & relationship extraction.

Provider abstraction over two implementations:

* ``RuleBasedExtractionProvider`` — deterministic patterns + gazetteers, no
  external credentials, fully offline. This is the default and is what the
  synthetic-corpus demo runs on.
* ``LLMExtractionProvider`` — an OpenAI-compatible chat endpoint behind the
  same contract. It is only used when ``LLM_PROVIDER`` is configured; its
  output is validated with Pydantic and rejected on any malformation (the
  provider can never write to the database directly — it returns structured
  data that the document service persists).

CONFIDENCE METHODOLOGY (deterministic; no random values):

  0.98  exact case-reference pattern (CASE-YYYY-NNN)
  0.95  phone / vehicle format patterns (fully format-validated)
  0.90  name found in the case's own confirmed entities (gazetteer:case)
  0.80  account format pattern; corpus gazetteer names (gazetteer:corpus);
        event with an explicit timestamp
  0.70-0.75  structural person patterns (namely X, Subject X, titled name)
  0.60-0.65  loose person / organization-suffix patterns
  0.70-0.90  relationships, per rule (see the rule tables below)

Every candidate carries a ``method`` ("pattern:...", "gazetteer:...",
"rule:column_pair_...", "rule:text_...") and a source location; nothing is
emitted without both. Extraction confidence is deliberately distinct from
investigator verification — acceptance is a separate, audited decision.
"""

from __future__ import annotations

import logging
import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from functools import lru_cache

from pydantic import BaseModel, Field, field_validator

from ..core.config import get_settings

logger = logging.getLogger("nexus.extraction")


# --------------------------------------------------------------------- model

class SourceRef(BaseModel):
    """Where a fact came from. Unavailable locations are represented, not
    invented: ``available`` is False when no precise location exists."""

    # Optional on input: the provider stamps the authoritative document_id
    # after validation (the LLM is told it, but omitting it must not fail the
    # whole document — we always already know the real id).
    document_id: int | str | None = None
    page: int | None = None
    row: int | None = None
    column: str | None = None
    value: str | None = None
    line: int | None = None
    snippet: str | None = None
    available: bool = True


class ExtractedEntity(BaseModel):
    type: str  # person | phone | vehicle | location | account | organization | case | event
    name: str
    aliases: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    method: str
    source: SourceRef


class ExtractedRelationship(BaseModel):
    source_type: str
    source_name: str
    target_type: str
    target_name: str
    relationship_type: str  # CALLED | OWNS | USED | LOCATED_AT | ...
    confidence: float = Field(ge=0.0, le=1.0)
    method: str
    supporting: SourceRef

    @field_validator("relationship_type")
    @classmethod
    def _known_type(cls, v: str) -> str:
        allowed = {"CALLED", "OWNS", "USED", "LOCATED_AT", "ASSOCIATED_WITH",
                   "INVOLVED_IN", "TRANSFERRED_TO", "MENTIONED_IN",
                   "CONNECTED_TO", "OCCURRED_AT"}
        if v not in allowed:
            raise ValueError(f"unsupported relationship type {v!r}")
        return v


class ExtractedClaim(BaseModel):
    """A structured claim extracted from a document line (stage 5).

    Structured claims — not free text — are the only legitimate input to
    the evidence-contradiction rule: subject, predicate, object, time and
    location must all be explicit. Claims are materialized to confirmed
    ``evidence_claim`` rows only when their subject candidate is accepted.
    """

    subject_type: str            # person | phone | vehicle | account | organization
    subject_name: str            # canonical name (language-neutral)
    predicate: str               # was_at | present_at | called | owns | ...
    object_type: str | None = None
    object_name: str | None = None
    object_value: str | None = None      # plain value when object is not an entity
    event_time: str | None = None        # "YYYY-MM-DD HH:MM[:SS]" or "DD/MM/YYYY"
    location_name: str | None = None     # canonical location (when predicate is spatial)
    language: str | None = None          # en | hi | mr | ur
    confidence: float = Field(ge=0.0, le=1.0)
    method: str
    source: SourceRef


class ExtractionResult(BaseModel):
    entities: list[ExtractedEntity] = Field(default_factory=list)
    relationships: list[ExtractedRelationship] = Field(default_factory=list)
    claims: list[ExtractedClaim] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    # Detected language (stage 5): {"code", "name", "script",
    # "confidence", "signals"} — None when undetermined.
    language: dict | None = None


class ExtractionError(Exception):
    """Raised when a provider cannot produce valid structured output.

    The document is then marked FAILED with this message — never partially
    persisted, never faked."""


# ------------------------------------------------------------------- content

@dataclass
class DocumentContent:
    """Normalized, memory-capped view of a stored document."""

    document_id: int
    kind: str  # pdf | txt | csv | image
    raw_text: str = ""
    pages: list[dict] = field(default_factory=list)      # pdf/image: {page, chars, text_head, ocr?}
    lines: list[tuple[int, str]] = field(default_factory=list)  # txt: (1-based line, text)
    csv_columns: list[str] = field(default_factory=list)
    csv_rows: list[tuple[int, dict]] = field(default_factory=list)  # (1-based data row, values)
    # Phase 1: how many pages were OCR'd (0 = pure text layer / no OCR)
    ocr_pages: int = 0


# ----------------------------------------------------------------- gazetteer

@dataclass(frozen=True)
class Gazetteer:
    persons: frozenset = frozenset()
    locations: frozenset = frozenset()
    organizations: frozenset = frozenset()


_ORG_SUFFIX = re.compile(
    r"(?i)\b(?:Pvt\.?\s*Ltd\.?|Ltd\.?|LLC|Corporation|Company|Firm|"
    r"Traders|Exim|Industries|Enterprises|Group|Agency|Bureau)\b")


@lru_cache(maxsize=1)
def _load_corpus_gazetteer() -> Gazetteer:
    """Names from the synthetic corpus (data/raw). The corpus is the same
    synthetic data the case files were seeded from, so these gazetteers are
    reproducible and fictional. Missing corpus => empty gazetteer, patterns
    still run."""
    import csv as _csv
    import json

    base = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))))), "data", "raw")
    persons: set[str] = set()
    locations: set[str] = set()
    orgs: set[str] = set()

    def _add_person(name: str | None) -> None:
        name = (name or "").strip()
        if len(name) >= 4 and " " in name and not _ORG_SUFFIX.search(name):
            persons.add(name.title() if name.islower() else name)

    def _add_location(name: str | None) -> None:
        name = (name or "").strip()
        if 3 <= len(name) <= 60:
            locations.add(name)

    try:
        with open(os.path.join(base, "criminal_records.csv"), encoding="utf-8") as fh:
            for row in _csv.DictReader(fh):
                _add_person(row.get("name"))
        with open(os.path.join(base, "transactions.csv"), encoding="utf-8") as fh:
            for row in _csv.DictReader(fh):
                for key in ("from_name", "to_name"):
                    name = (row.get(key) or "").strip()
                    if _ORG_SUFFIX.search(name):
                        orgs.add(name)
                    else:
                        _add_person(name)
        with open(os.path.join(base, "cdr.csv"), encoding="utf-8") as fh:
            for row in _csv.DictReader(fh):
                _add_location(row.get("cell_tower"))
        with open(os.path.join(base, "surveillance.json"), encoding="utf-8") as fh:
            for rec in json.load(fh):
                _add_location(rec.get("location"))
        with open(os.path.join(base, "social_media.json"), encoding="utf-8") as fh:
            for rec in json.load(fh):
                _add_location(rec.get("geo_hint"))
        with open(os.path.join(base, "firs.json"), encoding="utf-8") as fh:
            for rec in json.load(fh):
                _add_location(rec.get("station"))
    except FileNotFoundError:
        return Gazetteer()
    return Gazetteer(persons=frozenset(persons),
                     locations=frozenset(locations),
                     organizations=frozenset(orgs))


def _norm_name(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip().casefold())


# ------------------------------------------------- multilingual (stage 5)
@dataclass(frozen=True)
class AliasRegistry:
    """canonical name -> {lang: [surface forms]} per entity type.

    Loaded from data/raw/multilingual_aliases.json (SYNTHETIC DEMONSTRATION
    DATA). This is data, not logic: the extractor matches a surface form in
    the document and emits the canonical name, keeping the case graph
    language-neutral. Missing file => empty registry, patterns still run.
    """

    by_type: dict = field(default_factory=dict)  # etype -> canonical -> {lang: [forms]}


@lru_cache(maxsize=1)
def _load_multilingual_aliases() -> AliasRegistry:
    base = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))))), "data", "raw")
    try:
        import json as _json

        with open(os.path.join(base, "multilingual_aliases.json"),
                  encoding="utf-8") as fh:
            payload = _json.load(fh)
    except (FileNotFoundError, ValueError):
        return AliasRegistry()
    by_type: dict = {}
    for etype, canonicals in (payload.get("entities") or {}).items():
        for canonical, forms in (canonicals or {}).items():
            by_type.setdefault(etype, {})[canonical] = {
                lang: list(value or []) for lang, value in (forms or {}).items()
                if lang in ("en", "hi", "mr", "ur")}
    return AliasRegistry(by_type=by_type)


# Language-specific spatial connectives (a claim/LOCATED_AT needs one of
# these near the location) and communication verbs (CALLED rule).
_MULTILINGUAL_CONNECTIVES = {
    "hi": ("में", "पर", "से", "पास", "देखा", "स्थित"),
    "mr": ("मध्ये", "ला", "वरील", "जवळ", "दिसून", "आढळून", "स्थित"),
    "ur": ("میں", "پر", "پاس", "نظر", "دیکھا", "موجود"),
}
_MULTILINGUAL_CALLED = {
    "hi": ("बात", "बातचीत", "संवाद", "कॉल"),
    "mr": ("संवाद", "संपर्क", "बात", "कॉल"),
    "ur": ("رابطہ", "بات", "مکالمہ", "کال"),
}

# Devanagari / arabic word-ish sequences for the unknown-name pattern.
# Devanagari range ends at U+095F on purpose: danda (। U+0964), digits
# (U+0966+) and the rupee sign are not name material.
_RE_DEV_NAME = re.compile(r"[\u0900-\u095F]{3,16}")
# Arabic name material: base letters + Urdu extensions (pe, gaf, che,
# heh ہ, ھ, jeh, yeh ی/ے, rolled r, alef maqsura, superscript alef).
_RE_AR_NAME = re.compile(
    r"[\u0621-\u064A\u0670\u0671\u0679\u067E-\u06AF\u0681\u0686\u068A"
    r"\u0698\u06A9\u06BA\u06BE\u06C1\u06CC\u06D2]{2,14}")


def _title_latin(text: str) -> str:
    parts = (text or "").strip().split(" ")
    return " ".join(p[:1].upper() + p[1:] for p in parts if p)


# -------------------------------------------------------------------- rules

RE_CASE_REF = re.compile(r"\bCASE-\d{4}-\d{3,}\b")
RE_PHONE = re.compile(r"(?<!\d)(?:\+91[\s-]?)?9\d{9}(?!\d)")
RE_VEHICLE = re.compile(r"(?<![A-Z0-9])[A-Z]{2}\d{1,2}[A-Z]{1,2}\d{3,4}(?!\d)")
RE_ACCOUNT = re.compile(r"(?<![A-Z0-9])[A-Z]{2,5}\d{4,6}(?!\d)")
RE_TITLE_NAME = re.compile(r"\b(?:Mr|Mrs|Ms|Dr)\.?\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\b")
RE_INITIAL_NAME = re.compile(r"\b([A-Z])\.\s+([A-Z][a-z]{2,})\b")
RE_NAMED = re.compile(
    r"\bnamed(?:ly)?\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})"
    r"(?:\s+and\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2}))?")
RE_SUBJECT = re.compile(r"\bSubject\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b")
RE_ORG = re.compile(
    r"\b[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)*\s+"
    r"(?:Pvt\.?\s*Ltd\.?|Ltd\.?|LLC|Corporation|Company|Firm|Traders|Exim|"
    r"Industries|Enterprises|Group)\b")
RE_TS_ISO = re.compile(r"\b(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}(?::\d{2})?)\b")
RE_TS_DMY = re.compile(r"\b(\d{2}/\d{2}/\d{4})\b")

# Text connective rules: a relationship is only proposed when the sentence
# itself states it. Co-occurrence in the same document is NOT a basis.
RE_TEXT_CALLED = re.compile(
    r"((?:\+91[\s-]?)?9\d{9}|\b[A-Z][a-z]+\s+[A-Z][a-z]+\b)\s+called\s+"
    r"((?:\+91[\s-]?)?9\d{9}|\b[A-Z][a-z]+\s+[A-Z][a-z]+\b)", re.I)
RE_TEXT_VEHICLE_OWNER = re.compile(
    r"vehicle\s+([A-Z]{2}\d{1,2}[A-Z]{1,2}\d{3,4})\b.{0,60}?\b(?:of|registered to|owned by)\s+"
    r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)", re.I | re.S)
RE_TEXT_ARRIVED_VEHICLE = re.compile(
    r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+arrived in (?:a |the )?vehicle\s+"
    r"([A-Z]{2}\d{1,2}[A-Z]{1,2}\d{3,4})", re.I)
RE_TEXT_TRANSFER = re.compile(
    r"transfer(?:red)?\b.{0,40}?\bfrom\s+([A-Z]{2,5}\d{4,6})\b.{0,40}?\bto\s+([A-Z]{2,5}\d{4,6})",
    re.I)

# CSV column aliases -> canonical field.
_CSV_ALIASES = {
    "person": {"person", "name", "party", "individual", "suspect", "person_name", "full_name"},
    "phone": {"phone", "mobile", "phone_number", "contact", "handset", "number", "caller", "callee", "call_from", "call_to"},
    "vehicle": {"vehicle", "vehicle_no", "vehicle_number", "reg_no", "registration", "vehicle_registration"},
    "location": {"location", "place", "address", "area", "cell_tower", "station", "city"},
    "timestamp": {"timestamp", "time", "datetime", "date_time", "start_time", "registered_on", "observed_on", "posted_on", "date"},
    "account": {"account", "account_no", "bank_account", "from_account", "to_account", "acct"},
    "organization": {"organization", "org", "company", "firm", "organisation"},
    "case_reference": {"case", "case_number", "case_ref", "case_reference"},
}


def _classify_name_value(value: str) -> str:
    """A transaction 'name' column holds either a person or an organization."""
    v = (value or "").strip()
    if _ORG_SUFFIX.search(v):
        return "organization"
    return "person"


def _snippet(text: str, limit: int = 240) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _gazetteer_hits(text: str, names: frozenset) -> list[str]:
    """Corpus names present in the text at word boundaries, in text order.

    A boundary is the start/end of the text or any non-word character, so
    names at the end of a sentence ("...driver Nadeem Ansari.") and names
    carrying initials ("R. Kumar") still match, while partial words
    ("...ankiran deshpande") never do. Results are ordered by first
    occurrence so downstream order-sensitive rules (e.g. the
    LOCATED_AT connective rule, which takes the first person of the text
    item) are deterministic.
    """
    low = (text or "").casefold()
    found: list[tuple[int, str]] = []
    for name in names:
        if len(name) < 4:
            continue
        m = re.search(r"(?<!\w)" + re.escape(_norm_name(name)) + r"(?!\w)",
                      low)
        if m:
            found.append((m.start(), name))
    return [name for _, name in sorted(found)]


# 1-4 capitalized words (initials like "R. Kumar" allowed) — used by the
# latin was_at claim sentence patterns on RuleBasedExtractionProvider.
_EN_CLAIM_NAME_1_4 = r"[A-Z][A-Za-z.]+(?:\s+[A-Z][A-Za-z.]+){0,3}"


# ----------------------------------------------------------------- provider

class ExtractionProvider(ABC):
    name = "abstract"

    @abstractmethod
    def extract(self, content: DocumentContent,
                case_entities: dict[str, list[str]] | None = None) -> ExtractionResult:
        """Return a validated ExtractionResult or raise ExtractionError.

        ``case_entities`` maps entity_type -> [names+aliases] for the case,
        letting the provider treat the case's confirmed vocabulary as a
        first-class gazetteer.
        """


class RuleBasedExtractionProvider(ExtractionProvider):
    name = "rules"

    def __init__(self, corpus_gazetteer: Gazetteer | None = None):
        self.corpus = corpus_gazetteer or _load_corpus_gazetteer()

    # -- public ----------------------------------------------------------
    def extract(self, content: DocumentContent,
                case_entities: dict[str, list[str]] | None = None) -> ExtractionResult:
        case_entities = case_entities or {}
        result = ExtractionResult()
        lang_code: str | None = None
        if content.kind != "csv":
            from .language import detect_language

            lang_info = detect_language(content.raw_text or "")
            if lang_info is not None:
                result.language = lang_info.__dict__
                lang_code = lang_info.code
        if content.kind == "csv":
            self._extract_csv(content, case_entities, result)
        else:
            self._extract_text(content, case_entities, result)
            if lang_code in ("hi", "mr", "ur"):
                self._extract_multilingual(content, case_entities, result, lang_code)
            elif lang_code in ("en", None):
                # English (and undetermined) documents additionally get the
                # structured was_at claim pattern — additive; the claim is
                # only a candidate until its subject is accepted.
                self._extract_claims_en(content, case_entities, result)
        self._dedupe_in_document(result)
        if not result.entities and not result.relationships and not result.claims:
            result.warnings.append("No extractable entities or relationships were detected.")
        return result

    # -- text (pdf pages / txt lines) ------------------------------------
    def _extract_text(self, content: DocumentContent, case_entities, result):
        for item in self._text_items(content):
            location = item["location"]
            text = item["text"]
            if not text.strip():
                continue

            def src() -> SourceRef:
                ref = SourceRef(document_id=content.document_id, snippet=_snippet(text))
                for key in ("page", "line"):
                    if location.get(key) is not None:
                        setattr(ref, key, location[key])
                return ref

            # --- pattern entities (order matters: refs before names) ----
            for m in RE_CASE_REF.finditer(text):
                result.entities.append(ExtractedEntity(
                    type="case", name=m.group(0), confidence=0.98,
                    method="pattern:case_reference", source=src()))
            for m in RE_PHONE.finditer(text):
                result.entities.append(ExtractedEntity(
                    type="phone", name=m.group(0).replace(" ", "").replace("-", ""),
                    confidence=0.95, method="pattern:phone", source=src()))
            for m in RE_VEHICLE.finditer(text):
                result.entities.append(ExtractedEntity(
                    type="vehicle", name=m.group(0), confidence=0.95,
                    method="pattern:vehicle", source=src()))
            for m in RE_ACCOUNT.finditer(text):
                result.entities.append(ExtractedEntity(
                    type="account", name=m.group(0), confidence=0.80,
                    method="pattern:account", source=src()))

            # --- case-entity gazetteer ----------------------------------
            # Every known name present on the line is emitted (a line may
            # mention several people); same-line duplicates of one name are
            # collapsed by _dedupe_in_document, cross-line duplicates keep
            # their provenance.
            for etype in ("person", "vehicle", "location", "organization", "phone", "account"):
                for name in case_entities.get(etype, []):
                    if len(name) < 4 or not re.search(r"[A-Za-z]", name):
                        continue
                    if _norm_name(name) in _norm_name(text):
                        result.entities.append(ExtractedEntity(
                            type=etype, name=name, confidence=0.90,
                            method="gazetteer:case", source=src()))

            # --- corpus gazetteer ----------------------------------------
            for name in _gazetteer_hits(text, self.corpus.persons):
                if _norm_name(name) not in { _norm_name(e.name) for e in result.entities if e.type == "person" }:
                    result.entities.append(ExtractedEntity(
                        type="person", name=name, confidence=0.80,
                        method="gazetteer:corpus", source=src()))
            for name in _gazetteer_hits(text, self.corpus.locations):
                if _norm_name(name) not in { _norm_name(e.name) for e in result.entities if e.type == "location" }:
                    result.entities.append(ExtractedEntity(
                        type="location", name=name, confidence=0.80,
                        method="gazetteer:corpus", source=src()))
            for name in _gazetteer_hits(text, self.corpus.organizations):
                if _norm_name(name) not in { _norm_name(e.name) for e in result.entities if e.type == "organization" }:
                    result.entities.append(ExtractedEntity(
                        type="organization", name=name, confidence=0.80,
                        method="gazetteer:corpus", source=src()))

            # --- structural person patterns ------------------------------
            for m, conf, meth in (
                (RE_TITLE_NAME.finditer(text), 0.60, "pattern:title_name"),
                (RE_SUBJECT.finditer(text), 0.75, "pattern:subject"),
            ):
                for mm in m:
                    name = mm.group(1).strip()
                    if len(name.split()) >= 2 and not _ORG_SUFFIX.search(name):
                        result.entities.append(ExtractedEntity(
                            type="person", name=name, confidence=conf,
                            method=meth, source=src()))
            for mm in RE_NAMED.finditer(text):
                for group in (mm.group(1), mm.group(2)):
                    if not group:
                        continue
                    name = group.strip()
                    if len(name.split()) >= 2 and not _ORG_SUFFIX.search(name):
                        result.entities.append(ExtractedEntity(
                            type="person", name=name, confidence=0.70,
                            method="pattern:named", source=src()))
            for mm in RE_INITIAL_NAME.finditer(text):
                name = f"{mm.group(1)}. {mm.group(2)}"
                if not _ORG_SUFFIX.search(mm.group(2)):
                    result.entities.append(ExtractedEntity(
                        type="person", name=name, confidence=0.60,
                        method="pattern:initial_name", source=src()))
            for m in RE_ORG.finditer(text):
                result.entities.append(ExtractedEntity(
                    type="organization", name=m.group(0), confidence=0.65,
                    method="pattern:org_suffix", source=src()))

            # --- events: explicit timestamp + what the line says ----------
            ts_iso = RE_TS_ISO.search(text)
            ts_dmy = None if ts_iso else RE_TS_DMY.search(text)
            if ts_iso:
                stamp = f"{ts_iso.group(1)} {ts_iso.group(2)}"
            elif ts_dmy:
                stamp = ts_dmy.group(1)
            else:
                stamp = None
            if stamp:
                lead = _snippet(re.sub(r"\d{2}/\d{2}/\d{4}|\d{2}[:/]\d{2}(:\d{2})?|\d{4}-\d{2}-\d{2}", "", text), 120)
                result.entities.append(ExtractedEntity(
                    type="event", name=f"{stamp} — {lead[:60]}", confidence=0.80,
                    method="pattern:timestamp",
                    source=SourceRef(document_id=content.document_id, snippet=_snippet(text),
                                     value=stamp, **{k: v for k, v in location.items()})))

            # --- connective relationship rules ----------------------------
            # finditer, not search: a page (PDF) or a long line can state
            # several links; each is its own candidate. In-document dedupe
            # collapses identical (source, type, target) pairs.
            for m in RE_TEXT_CALLED.finditer(text):
                self._text_pair(result, m.group(1), m.group(2), "CALLED", 0.80, src())
            for m in RE_TEXT_VEHICLE_OWNER.finditer(text):
                self._text_pair(result, m.group(2), m.group(1), "OWNS", 0.85, src())
            for m in RE_TEXT_ARRIVED_VEHICLE.finditer(text):
                self._text_pair(result, m.group(1), m.group(2), "USED", 0.75, src())
            for m in RE_TEXT_TRANSFER.finditer(text):
                self._text_pair(result, m.group(1), m.group(2), "TRANSFERRED_TO", 0.85, src())
            # LOCATED_AT: person + known location + spatial connective.
            # The subject is the person whose name sits immediately BEFORE
            # the connective (local antecedent) — never the first person
            # anywhere in the document.
            known_locs = {n.casefold() for n in
                          (*case_entities.get("location", []),
                           *self.corpus.locations)}
            low_text = text.casefold()
            for spatial in re.finditer(
                    r"\b(?:near|at|in|from)\s+"
                    r"([A-Z][A-Za-z]+(?:\s+[A-Za-z]+)?)", text):
                loc = spatial.group(1)
                if loc.casefold() not in known_locs:
                    continue
                before = low_text[max(0, spatial.start() - 80):spatial.start()]
                after = low_text[spatial.end():spatial.end() + 80]
                person = None
                for window in (before, after):
                    best = None
                    for e in result.entities:
                        if (e.type != "person" or e.source is None
                                or not _same_location(e.source, location)):
                            continue
                        pos = window.rfind(e.name.casefold())
                        if pos >= 0 and (best is None or pos > best[0]):
                            best = (pos, e)
                    if best is not None:
                        person = best[1]
                        break
                if person is not None:
                    result.relationships.append(ExtractedRelationship(
                        source_type="person", source_name=person.name,
                        target_type="location", target_name=loc,
                        relationship_type="LOCATED_AT", confidence=0.75,
                        method="rule:text_location", supporting=src()))

    def _text_items(self, content: DocumentContent):
        if content.kind in ("pdf", "image"):
            for p in content.pages:
                yield {"location": {"page": p["page"]}, "text": p["text"]}
        else:
            for line_no, text in content.lines:
                yield {"location": {"line": line_no}, "text": text}

    def _text_pair(self, result, a, b, rel_type, conf, source: SourceRef):
        def kind_of(value: str) -> str:
            v = value.strip()
            if RE_PHONE.fullmatch(v.replace(" ", "")):
                return "phone"
            if RE_VEHICLE.fullmatch(v):
                return "vehicle"
            if RE_ACCOUNT.fullmatch(v):
                return "account"
            return "person"

        result.relationships.append(ExtractedRelationship(
            source_type=kind_of(a), source_name=a.strip(),
            target_type=kind_of(b), target_name=b.strip(),
            relationship_type=rel_type, confidence=conf,
            method=f"rule:text_{rel_type.lower()}", supporting=source))

    # -- csv ---------------------------------------------------------------
    def _extract_csv(self, content: DocumentContent, case_entities, result):
        if not content.csv_columns:
            result.warnings.append("CSV had no usable header row.")
            return

        # Classify each column once: role = (canonical, special)
        roles: dict[str, tuple[str, str]] = {}
        for col in content.csv_columns:
            key = col.strip().lower()
            if key == "caller":
                roles[col] = ("phone", "caller")
            elif key == "callee":
                roles[col] = ("phone", "callee")
            elif key in ("from_name", "to_name", "caller_name", "callee_name"):
                roles[col] = ("name",
                              "from_name" if key in ("from_name", "caller_name")
                              else "to_name")
            elif key in ("from_account", "to_account"):
                roles[col] = ("account", key)
            else:
                for canonical, aliases in _CSV_ALIASES.items():
                    if key in aliases:
                        roles[col] = (canonical, canonical)
                        break

        for row_no, row in content.csv_rows:
            def src_row(column: str | None = None, value: str | None = None) -> SourceRef:
                return SourceRef(document_id=content.document_id, row=row_no,
                                 column=column, value=value,
                                 snippet=_snippet(str(dict(row)), 200))

            row_entities: dict[str, str] = {}

            for col, (canonical, special) in roles.items():
                value = (row.get(col) or "").strip()
                if not value:
                    continue
                if canonical in ("phone",):
                    row_entities.setdefault("phone", value)
                    result.entities.append(ExtractedEntity(
                        type="phone", name=value, confidence=0.95,
                        method="pattern:phone", source=src_row(col, value)))
                elif canonical == "vehicle":
                    row_entities.setdefault("vehicle", value)
                    result.entities.append(ExtractedEntity(
                        type="vehicle", name=value, confidence=0.95,
                        method="pattern:vehicle", source=src_row(col, value)))
                elif canonical == "case_reference":
                    if RE_CASE_REF.fullmatch(value):
                        row_entities.setdefault("case_reference", value)
                        result.entities.append(ExtractedEntity(
                            type="case", name=value, confidence=0.98,
                            method="pattern:case_reference", source=src_row(col, value)))
                elif canonical == "account":
                    row_entities.setdefault("account", value)
                    result.entities.append(ExtractedEntity(
                        type="account", name=value, confidence=0.80,
                        method="pattern:account", source=src_row(col, value)))
                elif canonical == "person":
                    row_entities.setdefault("person", value)
                    result.entities.append(ExtractedEntity(
                        type="person", name=value, confidence=0.90,
                        method="structured:person_column", source=src_row(col, value)))
                elif canonical == "location":
                    row_entities.setdefault("location", value)
                    result.entities.append(ExtractedEntity(
                        type="location", name=value, confidence=0.80,
                        method="structured:location_column", source=src_row(col, value)))
                elif canonical == "organization":
                    row_entities.setdefault("organization", value)
                    result.entities.append(ExtractedEntity(
                        type="organization", name=value, confidence=0.90,
                        method="structured:organization_column", source=src_row(col, value)))
                elif canonical == "name":
                    etype = _classify_name_value(value)
                    row_entities.setdefault(etype, value)
                    result.entities.append(ExtractedEntity(
                        type=etype, name=value, confidence=0.85,
                        method=f"structured:{special}_column", source=src_row(col, value)))
                elif canonical == "timestamp":
                    pass  # context for events, no standalone candidate
                # unknown columns are deliberately ignored (handled gracefully)

            # --- structured relationship rules (explicit pairs only) -----
            def val_of(special: str) -> str | None:
                for col, (canonical, s) in roles.items():
                    if s == special:
                        v = (row.get(col) or "").strip()
                        if v:
                            return v
                return None

            caller_v, callee_v = val_of("caller"), val_of("callee")
            if caller_v and callee_v and RE_PHONE.fullmatch(caller_v) and RE_PHONE.fullmatch(callee_v):
                result.relationships.append(ExtractedRelationship(
                    source_type="phone", source_name=caller_v,
                    target_type="phone", target_name=callee_v,
                    relationship_type="CALLED", confidence=0.90,
                    method="rule:column_pair_cdr",
                    supporting=src_row(column="caller,callee")))
            from_v, to_v = val_of("from_account"), val_of("to_account")
            if from_v and to_v and RE_ACCOUNT.fullmatch(from_v) and RE_ACCOUNT.fullmatch(to_v):
                result.relationships.append(ExtractedRelationship(
                    source_type="account", source_name=from_v,
                    target_type="account", target_name=to_v,
                    relationship_type="TRANSFERRED_TO", confidence=0.90,
                    method="rule:column_pair_transfer",
                    supporting=src_row(column="from_account,to_account")))
            person = row_entities.get("person")
            if person:
                for other, rel_type, conf, method in (
                    ("phone", "OWNS", 0.90, "rule:column_pair_person_phone"),
                    ("vehicle", "OWNS", 0.90, "rule:column_pair_person_vehicle"),
                    ("location", "LOCATED_AT", 0.80, "rule:column_pair_person_location"),
                    ("case_reference", "INVOLVED_IN", 0.80, "rule:column_pair_person_case"),
                    ("organization", "ASSOCIATED_WITH", 0.70, "rule:column_pair_person_org"),
                    ("account", "OWNS", 0.85, "rule:column_pair_person_account"),
                ):
                    if row_entities.get(other):
                        result.relationships.append(ExtractedRelationship(
                            source_type="person", source_name=person,
                            target_type=other if other != "case_reference" else "case",
                            target_name=row_entities[other],
                            relationship_type=rel_type, confidence=conf,
                            method=method, supporting=src_row()))

    # -- multilingual text (hi / mr / ur) -----------------------------------
    def _multilingual_surface_index(self, lang: str) -> dict[str, tuple[str, str]]:
        """surface form -> (entity_type, canonical name) for this language,
        from the alias registry (SYNTHETIC DEMONSTRATION DATA)."""
        reg = _load_multilingual_aliases()
        index: dict[str, tuple[str, str]] = {}
        for etype, canonicals in reg.by_type.items():
            for canonical, forms in canonicals.items():
                for surface in forms.get(lang, []):
                    if surface and surface not in index:
                        index[surface] = (etype, canonical)
        return index

    @staticmethod
    def _surface_occurrences(surface: str, text: str) -> list[int]:
        """Character offsets where ``surface`` occurs in ``text``.

        Latin surface forms match by substring. Script surface forms match
        either by substring or by *normalized prefix* of a script word —
        this is what lets "पुणे" match the inflected "पुण्यात" (Devanagari
        case suffixes change the character sequence), while "पुणे" still
        does not match an unrelated "पुणेरी..."-style word shorter than
        the normalized surface (minimum 4 normalized chars).
        """
        if surface in text:
            return [m.start() for m in re.finditer(re.escape(surface), text)]
        if any(ord(c) > 0x2FF for c in surface):
            from .language.transliterate import normalize_for_match

            sn = normalize_for_match(surface)
            if len(sn) >= 4:
                return [wm.start() for wm in
                        re.finditer(r"[\u0900-\u097F]{2,}|[\u0621-\u064A\u067E-\u06AF\u0686\u0698\u06BA]{2,}", text)
                        if normalize_for_match(wm.group(0)).startswith(sn)]
        return []

    def _extract_multilingual(self, content: DocumentContent, case_entities,
                              result: ExtractionResult, lang: str) -> None:
        from .language.detect import NAME_STOPWORDS
        from .language.transliterate import normalize_for_match

        surface_index = self._multilingual_surface_index(lang)
        stopwords = NAME_STOPWORDS.get(lang, frozenset())
        name_re = _RE_DEV_NAME if lang in ("hi", "mr") else _RE_AR_NAME
        known_norms = {normalize_for_match(s) for s in surface_index}
        # individual known words (e.g. "कुमार" from "राजेश कुमार") so a
        # 2-word window that overlaps a known name is not re-emitted
        known_words = set()
        for s in surface_index:
            known_words.update(normalize_for_match(w) for w in s.split()
                               if len(normalize_for_match(w)) >= 4)

        for item in self._text_items(content):
            location = item["location"]
            text = item["text"]
            if not text.strip():
                continue
            ref = SourceRef(document_id=content.document_id, snippet=_snippet(text))
            for key in ("page", "line"):
                if location.get(key) is not None:
                    setattr(ref, key, location[key])

            # person/location surface forms present in this line, with their
            # offsets (offsets drive the adjacency rule below).
            person_hits: list[tuple[str, int]] = []     # (canonical, offset)
            location_hits: list[tuple[str, int]] = []   # (canonical, offset)
            for surface, (etype, canonical) in surface_index.items():
                for pos in self._surface_occurrences(surface, text):
                    if etype == "person":
                        person_hits.append((canonical, pos, surface))
                    elif etype == "location":
                        location_hits.append((canonical, pos, surface))
                    result.entities.append(ExtractedEntity(
                        type=etype, name=canonical, aliases=[surface],
                        confidence=0.85,
                        method=f"multilingual:gazetteer:{lang}", source=ref))
            persons = [p for p, _, _ in person_hits]
            locations = [l for l, _, _ in location_hits]

            # unknown-name pattern: a 2-word script sequence that no
            # surface form covers -> person candidate, transliterated name,
            # original surface form preserved as an alias (never merged).
            # In a run of 3+ name-like words only the first surviving
            # 2-word window is kept ("ahmad ali lahore" -> "ahmad ali",
            # not "ali lahore"); overlap is judged among windows that pass
            # the filters, so a stopword bridge cannot poison the chain.
            # Consecutive word runs (a non-overlapping 2-word regex would
            # consume shared words and miss windows like "ahmad ali" inside
            # "per ahmad ali lahore").
            word_runs = [m.group(0) for m in re.finditer(name_re.pattern, text)]
            candidate_windows: list[str] = []
            for w1, w2 in zip(word_runs, word_runs[1:]):
                seq = f"{w1} {w2}"
                if any(st in (w1, w2) for st in stopwords):
                    continue
                if (normalize_for_match(seq) in known_norms
                        or normalize_for_match(w1) in known_norms
                        or normalize_for_match(w2) in known_norms):
                    continue
                # either word overlapping a known name -> not a new name
                if any(any(kw and normalize_for_match(w).startswith(kw)
                           for kw in known_words
                           if len(kw) >= 4) for w in (w1, w2)):
                    continue
                candidate_windows.append(seq)
            for idx, seq in enumerate(candidate_windows):
                if any(candidate_windows[i].split()[1] == seq.split()[0]
                       for i in range(idx)):
                    continue
                latin = _title_latin(normalize_for_match(seq))
                if len(latin.split()) < 2:
                    continue
                result.entities.append(ExtractedEntity(
                    type="person", name=latin, aliases=[seq],
                    confidence=0.55, method=f"multilingual:person_pattern:{lang}",
                    source=ref))

            spatial = any(c in text for c in _MULTILINGUAL_CONNECTIVES[lang])
            stamp = None
            m_ts = RE_TS_ISO.search(text)
            if m_ts:
                stamp = f"{m_ts.group(1)} {m_ts.group(2)}"
            else:
                m_dmy = RE_TS_DMY.search(text)
                if m_dmy:
                    stamp = m_dmy.group(1)

            # Adjacency rule: a location must sit within 30 characters
            # AFTER a person surface form. This keeps claims honest — a
            # person and a location mentioned on the same line are NOT
            # linked unless the text actually puts them next to each other.
            pairs = list(dict.fromkeys(
                (canon_p, canon_l)
                for canon_p, pos_p, surf_p in person_hits
                for canon_l, pos_l, _surf_l in location_hits
                if 0 <= (pos_l - (pos_p + len(surf_p))) <= 30))

            if spatial and stamp:
                for p, loc in pairs:
                    result.claims.append(ExtractedClaim(
                        subject_type="person", subject_name=p,
                        predicate="was_at", object_type="location",
                        object_name=loc, location_name=loc,
                        event_time=stamp, language=lang, confidence=0.70,
                        method=f"multilingual:claim_was_at:{lang}",
                        source=ref))
            if spatial:
                for p, loc in pairs:
                    result.relationships.append(ExtractedRelationship(
                        source_type="person", source_name=p,
                        target_type="location", target_name=loc,
                        relationship_type="LOCATED_AT", confidence=0.70,
                        method=f"multilingual:rule_located_at:{lang}",
                        supporting=ref))
            distinct_persons = list(dict.fromkeys(persons))
            if len(distinct_persons) >= 2 and any(
                    v in text for v in _MULTILINGUAL_CALLED[lang]):
                a, b = distinct_persons[0], distinct_persons[1]
                if _norm_name(a) != _norm_name(b):
                    result.relationships.append(ExtractedRelationship(
                        source_type="person", source_name=a,
                        target_type="person", target_name=b,
                        relationship_type="CALLED", confidence=0.70,
                        method=f"multilingual:rule_called:{lang}",
                        supporting=ref))

    # -- english structured was_at claims (stage 5, additive) --------------
    # Sentence-structure patterns for latin was_at claims. The person and
    # the location must be *syntactically* linked by an observation/presence
    # verb + preposition — co-occurrence on a line is not enough. This keeps
    # "A reported that B was seen at X" from claiming A at X.
    # Scoped (?i:...) keeps the verb/preposition case-insensitive while the
    # name and location stay capitalized (a global re.I would let the greedy
    # name pattern swallow lowercase words like "was").
    EN_WAS_AT_SEEN_RE = re.compile(
        r"\b(" + _EN_CLAIM_NAME_1_4 + r")\s+"
        r"(?:(?i:was|were)\s+)?"
        r"(?i:seen|observed|sighted|found|spotted|arrived|located)\s+"
        r"(?i:at|in|near|by)\s+"
        r"([A-Z][A-Za-z]+(?:\s+[A-Za-z]+){0,2})\b")
    EN_WAS_AT_PLAIN_RE = re.compile(
        r"\b(" + _EN_CLAIM_NAME_1_4 + r")\s+"
        r"(?:(?i:was|were))\s+"
        r"(?i:at|in|near)\s+"
        r"([A-Z][A-Za-z]+(?:\s+[A-Za-z]+){0,2})\b")

    def _extract_claims_en(self, content: DocumentContent, case_entities,
                           result: ExtractionResult) -> None:
        """was_at claims for latin documents.

        A claim requires the sentence structure

            <person> [was|were] (seen|observed|sighted|found|spotted|
                                 arrived|located) at|in|near|by <location>
            <person> was|were at|in|near <location>

        where the person and location are known names (case-confirmed,
        the multilingual alias registry, or the corpus gazetteer) and the
        line carries an ISO timestamp. English patterns only — Devanagari
        and Urdu lines use _extract_multilingual.
        """
        reg = _load_multilingual_aliases()
        persons = [n for n in case_entities.get("person", [])
                   if re.search(r"[A-Za-z]", n)]
        locations = [n for n in case_entities.get("location", [])
                     if re.search(r"[A-Za-z]", n)]
        persons += [c for c in reg.by_type.get("person", {}) if c not in persons]
        locations += [c for c in reg.by_type.get("location", {}) if c not in locations]
        persons += [n for n in self.corpus.persons if n not in persons]
        locations += [n for n in self.corpus.locations if n not in locations]
        person_by_norm = {_norm_name(p): p for p in persons
                          if re.search(r"[A-Za-z]", p)}
        known_locations = [l for l in locations
                           if re.search(r"[A-Za-z]", l)]

        def _match_location(obj_raw: str) -> str | None:
            """The known location a captured location phrase refers to
            (exact word, or the phrase starting with it: 'Pune station'
            -> 'Pune')."""
            norm = _norm_name(obj_raw)
            for loc in known_locations:
                ln = _norm_name(loc)
                if norm == ln or (norm.startswith(ln)
                                  and len(norm) > len(ln)
                                  and (norm[len(ln)].isspace()
                                       or norm[len(ln)] == ".")):
                    return loc
            return None

        for item in self._text_items(content):
            location = item["location"]
            text = item["text"]
            if not text.strip():
                continue
            m_ts = RE_TS_ISO.search(text)
            if not m_ts:
                continue
            stamp = f"{m_ts.group(1)} {m_ts.group(2)}"
            pairs: list[tuple[str, str]] = []
            for rx in (self.EN_WAS_AT_SEEN_RE, self.EN_WAS_AT_PLAIN_RE):
                for m in rx.finditer(text):
                    subj = person_by_norm.get(_norm_name(m.group(1)))
                    if subj is None:
                        continue
                    loc = _match_location(m.group(2))
                    if loc is None:
                        continue
                    pairs.append((subj, loc))
            if not pairs:
                continue
            ref = SourceRef(document_id=content.document_id, snippet=_snippet(text))
            for key in ("page", "line"):
                if location.get(key) is not None:
                    setattr(ref, key, location[key])
            for p, loc in dict.fromkeys(pairs):
                result.claims.append(ExtractedClaim(
                    subject_type="person", subject_name=p,
                    predicate="was_at", object_type="location",
                    object_name=loc, location_name=loc,
                    event_time=stamp, language="en", confidence=0.70,
                    method="multilingual:claim_was_at:en", source=ref))

    # -- dedupe within one document ----------------------------------------
    def _dedupe_in_document(self, result: ExtractionResult) -> None:
        seen: set[tuple[str, str, str]] = set()
        kept = []
        for e in result.entities:
            loc = _location_key(e.source)
            key = (e.type, _norm_name(e.name), loc)
            if key in seen:
                existing = next(x for x in kept if (x.type, _norm_name(x.name), _location_key(x.source)) == key)
                for a in e.aliases:
                    if a not in existing.aliases:
                        existing.aliases.append(a)
                continue
            seen.add(key)
            kept.append(e)
        result.entities = kept

        seen_r: set[tuple] = set()
        kept_r = []
        for r in result.relationships:
            key = (r.source_type, _norm_name(r.source_name), r.relationship_type,
                   _norm_name(r.target_name), r.target_type, _location_key(r.supporting))
            if key in seen_r:
                continue
            seen_r.add(key)
            kept_r.append(r)
        result.relationships = kept_r

        seen_c: set[tuple] = set()
        kept_c = []
        for c in result.claims:
            key = (c.subject_type, _norm_name(c.subject_name), c.predicate,
                   _norm_name(c.object_name or c.object_value or ""),
                   c.event_time, _location_key(c.source))
            if key in seen_c:
                continue
            seen_c.add(key)
            kept_c.append(c)
        result.claims = kept_c


def _location_key(source: SourceRef) -> str:
    if source.page is not None:
        return f"p{source.page}"
    if source.row is not None:
        return f"r{source.row}"
    if source.line is not None:
        return f"l{source.line}"
    return "-"


def _same_location(a: SourceRef, b: dict) -> bool:
    if b.get("page") is not None:
        return a.page == b["page"]
    if b.get("line") is not None:
        return a.line == b["line"]
    return False


# ------------------------------------------------------------- LLM provider

class LLMExtractionProvider(ExtractionProvider):
    """OpenAI-compatible chat endpoint, JSON-only contract.

    The model is told the exact JSON schema and is validated with Pydantic;
    any deviation raises ExtractionError (document FAILED). The provider
    holds no database session and no write path.
    """

    name = "llm"

    _SYSTEM = (
        "You are a document extraction engine for a criminal-network "
        "investigation platform. Extract entities and relationships from the "
        "provided document. Respond with JSON only, matching exactly: "
        '{"entities": [{"type": "person|phone|vehicle|location|account|organization|case|event", '
        '"name": str, "aliases": [str], "confidence": 0.0-1.0, "method": "llm", '
        '"source": {"document_id": int, "page": int|null, "line": int|null, "snippet": str}}], '
        '"relationships": [{"source_type": str, "source_name": str, "target_type": str, '
        '"target_name": str, "relationship_type": "CALLED|OWNS|USED|LOCATED_AT|ASSOCIATED_WITH|'
        'INVOLVED_IN|TRANSFERRED_TO|MENTIONED_IN|CONNECTED_TO|OCCURRED_AT", "confidence": 0.0-1.0, '
        '"method": "llm", "supporting": {"document_id": int, "page": int|null, "line": int|null, '
        '"snippet": str}}], "warnings": [str]}. '
        "Only extract what the document states; never infer unsupported "
        "relationships; never fabricate page or line numbers."
    )

    def __init__(self):
        settings = get_settings()
        if not settings.llm_api_key:
            raise ExtractionError(
                "LLM provider configured but LLM_API_KEY is missing.")
        self.base_url = (settings.llm_base_url or "https://api.openai.com/v1").rstrip("/")
        self.model = settings.llm_model or "gpt-4o-mini"
        self.api_key = settings.llm_api_key

    def extract(self, content: DocumentContent,
                case_entities: dict[str, list[str]] | None = None) -> ExtractionResult:
        import json

        import httpx

        body_text = content.raw_text[:60_000]
        try:
            resp = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": self._SYSTEM},
                        {"role": "user", "content": f"Document id: {content.document_id}\n"
                                                     f"Kind: {content.kind}\n\n{body_text}"},
                    ],
                },
                timeout=120,
            )
            resp.raise_for_status()
            payload = json.loads(resp.json()["choices"][0]["message"]["content"])
            result = ExtractionResult.model_validate(payload)
        except ExtractionError:
            raise
        except Exception as exc:  # noqa: BLE001 — any failure = FAILED, honestly
            raise ExtractionError(f"LLM extraction failed: {exc.__class__.__name__}: {exc}") from exc

        # Stamp the real document id and force the method label.
        for e in result.entities:
            e.source.document_id = content.document_id
            e.method = "llm"
        for r in result.relationships:
            r.supporting.document_id = content.document_id
            r.method = "llm"
        self._dedupe_like_rule_based(result)
        return result

    @staticmethod
    def _dedupe_like_rule_based(result: ExtractionResult) -> None:
        provider = RuleBasedExtractionProvider.__new__(RuleBasedExtractionProvider)
        provider._dedupe_in_document(result)


# ------------------------------------------------------------------ factory

@lru_cache(maxsize=1)
def get_extraction_provider() -> ExtractionProvider:
    """Rule-based by default; LLM only when explicitly configured."""
    settings = get_settings()
    provider = (settings.llm_provider or "").lower().strip()
    if provider in ("", "rules", "rule", "none", "deterministic"):
        return RuleBasedExtractionProvider()
    try:
        return LLMExtractionProvider()
    except ExtractionError as exc:
        # A misconfigured LLM must not silently fall back to rules: the
        # operator asked for the LLM. Log and surface on next use.
        logger.warning("LLM provider unavailable, falling back to rules: %s", exc)
        return RuleBasedExtractionProvider()
