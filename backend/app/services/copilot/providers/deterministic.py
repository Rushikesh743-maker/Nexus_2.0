"""Deterministic copilot provider — always available, offline, honest.

Every answer is computed from the ``CaseContext`` (confirmed records only)
with fixed, documented formulas. The provider:

* never references a record that is not in the context (no hallucination);
* cites every record it mentions (``Citation`` with a minimal snapshot);
* computes ``confidence`` per intent from retrieved data — never invented;
* uses neutral, investigative language ("potential", "analytical support",
  "insufficient data") and never asserts guilt or truth of a record;
* returns a structured ``data`` payload the UI renders alongside the prose.

The prose itself is generated from the structured payload with templates —
no language model is involved, and the answer says so (``provider =
"deterministic"``).
"""

from __future__ import annotations

import datetime as _dt

import networkx as nx

from ...investigation_intelligence.evidence_impact import simulate_removal
from .base import Citation, CopilotAnswer, CopilotProvider

_EPS = 1e-9


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, round(x, 3)))


def _fmt_ts(ts) -> str | None:
    if ts is None:
        return None
    if isinstance(ts, str):
        return ts
    if isinstance(ts, _dt.datetime):
        return ts.strftime("%Y-%m-%d %H:%M")
    return str(ts)


class DeterministicProvider(CopilotProvider):
    id = "deterministic"
    name = "Deterministic engine (offline, no LLM)"

    # ------------------------------------------------------------- dispatch
    def answer(self, ctx, intent) -> CopilotAnswer:
        handler = getattr(self, f"_i_{intent.intent}", self._i_unsupported)
        ans = handler(ctx, intent)
        # stage-5 multilingual QA: re-render the PROSE in the question's
        # language. Facts, citations and confidence are the same — only
        # answer_text is replaced (see localize.py for the contract).
        from ..localize import LOCALIZED_LANGUAGES, render_answer
        q_lang = intent.params.get("question_language")
        if q_lang in LOCALIZED_LANGUAGES and (
                intent.intent == "unsupported" or ans.data):
            localized = render_answer(intent.intent, ans.data, q_lang, ctx)
            ans.data["question_language"] = q_lang
            if localized is not None:
                ans.answer_text = localized
                ans.data["answer_language"] = q_lang
            else:
                # honest fallback: no template for this intent yet
                ans.data["answer_language"] = "en"
                ans.data["localization_note"] = (
                    "This intent has no localized template; the answer is "
                    "served in English. Facts, citations and confidence "
                    "are identical either way.")
        else:
            ans.data["answer_language"] = q_lang or "en"
        return ans

    # ------------------------------------------------------------- helpers
    def _c_entity(self, ctx, eid: int) -> Citation | None:
        ent = ctx.data.entities_by_id.get(eid)
        if ent is None:
            return None
        return Citation("entity", eid, ent.canonical_name,
                        {"entity_type": ent.entity_type,
                         "canonical_name": ent.canonical_name})

    def _c_relationship(self, ctx, rid: int) -> Citation | None:
        rel = next((r for r in ctx.data.relationships if r.id == rid), None)
        if rel is None:
            return None
        return Citation("relationship", rid, rel.relationship_type,
                        {"relationship_type": rel.relationship_type,
                         "source": ctx.name_of(rel.source_entity_id),
                         "target": ctx.name_of(rel.target_entity_id)})

    def _c_evidence(self, ctx, eid: int) -> Citation | None:
        ev = next((v for v in ctx.data.evidence if v.id == eid), None)
        if ev is None:
            return None
        return Citation("evidence", eid, f"E{eid} ({ev.evidence_type})",
                        {"evidence_type": ev.evidence_type,
                         "source_reference": ev.source_reference,
                         "document_id": ev.document_id})

    def _c_finding(self, f) -> Citation:
        return Citation("finding", f.id, f.title,
                        {"finding_type": f.finding_type,
                         "status": f.status,
                         "graph_version": f.graph_version})

    def _c_hypothesis(self, h) -> Citation:
        return Citation("hypothesis", h.id, h.title,
                        {"hypothesis_type": h.hypothesis_type,
                         "analytical_score": h.analytical_score,
                         "confidence_band": h.confidence_band})

    def _c_event(self, ctx, e) -> Citation:
        return Citation("event", e.id,
                        f"{e.event_type} @ {ctx.name_of(e.entity_id)}",
                        {"event_type": e.event_type,
                         "timestamp": _fmt_ts(e.timestamp),
                         "entity": ctx.name_of(e.entity_id),
                         "location": ctx.location_name(e.location_id)})

    def _c_location(self, ctx, lid: int) -> Citation | None:
        loc = next((l for l in ctx.data.locations if l.id == lid), None)
        if loc is None:
            return None
        return Citation("location", lid, loc.name,
                        {"latitude": loc.latitude, "longitude": loc.longitude})

    def _c_claim(self, ctx, c) -> Citation:
        return Citation("claim", c.id,
                        f"{ctx.name_of(c.subject_entity_id)} {c.predicate}",
                        {"predicate": c.predicate,
                         "object_value": c.object_value,
                         "event_time": _fmt_ts(c.event_time)})

    def _dedupe(self, cits) -> list[Citation]:
        seen, out = set(), []
        for c in cits:
            if c is None or (c.kind, c.id) in seen:
                continue
            seen.add((c.kind, c.id))
            out.append(c)
        return out

    def _findings_of(self, ctx, ftype: str) -> list:
        return [f for f in ctx.findings if f.finding_type == ftype]

    def _suggestions(self, ctx, base: list[str]) -> list[str]:
        top = base[:4]
        if len(ctx.data.entities) >= 2:
            a, b = ctx.data.entities[0].canonical_name, ctx.data.entities[1].canonical_name
            if f"How is {a} connected to {b}?" not in top:
                top.append(f"How is {a} connected to {b}?")
        if ctx.counts["entities"]:
            top.append(f"Who is connected to {ctx.data.entities[0].canonical_name}?")
        return top[:5]

    # ============================================================= intents
    def _i_case_overview(self, ctx, intent) -> CopilotAnswer:
        c = ctx.counts
        if c["entities"] == 0 and c["evidence"] == 0:
            return CopilotAnswer(
                intent.intent, intent.interpretation, status="not_enough_data",
                answer_text="This case has no confirmed records yet. Upload "
                            "documents and accept extraction candidates to "
                            "build the confirmed knowledge base.",
                confidence=1.0,
                confidence_basis="Empty confirmed data set (nothing to summarize).",
                suggestions=self._suggestions(ctx, ["What contradictions are there?"]))

        total = (c["entities"] + c["relationships"] + c["evidence"]
                 + c["timeline_events"])
        confidence = _clamp01(0.3 + 0.7 * min(1.0, total / 20))
        high_findings = [f for f in ctx.findings
                         if (f.details or {}).get("severity") == "HIGH"
                         or f.finding_type == "CONTRADICTION"][:3]
        citations = [self._c_finding(f) for f in high_findings]
        text = (f"Case {ctx.case.case_number} — {ctx.case.title} "
                f"(status: {ctx.case.status}, priority: {ctx.case.priority}).\n\n"
                f"Confirmed records: {c['entities']} entities, "
                f"{c['relationships']} relationships, {c['evidence']} evidence "
                f"items, {c['timeline_events']} timeline events, "
                f"{c['locations']} locations, {c['claims']} structured claims.\n\n"
                f"Analysis: {c['findings']} findings and {c['hypotheses']} "
                "hypotheses on record. ")
        if high_findings:
            text += ("Highlights: " + "; ".join(f.title for f in high_findings) + ". ")
        else:
            text += "No high-severity findings are currently flagged. "
        text += ("These are analytical results over confirmed records — "
                 "they are starting points for review, not conclusions.")
        return CopilotAnswer(
            intent.intent, intent.interpretation,
            answer_text=text, confidence=confidence,
            confidence_basis=("Computed from confirmed-record volume: "
                              "0.3 + 0.7·min(1, total/20), total = entities + "
                              f"relationships + evidence + events = {total}."),
            citations=self._dedupe(citations),
            data={"counts": c,
                  "high_findings": [{"id": f.id, "title": f.title,
                                     "finding_type": f.finding_type}
                                    for f in high_findings],
                  "case": {"number": ctx.case.case_number,
                           "title": ctx.case.title,
                           "status": ctx.case.status}},
            suggestions=self._suggestions(ctx,
                                          ["What contradictions are there?",
                                           "What are the competing hypotheses?"]))

    def _i_entity_profile(self, ctx, intent) -> CopilotAnswer:
        name = intent.params.get("node")
        eid, canon = ctx.resolve_all(name) if name else (None, None)
        if eid is None:
            return CopilotAnswer(
                intent.intent, intent.interpretation, status="unsupported",
                answer_text=f"“{name}” is not a confirmed entity in this "
                            "case. The copilot only reports confirmed "
                            "records.",
                confidence=0.0, confidence_basis="Name not resolved.",
                suggestions=self._suggestions(ctx, []))
        ent = ctx.data.entities_by_id[eid]
        aliases = (ctx.data.entity_metadata.get(eid, {}).get("aliases")) or []
        rels = [r for r in ctx.data.relationships
                if r.source_entity_id == eid or r.target_entity_id == eid]
        rels_by_type: dict[str, int] = {}
        linked_names: set[str] = set()
        for r in rels:
            rels_by_type[r.relationship_type] = rels_by_type.get(
                r.relationship_type, 0) + 1
            other = (r.target_entity_id if r.source_entity_id == eid
                     else r.source_entity_id)
            linked_names.add(ctx.name_of(other))
        events = [e for e in ctx.data.events if e.entity_id == eid]
        claims = [c for c in ctx.data.claims if c.subject_entity_id == eid]
        in_findings = [f for f in ctx.findings
                       if eid in (f.involved_entity_ids or [])]
        in_hyps = [h for h in ctx.hypotheses
                   if eid in (h.involved_entity_ids or [])]
        degree = (ctx.graph.graph.degree(f"e{eid}")
                  if f"e{eid}" in ctx.graph.graph else 0)

        confidence = _clamp01(0.4
                              + 0.15 * min(1.0, len(rels) / 3)
                              + 0.15 * min(1.0, len(events) / 3)
                              + 0.15 * min(1.0, len(claims) / 2)
                              + 0.15 * min(1.0, len(in_findings) / 2))
        citations = [self._c_entity(ctx, eid)]
        citations += [self._c_relationship(ctx, r.id) for r in rels[:8]]
        citations += [self._c_event(ctx, e) for e in events[:8]]
        citations += [self._c_finding(f) for f in in_findings[:3]]

        conn = f"Connections: {len(rels)} confirmed relationship(s)"
        if rels_by_type:
            conn += " — " + ", ".join(f"{k}×{v}"
                                      for k, v in sorted(rels_by_type.items()))
        if linked_names:
            conn += ". Linked to: " + ", ".join(sorted(linked_names))
        conn += ".\n"
        tl = f"Timeline: {len(events)} recorded event(s)."
        if any(e.timestamp for e in events):
            tl += " Most recent: " + _fmt_ts(max(e.timestamp for e in events
                                                 if e.timestamp)) + "."
        tl += "\n"
        cl = f"Structured claims: {len(claims)}."
        if claims:
            cl += " Example: " + " ".join(
                f"{c.predicate} {c.object_value or ''}".strip()
                for c in claims[:2]) + "."
        cl += "\n"
        text = (f"{ent.canonical_name} ({ent.entity_type}).\n\n"
                + conn + tl + cl
                + f"Appears in {len(in_findings)} finding(s) and "
                  f"{len(in_hyps)} hypothesis(es). Network degree in the "
                  f"case graph: {degree}.")
        return CopilotAnswer(
            intent.intent, intent.interpretation, answer_text=text,
            confidence=confidence,
            confidence_basis=("0.4 + 0.15·min(1,rels/3) + 0.15·min(1,events/3) "
                              "+ 0.15·min(1,claims/2) + 0.15·min(1,findings/2)"),
            citations=self._dedupe(citations),
            data={"entity_id": eid, "entity_type": ent.entity_type,
                  "canonical_name": ent.canonical_name,
                  "aliases": aliases, "relationships": rels_by_type,
                  "linked_entities": sorted(linked_names),
                  "event_count": len(events), "claim_count": len(claims),
                  "finding_count": len(in_findings),
                  "hypothesis_count": len(in_hyps), "degree": degree},
            suggestions=self._suggestions(ctx, [
                f"Who is connected to {ent.canonical_name}?",
                "What happened to " + ent.canonical_name + "?",
                "Find evidence about " + ent.canonical_name + "."]))

    def _i_relationship_path(self, ctx, intent) -> CopilotAnswer:
        a_name, b_name = intent.params.get("a"), intent.params.get("b")
        a_id, _ = ctx.resolve_all(a_name) if a_name else (None, None)
        b_id, _ = ctx.resolve_all(b_name) if b_name else (None, None)
        if a_id is None or b_id is None:
            bad = a_name if a_id is None else b_name
            return CopilotAnswer(
                intent.intent, intent.interpretation, status="unsupported",
                answer_text=f"Could not resolve “{bad}” to a confirmed "
                            "entity in this case.",
                confidence=0.0, confidence_basis="Name not resolved.",
                suggestions=self._suggestions(ctx, []))
        if a_id == b_id:
            return CopilotAnswer(
                intent.intent, intent.interpretation, status="answered",
                answer_text=f"Both names resolve to the same confirmed "
                            f"entity: {ctx.name_of(a_id)}.",
                confidence=1.0, confidence_basis="Same entity.",
                citations=[self._c_entity(ctx, a_id)],
                data={"a": a_id, "b": b_id, "path": [a_id], "hops": 0},
                suggestions=self._suggestions(ctx, []))

        cutoff = intent.params.get("cutoff") or 5
        g = ctx.graph.graph
        na, nb = f"e{a_id}", f"e{b_id}"
        try:
            path = nx.shortest_path(g, na, nb)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            path = None
        if path is None:
            return CopilotAnswer(
                intent.intent, intent.interpretation, status="not_enough_data",
                answer_text=(f"No confirmed connection between "
                             f"{ctx.name_of(a_id)} and {ctx.name_of(b_id)} "
                             f"within {cutoff} hops. Absence of a confirmed "
                             "path is not evidence of no connection — only "
                             "that none is recorded in the confirmed data."),
                confidence=0.0,
                confidence_basis="No path in the confirmed graph.",
                citations=[self._c_entity(ctx, a_id),
                           self._c_entity(ctx, b_id)],
                data={"a": a_id, "b": b_id, "path": None, "hops": None},
                suggestions=self._suggestions(ctx, []))

        ids = [int(n[1:]) for n in path]
        hops = len(ids) - 1
        edges = []
        for i in range(len(path) - 1):
            key = tuple(sorted((path[i], path[i + 1])))
            info = ctx.graph.edges.get(key)
            edges.append({"from": ids[i], "to": ids[i + 1],
                          "relationship_type":
                              info.relationship_type if info else None,
                          "relationship_id": info.relationship_id if info else None})
        confidence = _clamp01(1.0 - 0.15 * (hops - 1))
        citations = [self._c_entity(ctx, i) for i in ids]
        citations += [self._c_relationship(ctx, e["relationship_id"])
                      for e in edges if e["relationship_id"]]
        chain = " → ".join(
            f"{ctx.name_of(i)}" for i in ids)
        text = (f"Confirmed connection: {a_name} → {b_name} in {hops} hop(s).\n\n"
                f"Path: {chain}\n"
                + "\n".join(f"  • {ctx.name_of(e['from'])} "
                            f"{(e['relationship_type'] or '—').lower()} "
                            f"{ctx.name_of(e['to'])}" for e in edges)
                + "\n\nThis path uses confirmed relationships only; it is a "
                  "recorded association, not an assertion of conduct.")
        return CopilotAnswer(
            intent.intent, intent.interpretation, answer_text=text,
            confidence=confidence,
            confidence_basis=("1.0 − 0.15·(hops−1); shorter confirmed paths "
                              f"are more direct. hops = {hops}."),
            citations=self._dedupe(citations),
            data={"a": a_id, "b": b_id, "hops": hops, "path": ids,
                  "edges": edges},
            suggestions=self._suggestions(ctx, [
                f"Who is connected to {ctx.name_of(a_id)}?",
                f"Who is connected to {ctx.name_of(b_id)}?"]))

    def _i_neighbourhood(self, ctx, intent) -> CopilotAnswer:
        name = intent.params.get("node")
        eid, _ = ctx.resolve_all(name) if name else (None, None)
        if eid is None:
            return CopilotAnswer(
                intent.intent, intent.interpretation, status="unsupported",
                answer_text=f"“{name}” is not a confirmed entity in this case.",
                confidence=0.0, confidence_basis="Name not resolved.",
                suggestions=self._suggestions(ctx, []))
        hops = min(int(intent.params.get("hops") or 2), 5)
        g = ctx.graph.graph
        center = f"e{eid}"
        if center not in g:
            return CopilotAnswer(
                intent.intent, intent.interpretation, status="not_enough_data",
                answer_text=f"{ctx.name_of(eid)} has no confirmed "
                            "relationships in this case.",
                confidence=0.0, confidence_basis="Isolated node.",
                citations=[self._c_entity(ctx, eid)],
                data={"node": eid, "neighbours": []},
                suggestions=self._suggestions(ctx, []))
        try:
            dist = nx.single_source_shortest_path_length(g, center, cutoff=hops)
        except nx.NodeNotFound:
            dist = {}
        neighbours = []
        for nid, d in sorted(dist.items()):
            if nid == center:
                continue
            nid_int = int(nid[1:])
            ent = ctx.data.entities_by_id.get(nid_int)
            neighbours.append({"entity_id": nid_int,
                               "name": ent.canonical_name if ent else nid,
                               "entity_type": ent.entity_type if ent else "?",
                               "distance": d})
        neighbours.sort(key=lambda x: (x["distance"], x["name"]))
        confidence = _clamp01(0.5 + 0.5 * min(1.0, len(neighbours) / 10))
        citations = [self._c_entity(ctx, eid)]
        citations += [self._c_entity(ctx, n["entity_id"]) for n in neighbours[:10]]
        text = (f"Within {hops} hop(s) of {ctx.name_of(eid)}, the confirmed "
                f"network contains {len(neighbours)} other entit"
                + ("y." if len(neighbours) == 1 else "ies.") + "\n\n"
                + "\n".join(f"  • {n['name']} ({n['entity_type']}) — "
                            f"{n['distance']} hop(s) away"
                            for n in neighbours[:15])
                + ("" if len(neighbours) <= 15 else f"\n  • … and {len(neighbours)-15} more.")
                + "\n\nListed relationships are confirmed records only.")
        return CopilotAnswer(
            intent.intent, intent.interpretation, answer_text=text,
            confidence=confidence,
            confidence_basis=("0.5 + 0.5·min(1, neighbours/10) — breadth of "
                              f"the retrieved neighbourhood ({len(neighbours)})."),
            citations=self._dedupe(citations),
            data={"node": eid, "hops": hops, "neighbours": neighbours},
            suggestions=self._suggestions(ctx, [
                f"What happened to {ctx.name_of(eid)}?",
                "Find evidence about " + ctx.name_of(eid) + "."]))

    def _i_timeline(self, ctx, intent) -> CopilotAnswer:
        node = intent.params.get("node")
        eid, _ = ctx.resolve_all(node) if node else (None, None)
        events = [e for e in ctx.data.events
                  if eid is None or e.entity_id == eid]
        dated = [e for e in events if e.timestamp is not None]
        dated.sort(key=lambda e: (e.timestamp, e.id))
        if not events:
            scope = ctx.name_of(eid) if eid else "this case"
            return CopilotAnswer(
                intent.intent, intent.interpretation, status="not_enough_data",
                answer_text=f"No timeline events are recorded for {scope}.",
                confidence=0.0, confidence_basis="No events.",
                citations=[self._c_entity(ctx, eid)] if eid else [],
                data={"events": []},
                suggestions=self._suggestions(ctx, []))
        confidence = _clamp01(0.4 + 0.6 * (len(dated) / len(events)))
        citations = [self._c_event(ctx, e) for e in dated[:15]]
        if eid is not None:
            citations.append(self._c_entity(ctx, eid))
        scope = ctx.name_of(eid) if eid else "the case"
        lines = []
        for e in dated[:15]:
            lines.append(f"  • {_fmt_ts(e.timestamp)} — {e.event_type}: "
                         f"{ctx.name_of(e.entity_id)} at "
                         f"{ctx.location_name(e.location_id)}"
                         + (f" (evidence E{e.evidence_id})" if e.evidence_id else ""))
        text = (f"Timeline for {scope}: {len(events)} event(s), "
                f"{len(dated)} dated.\n" + "\n".join(lines)
                + (f"\n  … and {len(dated)-15} more." if len(dated) > 15 else "")
                + "\n\nEvents are confirmed records; ordering is by recorded "
                  "timestamp.")
        return CopilotAnswer(
            intent.intent, intent.interpretation, answer_text=text,
            confidence=confidence,
            confidence_basis=("0.4 + 0.6·(dated/total events) — a fully dated "
                              f"timeline is exact ({len(dated)}/{len(events)})."),
            citations=self._dedupe(citations),
            data={"scope": eid, "event_count": len(events),
                  "dated_count": len(dated),
                  "events": [{"id": e.id, "type": e.event_type,
                              "timestamp": _fmt_ts(e.timestamp),
                              "entity": ctx.name_of(e.entity_id),
                              "location": ctx.location_name(e.location_id),
                              "evidence_id": e.evidence_id}
                             for e in dated]},
            suggestions=self._suggestions(ctx, [
                "What contradictions are there?",
                "What is missing from the case?"]))

    def _i_contradictions(self, ctx, intent) -> CopilotAnswer:
        rows = self._findings_of(ctx, "CONTRADICTION")
        rows.sort(key=lambda f: (0 if (f.details or {}).get("severity") == "HIGH"
                                 else 1, f.title))
        if not rows:
            return CopilotAnswer(
                intent.intent, intent.interpretation, status="answered",
                answer_text="No potential contradictions were detected in the "
                            "confirmed records. This means the analyzed "
                            "pairs satisfied all rules — it is not a "
                            "declaration that every record is consistent.",
                confidence=1.0,
                confidence_basis="Engine evaluated the confirmed pairs; none "
                                 "violated R1–R4.",
                data={"contradictions": []},
                suggestions=self._suggestions(ctx, ["What is missing?"]))
        citations, items = [], []
        for f in rows[:10]:
            citations.append(self._c_finding(f))
            for ev_id in (f.supporting_evidence_ids or [])[:3]:
                citations.append(self._c_evidence(ctx, ev_id))
            items.append({"id": f.id, "title": f.title,
                          "type": (f.details or {}).get("contradiction_type"),
                          "severity": (f.details or {}).get("severity"),
                          "summary": f.summary,
                          "status": f.status})
        text = (f"{len(rows)} potential contradiction(s) detected in the "
                "confirmed records:\n"
                + "\n".join(f"  • [{it['severity'] or '—'}] {it['title']}"
                            for it in items)
                + "\n\nThese are analytical flags over confirmed records "
                  "requiring investigator review — not determinations that "
                  "any record is false.")
        return CopilotAnswer(
            intent.intent, intent.interpretation, answer_text=text,
            confidence=1.0,
            confidence_basis="Computed by contradiction-engine v2 over "
                             "confirmed records only.",
            citations=self._dedupe(citations),
            data={"contradictions": items},
            suggestions=self._suggestions(ctx, ["What are the competing hypotheses?"]))

    def _i_gaps(self, ctx, intent) -> CopilotAnswer:
        rows = self._findings_of(ctx, "INVESTIGATION_GAP")
        if not rows:
            return CopilotAnswer(
                intent.intent, intent.interpretation, status="answered",
                answer_text="No investigation gaps were flagged by the "
                            "gap engine for the current confirmed data.",
                confidence=1.0,
                confidence_basis="Gap engine ran over the confirmed data.",
                data={"gaps": []},
                suggestions=self._suggestions(ctx, []))
        citations, items = [], []
        for f in rows[:10]:
            citations.append(self._c_finding(f))
            items.append({"id": f.id, "title": f.title,
                          "gap_type": (f.details or {}).get("gap_type"),
                          "summary": f.summary})
        text = (f"{len(rows)} investigation gap(s) flagged:\n"
                + "\n".join(f"  • [{it['gap_type'] or '—'}] {it['title']}"
                            for it in items)
                + "\n\nGaps mark where the confirmed data is insufficient — "
                  "a pointer to what to verify next, not a conclusion.")
        return CopilotAnswer(
            intent.intent, intent.interpretation, answer_text=text,
            confidence=1.0,
            confidence_basis="Computed by the deterministic gap engine.",
            citations=self._dedupe(citations),
            data={"gaps": items},
            suggestions=self._suggestions(ctx, []))

    def _i_hypotheses(self, ctx, intent) -> CopilotAnswer:
        rows = sorted(ctx.hypotheses,
                      key=lambda h: (-h.analytical_score, h.id))
        if not rows:
            return CopilotAnswer(
                intent.intent, intent.interpretation, status="not_enough_data",
                answer_text="No hypotheses have been generated for this case "
                            "yet. Run the investigation analysis to produce "
                            "the deterministic hypothesis set.",
                confidence=0.0, confidence_basis="No hypothesis rows.",
                data={"hypotheses": []},
                suggestions=self._suggestions(ctx, ["Summarize the case"]))
        citations, items = [], []
        for h in rows[:8]:
            citations.append(self._c_hypothesis(h))
            for ev_id in (h.supporting_evidence_ids or [])[:2]:
                citations.append(self._c_evidence(ctx, ev_id))
            items.append({"id": h.id, "title": h.title,
                          "type": h.hypothesis_type,
                          "score": h.analytical_score,
                          "band": h.confidence_band,
                          "description": h.description,
                          "status": h.status})
        top_score = items[0]["score"] if items else 0.0
        text = (f"{len(rows)} hypothesis(es) on record, ranked by "
                "deterministic analytical score:\n"
                + "\n".join(f"  • [{it['band']}] {it['title']} "
                            f"(score {it['score']:.2f})" for it in items)
                + "\n\nScores are computed from confirmed signals with "
                  "visible components; they are not probabilities of guilt.")
        return CopilotAnswer(
            intent.intent, intent.interpretation, answer_text=text,
            confidence=_clamp01(top_score),
            confidence_basis=("Top hypothesis's deterministic analytical "
                              f"score ({top_score:.2f})."),
            citations=self._dedupe(citations),
            data={"hypotheses": items},
            suggestions=self._suggestions(ctx, ["What contradictions are there?"]))

    def _evidence_for_entity(self, ctx, eid: int) -> list[int]:
        out: set[int] = set()
        for r in ctx.data.relationships:
            if r.source_entity_id != eid and r.target_entity_id != eid:
                continue
            if r.candidate_id is not None:
                out.update(ctx.data.evidence_index.get(
                    f"candidate:{r.candidate_id}", []))
        for e in ctx.data.events:
            if e.entity_id == eid and e.evidence_id:
                out.add(e.evidence_id)
        for c in ctx.data.claims:
            if c.subject_entity_id == eid:
                out.add(c.evidence_id)
        return sorted(out)

    def _i_evidence_lookup(self, ctx, intent) -> CopilotAnswer:
        eid = intent.params.get("evidence_id")
        if eid is not None:
            ev = next((v for v in ctx.data.evidence if v.id == eid), None)
            if ev is None:
                return CopilotAnswer(
                    intent.intent, intent.interpretation, status="not_enough_data",
                    answer_text=f"Evidence record {eid} does not exist in "
                                "this case.",
                    confidence=0.0, confidence_basis="Record not found.",
                    data={}, suggestions=self._suggestions(ctx, []))
            linked_rels = [r.id for r in ctx.data.relationships
                           if r.candidate_id is not None
                           and eid in ctx.data.evidence_index.get(
                               f"candidate:{r.candidate_id}", [])]
            linked_events = [e.id for e in ctx.data.events
                             if e.evidence_id == eid]
            linked_claims = [c for c in ctx.data.claims if c.evidence_id == eid]
            cited_findings = [f for f in ctx.findings
                              if eid in (f.supporting_evidence_ids or [])]
            cited_hyps = [h for h in ctx.hypotheses
                          if eid in (h.supporting_evidence_ids or [])
                          or eid in (h.contradicting_evidence_ids or [])]
            citations = [self._c_evidence(ctx, eid)]
            citations += [self._c_relationship(ctx, r) for r in linked_rels[:6]]
            citations += [self._c_event(ctx, e) for e in
                          [e for e in ctx.data.events if e.id in linked_events][:6]]
            citations += [self._c_claim(ctx, c) for c in linked_claims[:4]]
            citations += [self._c_finding(f) for f in cited_findings[:3]]
            text = (f"Evidence E{eid} — {ev.evidence_type}"
                    + (f" (document {ev.document_id})" if ev.document_id else "")
                    + (f", source reference “{ev.source_reference}”"
                       if ev.source_reference else "") + ".\n"
                    f"Linked: {len(linked_rels)} confirmed relationship(s), "
                    f"{len(linked_events)} timeline event(s), "
                    f"{len(linked_claims)} structured claim(s).\n"
                    f"Cited by {len(cited_findings)} finding(s) and "
                    f"{len(cited_hyps)} hypothesis(es).\n\n"
                    "Use the impact question to see what removing this record "
                    "would change (simulation only).")
            return CopilotAnswer(
                intent.intent, intent.interpretation, answer_text=text,
                confidence=1.0,
                confidence_basis="Record exists; linkage computed from "
                                 "confirmed provenance.",
                citations=self._dedupe(citations),
                data={"evidence_id": eid, "type": ev.evidence_type,
                      "source_reference": ev.source_reference,
                      "linked_relationships": linked_rels,
                      "linked_events": linked_events,
                      "claims": len(linked_claims),
                      "cited_by_findings": [f.id for f in cited_findings],
                      "cited_by_hypotheses": [h.id for h in cited_hyps]},
                suggestions=self._suggestions(ctx,
                                              [f"What happens if we remove E{eid}?"]))

        node = intent.params.get("node")
        if node:
            eid2, canon = ctx.resolve_all(node)
            if eid2 is None:
                return CopilotAnswer(
                    intent.intent, intent.interpretation, status="unsupported",
                    answer_text=f"“{node}” is not a confirmed entity.",
                    confidence=0.0, confidence_basis="Name not resolved.",
                    suggestions=self._suggestions(ctx, []))
            ev_ids = self._evidence_for_entity(ctx, eid2)
            citations = [self._c_entity(ctx, eid2)]
            citations += [self._c_evidence(ctx, i) for i in ev_ids[:10]]
            if not ev_ids:
                text = (f"No evidence rows are linked to {canon} through "
                        "confirmed relationships, events or claims.")
            else:
                text = (f"{len(ev_ids)} evidence record(s) are linked to "
                        f"{canon}: " + ", ".join(f"E{i}" for i in ev_ids[:10])
                        + ("." if len(ev_ids) <= 10 else ", …") + "")
            return CopilotAnswer(
                intent.intent, intent.interpretation, answer_text=text,
                confidence=_clamp01(0.5 + 0.5 * min(1.0, len(ev_ids) / 5)),
                confidence_basis="0.5 + 0.5·min(1, linked_evidence/5).",
                citations=self._dedupe(citations),
                data={"entity": eid2, "evidence_ids": ev_ids},
                suggestions=self._suggestions(ctx,
                                              [f"What happens if we remove E{ev_ids[0]}?" if ev_ids else ""]))
        # whole case
        evs = ctx.data.evidence
        citations = [self._c_evidence(ctx, v.id) for v in evs[:15]]
        text = (f"The case has {len(evs)} confirmed evidence record(s). "
                "Ask about a specific record (e.g. “what is E17?”) or about "
                "a person (e.g. “find evidence about "
                + (ctx.data.entities[0].canonical_name
                   if ctx.data.entities else "the main person") + "”).")
        return CopilotAnswer(
            intent.intent, intent.interpretation, answer_text=text,
            confidence=1.0, confidence_basis="Count of confirmed records.",
            citations=self._dedupe(citations),
            data={"evidence_count": len(evs),
                  "evidence_ids": [v.id for v in evs[:50]]},
            suggestions=self._suggestions(ctx,
                                          [f"What is E{evs[0].id}?" if evs else ""]))

    def _i_location_query(self, ctx, intent) -> CopilotAnswer:
        """Locations for a person or the case, from the three confirmed
        sources (never mixed, always cited):

          1. location rows (carrying coordinates — geospatial-capable),
          2. confirmed location *entities* referenced by structured claims
             (extracted locations become entity rows, not location rows),
          3. structured claim object values (text) with no entity link.

        A location therefore shows up even when the case has no coordinate
        rows — the stage-5 multilingual cases store places as entities.
        """
        from ..context import _norm
        node = intent.params.get("node")
        eid, _ = ctx.resolve_all(node) if node else (None, None)

        refs: dict[str, dict] = {}

        def add(name, entity_id=None, location_id=None,
                lat=None, lon=None, claim=None):
            if not name:
                return
            ref = refs.setdefault(_norm(name), {
                "name": name, "entity_id": None, "location_id": None,
                "lat": None, "lon": None, "claims": []})
            ref["entity_id"] = ref["entity_id"] or entity_id
            if location_id is not None:
                ref["location_id"] = location_id
                row = next((l for l in ctx.data.locations
                            if l.id == location_id), None)
                if row is not None:
                    ref["lat"], ref["lon"] = row.latitude, row.longitude
            if lat is not None:
                ref["lat"], ref["lon"] = lat, lon
            if claim is not None and claim not in ref["claims"]:
                ref["claims"].append(claim)

        # (3) + (2): structured claims — the person's own claims when the
        # question is scoped to a person, all claims in case scope.
        for c in ctx.data.claims:
            if eid is not None and c.subject_entity_id != eid:
                continue
            ent = (ctx.data.entities_by_id.get(c.object_entity_id)
                   if c.object_entity_id else None)
            if ent is not None and ent.entity_type == "location":
                add(ent.canonical_name, entity_id=ent.id,
                    location_id=c.location_id, claim=c)
            elif c.object_value:
                add(c.object_value, location_id=c.location_id, claim=c)

        # (1): location rows — all in case scope; rows tied to the person
        # (via their claims or timeline events) in person scope.
        for l in ctx.data.locations:
            if eid is None:
                add(l.name, location_id=l.id, lat=l.latitude,
                    lon=l.longitude)
            elif any(c.subject_entity_id == eid and c.location_id == l.id
                     for c in ctx.data.claims) or \
                 any(e.entity_id == eid and e.location_id == l.id
                     for e in ctx.data.events):
                add(l.name, location_id=l.id, lat=l.latitude,
                    lon=l.longitude)

        # case scope: confirmed location entities even without claims yet
        if eid is None:
            for e in ctx.data.entities:
                if e.entity_type == "location":
                    add(e.canonical_name, entity_id=e.id)

        if not refs:
            scope = ctx.name_of(eid) if eid else "this case"
            return CopilotAnswer(
                intent.intent, intent.interpretation, status="not_enough_data",
                answer_text=f"No locations are recorded for {scope}.",
                confidence=0.0, confidence_basis="No locations.",
                data={"locations": []},
                suggestions=self._suggestions(ctx, []))

        locs = sorted(refs.values(),
                      key=lambda r: (-len(r["claims"]), r["name"].lower()))
        with_coords = [r for r in locs if r["lat"] is not None]
        confidence = _clamp01(0.5 + 0.5 * (len(with_coords) / len(locs)))
        citations = []
        for r in locs[:10]:
            if r["location_id"] is not None:
                citations.append(self._c_location(ctx, r["location_id"]))
            elif r["entity_id"] is not None:
                citations.append(self._c_entity(ctx, r["entity_id"]))
            citations.extend(self._c_claim(ctx, c) for c in r["claims"][:3])
        if eid is not None:
            citations.append(self._c_entity(ctx, eid))
        lines = []
        for r in locs[:15]:
            line = f"  • {r['name']}"
            if r["lat"] is not None:
                line += f" ({r['lat']:.4f}, {r['lon']:.4f})"
            if r["claims"]:
                line += f" — {len(r['claims'])} structured claim(s)"
                times = sorted({t for c in r["claims"]
                                if (t := _fmt_ts(c.event_time))})
                if times:
                    line += f", {times[0]}" + (f"–{times[-1]}"
                                               if len(times) > 1 else "")
            elif r["location_id"] is None and r["entity_id"] is not None:
                line += " (confirmed location, no coordinates)"
            lines.append(line)
        text = (f"Locations" + (f" for {ctx.name_of(eid)}" if eid else " in the case")
                + f": {len(locs)}.\n" + "\n".join(lines)
                + "\n\nLocations are confirmed records; coordinates enable "
                  "geospatial analysis when present.")
        return CopilotAnswer(
            intent.intent, intent.interpretation, answer_text=text,
            confidence=confidence,
            confidence_basis=("0.5 + 0.5·(with_coordinates/total) — "
                              "geospatial rules need coordinates."),
            citations=self._dedupe(citations),
            data={"scope": eid, "locations": [
                {"id": r["location_id"] or r["entity_id"], "name": r["name"],
                 "latitude": r["lat"], "longitude": r["lon"],
                 "claims": [c.id for c in r["claims"]]} for r in locs]},
            suggestions=self._suggestions(ctx, ["What happened?"]))

    def _i_impact_simulation(self, ctx, intent) -> CopilotAnswer:
        eid = intent.params.get("evidence_id")
        ev = next((v for v in ctx.data.evidence if v.id == eid), None)
        if ev is None:
            return CopilotAnswer(
                intent.intent, intent.interpretation, status="not_enough_data",
                answer_text=f"Evidence record {eid} does not exist in this "
                            "case, so there is nothing to simulate.",
                confidence=0.0, confidence_basis="Record not found.",
                data={}, suggestions=self._suggestions(ctx, []))
        if ctx.db is None:  # defensive: never simulate without a session
            return CopilotAnswer(
                intent.intent, intent.interpretation, status="error",
                answer_text="The impact simulator is unavailable.",
                confidence=0.0, confidence_basis="No session.",
                data={}, suggestions=[])
        diff = simulate_removal(ctx.db, ctx.data, eid)
        removed = diff.get("edges_removed", [])
        dd = diff.get("diff", {})
        degree_changes = dd.get("degree_changes", [])
        betweenness_changes = dd.get("betweenness_changes", [])
        comp_before = dd.get("components_before")
        comp_after = dd.get("components_after")
        disc = dd.get("newly_disconnected_pairs", [])
        isolated = diff.get("newly_isolated_entities", [])
        citations = [self._c_evidence(ctx, eid)]
        for e in removed[:5]:
            for nid in e.get("edge", []):
                try:
                    citations.append(self._c_entity(ctx, int(nid[1:])))
                except (ValueError, IndexError):
                    pass
        if not removed:
            text = (f"Simulation (nothing changed): removing E{eid} would not "
                    "remove any confirmed relationship — every linked pair "
                    "is supported by other evidence or by unproven records. "
                    f"Degree changes: {len(degree_changes)}; betweenness "
                    f"changes: {len(betweenness_changes)}.")
        else:
            text = (f"Simulation (nothing changed): removing E{eid} would "
                    f"remove {len(removed)} confirmed edge(s):\n"
                    + "\n".join(f"  • {e.get('edge')} — {e.get('rule', '')}"
                                for e in removed[:8])
                    + (f"\n  … and {len(removed)-8} more." if len(removed) > 8 else "")
                    + f"\n\nNewly disconnected pairs: {len(disc)}"
                    + (f"; newly isolated: "
                       + ", ".join(i.get("name") or i.get("node", "?")
                                   for i in isolated[:5])
                       if isolated else "")
                    + f". Network components: {comp_before} → {comp_after}.")
        text += ("\n\nThis is a what-if over the in-memory confirmed graph; "
                 "no stored record was created, modified or deleted.")
        return CopilotAnswer(
            intent.intent, intent.interpretation, answer_text=text,
            confidence=1.0,
            confidence_basis="Deterministic in-memory diff of the confirmed "
                             "graph (simulation_only).",
            citations=self._dedupe(citations),
            data={"evidence_id": eid, "simulation_only": True,
                  "edges_removed": removed,
                  "newly_isolated_entities": isolated,
                  "diff": dd,
                  "affected_findings": diff.get("affected_findings", [])},
            suggestions=self._suggestions(ctx, [f"What is E{eid}?"]))

    def _i_entity_search(self, ctx, intent) -> CopilotAnswer:
        from ..search import search_case
        q = (intent.params.get("query") or "").strip()
        if not q:
            return CopilotAnswer(
                intent.intent, intent.interpretation, status="unsupported",
                answer_text="Nothing to search for.",
                confidence=0.0, confidence_basis="Empty query.",
                data={}, suggestions=self._suggestions(ctx, []))
        res = search_case(ctx, q)
        hits = res["hits"]
        if not hits:
            return CopilotAnswer(
                intent.intent, intent.interpretation, status="answered",
                answer_text=(f"No confirmed records in this case match “{q}”. "
                             "The search covers entities, relationships, "
                             "evidence, events, locations and claims — all "
                             "confirmed data only."),
                confidence=1.0,
                confidence_basis="Zero matches over the confirmed data set.",
                data={"query": q, "hits": []},
                suggestions=self._suggestions(ctx, []))
        citations = []
        for h in hits[:20]:
            getter = {"entity": self._c_entity, "relationship":
                      self._c_relationship, "evidence": self._c_evidence,
                      "location": self._c_location}
            fn = getter.get(h["kind"])
            if fn:
                citations.append(fn(ctx, h["id"]))
            elif h["kind"] == "event":
                ev = next((e for e in ctx.data.events if e.id == h["id"]), None)
                if ev:
                    citations.append(self._c_event(ctx, ev))
            elif h["kind"] == "claim":
                cl = next((c for c in ctx.data.claims if c.id == h["id"]), None)
                if cl:
                    citations.append(self._c_claim(ctx, cl))
        kinds = res["counts"]
        text = (f"{len(hits)} confirmed record(s) match “{q}” "
                "(multilingual, case-scoped): "
                + ", ".join(f"{v} {k}" for k, v in sorted(kinds.items()))
                + ".\n" + "\n".join(
                    f"  • [{h['kind']}] {h['label']}"
                    for h in hits[:15])
                + (f"\n  … and {len(hits)-15} more." if len(hits) > 15 else "")
                + "\n\nMatches are over confirmed records only; no "
                  "free-text guessing.")
        return CopilotAnswer(
            intent.intent, intent.interpretation, answer_text=text,
            confidence=_clamp01(0.4 + 0.6 * min(1.0, len(hits) / 5)),
            confidence_basis="0.4 + 0.6·min(1, hits/5) — more precise "
                             f"matches ({len(hits)}) raise confidence.",
            citations=self._dedupe(citations),
            data={"query": q, "hit_count": len(hits), "hits": hits},
            suggestions=self._suggestions(ctx, []))

    # ------------------------------------------------------------- fallback
    def _i_unsupported(self, ctx, intent) -> CopilotAnswer:
        return CopilotAnswer(
            intent.intent, intent.interpretation, status="unsupported",
            answer_text="I can help with: case overview, an entity's "
                        "profile, connections between two people, a "
                        "person's network, the timeline, contradictions, "
                        "gaps, hypotheses, evidence lookup (E<id>), "
                        "locations, impact simulation, and a multilingual "
                        "search.",
            confidence=0.0, confidence_basis="Intent not recognized.",
            suggestions=self._suggestions(ctx, ["Summarize the case"]))
