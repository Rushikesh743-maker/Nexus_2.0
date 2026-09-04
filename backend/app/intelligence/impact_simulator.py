"""
Evidence impact simulator.

Answers one question: *what would this case look like if this record had never
been filed?*

The honest way to answer it is to actually run the pipeline without the record
— ingestion, extraction, identity resolution, graph construction, analytics,
anomaly detection and the contradiction engine — and diff the result against
the case as recorded. That is what this module does. A full re-run costs about
a quarter of a second on the Operation Meridian corpus, which is cheap enough
that there is no reason to approximate.

Approximating would also be wrong in an interesting way. Withdrawing a record
can change *identity resolution*: two people merged on a phone number quoted
only in that record come apart again. An adjustment applied to the finished
graph cannot show that; a re-run does, and it is often the most important thing
the simulation has to say.

Nothing here mutates the baseline. The counterfactual is a separate graph built
from the same files on disk, and the case as recorded is never modified — the
simulation is a thought experiment, and the UI says so.

Aligning the two runs
---------------------
Person ids are positional (`P0001`, `P0002`, ...), assigned over sorted
clusters, so withholding one record renumbers everyone after it. Diffing on ids
would report the entire network as changed. Persons are therefore matched
between the two runs by what identifies them — phone numbers, account numbers
and name forms — rather than by id. Every other node type already has a
deterministic id derived from its label and needs no alignment.

That alignment is also what surfaces an un-merge: one baseline subject matching
two counterfactual subjects means the withheld record was the only thing
holding an identity together.
"""

from __future__ import annotations

from collections import defaultdict

from ..graph.analytics import NetworkAnalytics
from ..graph.anomaly import AnomalyDetector
from ..graph.build import build_graph
from .contradiction_engine import ContradictionEngine


# ------------------------------------------------------------- alignment

def _signature(attrs: dict) -> set[str]:
    """What identifies a subject, independent of the id they were given."""
    sig = set()
    for ph in attrs.get("phones") or []:
        sig.add(f"ph:{ph}")
    for ac in attrs.get("accounts") or []:
        sig.add(f"ac:{ac}")
    for name in [attrs.get("label")] + list(attrs.get("aliases") or []):
        if name:
            sig.add(f"nm:{str(name).strip().lower()}")
    return sig


def _align_persons(base, cf) -> tuple[dict, dict, list[dict]]:
    """
    Match baseline persons to counterfactual persons by identifier overlap.

    Returns `(base_key, cf_key, splits)` — two node-id-to-stable-key maps and
    the baseline subjects that came apart into several counterfactual subjects.
    """
    base_p = {n: _signature(d) for n, d in base.G.nodes(data=True) if d.get("type") == "PERSON"}
    cf_p = {n: _signature(d) for n, d in cf.G.nodes(data=True) if d.get("type") == "PERSON"}

    # Greedy, highest-overlap-first, and sorted so the result never depends on
    # dict ordering: two runs over the same corpus must align identically.
    pairs = []
    for b, bs in base_p.items():
        for c, cs in cf_p.items():
            overlap = len(bs & cs)
            if overlap:
                pairs.append((-overlap, b, c))
    pairs.sort()

    base_key, cf_key = {}, {}
    taken_b, taken_c = set(), set()
    matched_to: dict[str, list[str]] = defaultdict(list)
    for _, b, c in pairs:
        if b in taken_b or c in taken_c:
            continue
        key = f"P:{b}"
        base_key[b], cf_key[c] = key, key
        taken_b.add(b)
        taken_c.add(c)

    # A counterfactual subject with no first-choice match may still overlap a
    # baseline subject that is already taken — that is an un-merge, and both
    # halves matter, so record it rather than dropping it.
    for c, cs in cf_p.items():
        if c in taken_c:
            continue
        best, best_overlap = None, 0
        for b, bs in base_p.items():
            o = len(bs & cs)
            if o > best_overlap:
                best, best_overlap = b, o
        if best is not None:
            matched_to[best].append(c)
            cf_key[c] = f"P:{best}#split{len(matched_to[best])}"
        else:
            cf_key[c] = f"NEW:{c}"

    for b in base_p:
        base_key.setdefault(b, f"P:{b}")

    splits = [
        {
            "subject": base.G.nodes[b].get("label"),
            "baseline_id": b,
            "became": [cf.G.nodes[c].get("label") for c in cs],
            "detail": (
                f"{base.G.nodes[b].get('label')} was assembled from records that the "
                "withheld evidence tied together. Without it, identity resolution no "
                f"longer joins them and the subject separates into "
                f"{len(cs) + 1} identities."
            ),
        }
        for b, cs in sorted(matched_to.items())
    ]
    return base_key, cf_key, splits


def _key_map(graph, person_keys: dict) -> dict:
    """Stable key for every node: aligned for persons, the id itself otherwise."""
    out = {}
    for n, d in graph.G.nodes(data=True):
        out[n] = person_keys.get(n, n) if d.get("type") == "PERSON" else n
    return out


def _edges_by_key(graph, keys: dict) -> dict:
    out = {}
    for a, b, d in graph.G.edges(data=True):
        ka, kb = keys.get(a, a), keys.get(b, b)
        out[tuple(sorted((ka, kb)))] = {
            "a_label": graph.G.nodes[a].get("label"),
            "b_label": graph.G.nodes[b].get("label"),
            "types": list(d.get("types", [])),
            "confidence": d.get("confidence"),
            "observations": d.get("observations"),
            "weight": round(float(d.get("weight", 0)), 3),
            "independent_sources": sorted({s.get("source_type") for s in d.get("sources", [])}),
        }
    return out


def _finding_key(f: dict) -> tuple:
    """Findings are re-numbered on every run, so identity is type plus title."""
    return (f.get("type"), f.get("title"))


# -------------------------------------------------------------- simulator

class ImpactSimulator:
    """
    Withhold evidence, re-run the case, and report what changed.

    `baseline` is the case as recorded and is only ever read.
    """

    def __init__(self, baseline, baseline_contradictions=None,
                 baseline_findings=None, baseline_analytics=None):
        self.baseline = baseline
        self._contradictions = baseline_contradictions
        self._findings = baseline_findings
        self._analytics = baseline_analytics

    # ---------------------------------------------------------- baselines
    def _base_analytics(self):
        if self._analytics is None:
            self._analytics = NetworkAnalytics(self.baseline)
        return self._analytics

    def _base_contradictions(self):
        if self._contradictions is None:
            self._contradictions = ContradictionEngine(self.baseline).run_all()
        return self._contradictions

    def _base_findings(self):
        if self._findings is None:
            self._findings = AnomalyDetector(self.baseline, self._base_analytics()).run_all()
        return self._findings

    # ------------------------------------------------------------ helpers
    def describe_withheld(self, sources, records) -> list[dict]:
        docs = self.baseline.raw.get("documents", {})
        out = []
        for sid in sorted(sources):
            doc = docs.get(sid) or {}
            rec = doc.get("record") or {}
            title = (rec.get("narrative") or rec.get("observation") or rec.get("text")
                     or rec.get("name") or "")
            out.append({
                "source_id": sid,
                "source_type": doc.get("source_type"),
                "known": sid in docs,
                "summary": (str(title)[:160] + "…") if len(str(title)) > 160 else str(title),
            })
        for rid in sorted(records):
            out.append({"source_id": rid, "source_type": "record", "known": True,
                        "summary": "Individual row withheld from its feed."})
        return out

    # --------------------------------------------------------------- main
    def simulate(self, exclude_sources=(), exclude_records=()) -> dict:
        sources = {s for s in (exclude_sources or ()) if s}
        records = {r for r in (exclude_records or ()) if r}
        if not sources and not records:
            raise ValueError("Nothing was withheld: pass a source id or a record id.")

        base = self.baseline
        cf = build_graph(sources, records)

        base_contra = self._base_contradictions()
        base_find = self._base_findings()
        base_an = self._base_analytics()

        cf_an = NetworkAnalytics(cf)
        cf_contra = ContradictionEngine(cf).run_all()
        cf_find = AnomalyDetector(cf, cf_an).run_all()

        base_pk, cf_pk, splits = _align_persons(base, cf)
        base_keys, cf_keys = _key_map(base, base_pk), _key_map(cf, cf_pk)
        base_edges, cf_edges = _edges_by_key(base, base_keys), _edges_by_key(cf, cf_keys)

        removed_links, weakened_links = [], []
        for key, e in sorted(base_edges.items()):
            after = cf_edges.get(key)
            if after is None:
                removed_links.append({**e, "impact": "link disappears entirely"})
            else:
                d_conf = round((after["confidence"] or 0) - (e["confidence"] or 0), 4)
                d_obs = (after["observations"] or 0) - (e["observations"] or 0)
                lost = sorted(set(e["independent_sources"]) - set(after["independent_sources"]))
                if d_conf or d_obs or lost:
                    weakened_links.append({
                        **e,
                        "confidence_after": after["confidence"],
                        "confidence_delta": d_conf,
                        "observations_after": after["observations"],
                        "observations_delta": d_obs,
                        "independent_sources_after": after["independent_sources"],
                        "independent_sources_lost": lost,
                    })
        introduced_links = [
            {**e, "impact": "link appears only once the record is withheld"}
            for key, e in sorted(cf_edges.items()) if key not in base_edges
        ]

        # Subjects left with nothing linking them to the rest of the case. Only
        # those that *had* a link before are interesting: a subject who was
        # already isolated has not been affected by anything.
        base_key_to_id = {k: b for b, k in base_pk.items()}
        isolated = []
        for n, d in sorted(cf.G.nodes(data=True)):
            if d.get("type") != "PERSON" or cf.G.degree(n) != 0:
                continue
            before_id = base_key_to_id.get(cf_pk.get(n))
            if before_id is None or base.G.degree(before_id) == 0:
                continue
            isolated.append({
                "subject": d.get("label"),
                "links_before": base.G.degree(before_id),
                "detail": ("Every link to this subject came from the withheld "
                           "evidence; nothing else in the case connects them."),
            })

        # Contradictions and findings are keyed on content: both are renumbered
        # on every run, so ids cannot be compared across the two.
        base_ck = {(c["type"], c["title"]): c for c in base_contra}
        cf_ck = {(c["type"], c["title"]): c for c in cf_contra}
        resolved = [base_ck[k] for k in sorted(base_ck.keys() - cf_ck.keys())]
        introduced_c = [cf_ck[k] for k in sorted(cf_ck.keys() - base_ck.keys())]

        base_fk = {_finding_key(f): f for f in base_find}
        cf_fk = {_finding_key(f): f for f in cf_find}
        find_resolved = [base_fk[k] for k in sorted(base_fk.keys() - cf_fk.keys())]
        find_introduced = [cf_fk[k] for k in sorted(cf_fk.keys() - base_fk.keys())]

        # Influence movement, reported on subjects that actually moved.
        base_rank = {base_keys[r["id"]]: r for r in base_an.influence() if r["id"] in base_keys}
        cf_rank = {cf_keys[r["id"]]: r for r in cf_an.influence() if r["id"] in cf_keys}
        influence_changes = []
        for key, before in sorted(base_rank.items(), key=lambda kv: kv[1]["rank"]):
            after = cf_rank.get(key)
            if after is None:
                influence_changes.append({
                    "subject": before.get("label"), "rank_before": before["rank"],
                    "rank_after": None, "score_before": before["score"], "score_after": None,
                    "detail": "No longer ranked once the record is withheld.",
                })
            elif after["rank"] != before["rank"]:
                influence_changes.append({
                    "subject": before.get("label"),
                    "rank_before": before["rank"], "rank_after": after["rank"],
                    "score_before": before["score"], "score_after": after["score"],
                    "rank_delta": after["rank"] - before["rank"],
                })
        influence_changes = influence_changes[:15]

        return {
            "withheld": self.describe_withheld(sources, records),
            "exclude_sources": sorted(sources),
            "exclude_records": sorted(records),
            "summary": {
                "subjects_before": base.G.number_of_nodes(),
                "subjects_after": cf.G.number_of_nodes(),
                "links_before": base.G.number_of_edges(),
                "links_after": cf.G.number_of_edges(),
                "contradictions_before": len(base_contra),
                "contradictions_after": len(cf_contra),
                "findings_before": len(base_find),
                "findings_after": len(cf_find),
                "entities_resolved_before": len(base.raw["entities"]),
                "entities_resolved_after": len(cf.raw["entities"]),
                "links_removed": len(removed_links),
                "links_weakened": len(weakened_links),
            },
            "removed_links": removed_links,
            "weakened_links": weakened_links,
            "introduced_links": introduced_links,
            "isolated_subjects": isolated,
            "identity_splits": splits,
            "contradictions_resolved": resolved,
            "contradictions_introduced": introduced_c,
            "findings_resolved": find_resolved,
            "findings_introduced": find_introduced,
            "influence_changes": influence_changes,
            "method": (
                "The pipeline was re-run from the source files with this evidence "
                "withheld — ingestion, extraction, identity resolution, graph "
                "construction, analytics, pattern detection and contradiction "
                "detection all recomputed. Nothing in the case as recorded was "
                "modified."
            ),
            "disclaimer": (
                "A simulation, not a finding. It shows how much of the current "
                "picture rests on one record; it does not suggest that record is "
                "wrong, and it does not change the case."
            ),
        }


def simulate_removal(baseline, exclude_sources=(), exclude_records=(), **kw) -> dict:
    return ImpactSimulator(baseline, **kw).simulate(exclude_sources, exclude_records)
