"""
Contradiction engine configuration.

Every threshold the engine applies lives here, not scattered through the
detectors. Two reasons that matters in this domain:

* An investigator who disagrees with a finding must be able to see the number
  that produced it and change it. A rule buried in a comparison three files
  deep is not reviewable.
* These are *prototype* weights. They are not a legal reliability ranking and
  carry no evidentiary standing. A deployment replaces them with values its
  own jurisdiction and data quality justify.
"""

from __future__ import annotations

import os

# --------------------------------------------------------------- movement

# Above this implied point-to-point speed, two sightings cannot both be true
# under ordinary ground travel. Deliberately generous: Mumbai suburban rail
# peaks around 80 km/h and an expressway car run can exceed it, so the value is
# set where road/rail explanations run out rather than where traffic is heavy.
MAX_REASONABLE_SPEED_KMPH = float(os.environ.get("NEXUS_MAX_SPEED_KMPH", 120.0))

# A second, softer band. Between these two values movement is unusual but not
# impossible, so the engine reports a *possible* inconsistency at low severity
# instead of asserting a conflict.
UNUSUAL_SPEED_KMPH = float(os.environ.get("NEXUS_UNUSUAL_SPEED_KMPH", 80.0))

# Cell sites and reported locations are points standing in for areas. Two
# observations closer than this are treated as the same place — a handset
# switching between adjacent towers is not a journey.
MIN_SEPARATION_KM = 1.5

# Below this gap, clock skew between two independent systems is a likelier
# explanation than movement, so the pair is not evaluated for speed.
MIN_INTERVAL_MINUTES = 2.0

# --------------------------------------------------------- time precision
#
# How exactly a source pins an observation in time. A contradiction that turns
# on minutes cannot be raised from a record that only fixes a calendar day —
# this is the single most important false-positive control in the engine, since
# most FIR and surveillance records in the corpus carry the document's filing
# time rather than the time of the event described.

PRECISION_EXACT = "exact"        # a timestamped machine record (CDR call start)
PRECISION_STATED = "stated"      # a time of day written in the narrative
PRECISION_DOCUMENT = "document"  # only the document's own date is known

# Precisions that may support a timing-based contradiction.
TIME_PRECISE = {PRECISION_EXACT, PRECISION_STATED}

# A time read out of free text carries the reporting officer's rounding — "at
# 0820 hrs" is usually a watch reading, but it may have been rounded to the
# nearest five or ten minutes. The engine widens every stated-time interval by
# this much *in the subject's favour* before judging it, so a conflict has to
# survive the rounding to be reported.
STATED_TIME_TOLERANCE_MINUTES = 15.0

# ----------------------------------------------------- source reliability
#
# Prototype weights only — see the module docstring. Higher means the record is
# treated as a firmer statement of fact when support and contradiction are
# weighed against each other.

SOURCE_RELIABILITY = {
    "structured_record": 1.00,   # machine-generated: CDR, bank transaction
    "cdr": 1.00,
    "transaction": 1.00,
    "verified_report": 0.90,     # an officer's own observation
    "surveillance": 0.90,
    "criminal_record": 0.90,
    "document": 0.80,            # a filed record parsed as text
    "fir": 0.80,
    "ocr": 0.70,                 # a scanned document recovered by OCR
    "fir_scan": 0.70,
    "social_media": 0.55,        # open source, unverified
    "inferred": 0.50,            # produced by the system, not observed
}

DEFAULT_RELIABILITY = 0.60


def reliability(source_type: str) -> float:
    """Prototype reliability weight for a source system."""
    return SOURCE_RELIABILITY.get(source_type, DEFAULT_RELIABILITY)


# ------------------------------------------------------------ scoring

# The most a contradiction may reduce a relationship's confidence. Conflicting
# evidence weakens a conclusion; it does not delete the evidence that supports
# it, so confidence is never driven to zero by this engine.
CONFIDENCE_IMPACT_CAP = 0.45

# Repeated records from one source system are correlated — twenty calls on the
# same CDR are not twenty independent confirmations. The k-th record of a given
# source type is therefore discounted by 1/sqrt(k).
DIMINISHING_RETURNS = True

# Contradiction ratio bands for severity.
SEVERITY_HIGH_RATIO = 0.50
SEVERITY_MEDIUM_RATIO = 0.25

# ------------------------------------------------- association conflicts

# Two people recorded with the same vehicle this far apart are an ordinary
# change of driver, not a conflict. Only overlapping claims are examined.
VEHICLE_WINDOW_HOURS = 12.0

# Relationship types that legitimately explain one vehicle or handset moving
# between two people; when one is present the engine does not raise a conflict.
TRANSFER_RELATIONSHIPS = {"SUPPLIED_BY", "INSTRUCTED_BY", "REPORTS_TO", "SHARES_HANDSET"}

# Entity attributes compared for identity-resolution conflicts, and how they
# are compared. Attributes not listed here are ignored.
IDENTITY_ATTRIBUTES = {
    "police_district": "exact",
    "date_of_birth": "exact",
    "address": "exact",
    "active_period": "overlap",
}
