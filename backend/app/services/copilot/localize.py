"""Localized answer rendering (stage 5 — multilingual question answering).

The deterministic provider always computes the *facts* — the structured
``data`` payload, the citations, the confidence and its basis — in the
canonical (English) layer. When the investigator asks in Hindi, Marathi
or Urdu, this module re-renders only the answer *prose* of that same
structured payload in the question's language.

Guarantees (same no-hallucination contract as the English layer):

* the structured ``data`` is the single source of truth — the templates
  can neither add nor remove facts, numbers or record references;
* evidence references keep their exact stable form (``E<id>``);
* the neutral analytical register is preserved ("potential", "requires
  review", "not a determination");
* citations and confidence are set by the provider and never touched
  here — only ``answer_text`` is replaced;
* an intent without a template falls back to the English text, and the
  answer reports this honestly via ``data["answer_language"]``.
"""
from __future__ import annotations

from typing import Callable

#: languages with localized templates (question-script detection codes)
LOCALIZED_LANGUAGES = ("hi", "mr", "ur")


def _name(ctx, entity_id: int | None) -> str:
    return ctx.name_of(entity_id) if entity_id is not None else "—"


def _fmt_edges(edges: list[dict], ctx) -> str:
    return "\n".join(
        f"  • {_name(ctx, e.get('from'))} — "
        f"{(e.get('relationship_type') or '—').lower()} — "
        f"{_name(ctx, e.get('to'))}"
        for e in edges)


# ------------------------------------------------------------------ Hindi
def _hi_case_overview(d, ctx):
    c = d.get("counts", {})
    case = d.get("case", {})
    out = (f"केस {case.get('number')} — {case.get('title')} "
           f"(स्थिति: {case.get('status')}, प्राथमिकता: {case.get('priority')}).\n\n"
           f"पुष्ट रिकॉर्ड: {c.get('entities', 0)} इकाइयाँ, "
           f"{c.get('relationships', 0)} संबंध, {c.get('evidence', 0)} साक्ष-रिकॉर्ड, "
           f"{c.get('timeline_events', 0)} समय-रेखा घटनाएँ, "
           f"{c.get('locations', 0)} स्थान, {c.get('claims', 0)} संरचित दावे.\n\n"
           f"विश्लेषण: {c.get('findings', 0)} निष्कर्ष और "
           f"{c.get('hypotheses', 0)} कल्पनाएँ दर्ज हैं। ")
    hf = d.get("high_findings") or []
    if hf:
        out += "प्रमुख: " + "; ".join(f["title"] for f in hf) + "। "
    else:
        out += "हाल में कोई उच्च-गंभीरता निष्कर्ष चिह्नित नहीं है। "
    out += ("ये पुष्ट रिकॉर्ड पर विश्लेषणात्मक परिणाम हैं — समीक्षा का "
            "आरंभिक बिंदु, निष्कर्ष नहीं।")
    return out


def _hi_entity_profile(d, ctx):
    rels = d.get("relationships") or {}
    rel_desc = ", ".join(f"{k}×{v}" for k, v in sorted(rels.items()))
    out = (f"{d.get('canonical_name')} ({d.get('entity_type')}).\n\n"
           f"संबंध: {sum(rels.values())} पुष्ट संबंध"
           + (f" — {rel_desc}" if rel_desc else "") + ". ")
    linked = d.get("linked_entities") or []
    if linked:
        out += "जुड़े हुए: " + ", ".join(linked) + ". "
    out += (f"\nसमय-रेखा: {d.get('event_count', 0)} दर्ज घटनाएँ।\n"
            f"संरचित दावे: {d.get('claim_count', 0)}।\n"
            f"निष्कर्षों में: {d.get('finding_count', 0)}; कल्पनाओं में: "
            f"{d.get('hypothesis_count', 0)}। केस-ग्राफ में नेटवर्क-कोटी: "
            f"{d.get('degree', 0)}।\n\nसभी पुष्ट रिकॉर्डों पर आधारित — "
            f"आचरण का निश्चय नहीं।")
    return out


def _hi_relationship_path(d, ctx):
    a, b = _name(ctx, d.get("a")), _name(ctx, d.get("b"))
    chain = " → ".join(_name(ctx, i) for i in d.get("path") or [])
    out = (f"पुष्ट संबंध: {a} → {b}, {d.get('hops')} कदम।\n\n"
           f"मार्ग: {chain}\n" + _fmt_edges(d.get("edges") or [], ctx) +
           "\n\nयह मार्ग केवल पुष्ट संबंधों से गठित है — दर्ज सहसंबंध, "
           "आचरण का आरोप नहीं।")
    return out


def _hi_neighbourhood(d, ctx):
    nbs = d.get("neighbours") or []
    lines = "\n".join(f"  • {n['name']} ({n['entity_type']}) — "
                      f"{n['distance']} कदम दूर" for n in nbs[:15])
    more = (f"\n  • … और {len(nbs) - 15} अन्य" if len(nbs) > 15 else "")
    return (f"{_name(ctx, d.get('node'))} से {d.get('hops')} कदमों के भीतर, "
            f"पुष्ट नेटवर्क में {len(nbs)} अन्य इकाइयाँ हैं:\n" + lines + more +
            "\n\nसभी दर्ज संबंध पुष्ट रिकॉर्ड हैं।")


def _hi_timeline(d, ctx):
    events = d.get("events") or []
    scope = _name(ctx, d.get("scope")) if d.get("scope") else "केस"
    lines = "\n".join(
        f"  • {e['timestamp']} — {e['type']}: {e['entity']} "
        f"({e['location']})" + (f" (साक्ष E{e['evidence_id']})"
                                if e.get("evidence_id") else "")
        for e in events[:15])
    more = (f"\n  … और {d.get('dated_count', 0) - 15} अन्य"
            if d.get("dated_count", 0) > 15 else "")
    return (f"{scope} की समय-रेखा: {d.get('event_count', 0)} घटनाएँ, "
            f"{d.get('dated_count', 0)} तिथिबद्ध।\n" + lines + more +
            "\n\nघटनाएँ पुष्ट रिकॉर्ड हैं; क्रव दर्ज तिथि-काल के अनुसार।")


def _hi_contradictions(d, ctx):
    items = d.get("contradictions") or []
    lines = "\n".join(f"  • [{it.get('severity') or '—'}] {it['title']}"
                      for it in items)
    return (f"पुष्ट रिकॉर्ड में {len(items)} संभावित विरोधाभास मिला गया:\n"
            + lines +
            "\n\nये पुष्ट रिकॉर्ड पर विश्लेषणात्मक चिह्न हैं — किसी रिकॉर्ड के"
            " झूठे होने का निश्चय नहीं। जाँच-अधिकारी की समीक्षा आवश्यक।")


def _hi_gaps(d, ctx):
    items = d.get("gaps") or []
    lines = "\n".join(f"  • [{it.get('gap_type') or '—'}] {it['title']}"
                      for it in items)
    return (f"{len(items)} अनुसंधान-अंतर (gap) चिह्नित:\n" + lines +
            "\n\nअंतर दर्शाते हैं कि कहाँ पुष्ट डेटा अपर्याप्त है — अगली "
            "जाँच का संकेत, निष्कर्ष नहीं।")


def _hi_hypotheses(d, ctx):
    items = d.get("hypotheses") or []
    lines = "\n".join(f"  • [{it.get('band') or '—'}] {it['title']} "
                      f"(स्कोर {it.get('score', 0):.2f})" for it in items)
    return (f"दर्ज {len(items)} कल्पनाएँ, निश्चित विश्लेषणात्मक स्कोर के "
            f"अनुसार क्रमबद्ध:\n" + lines +
            "\n\nस्कोर पुष्ट संकेतों से, दृश्य घटकों सहित गणनाएँ — "
            "दोष की संभावना नहीं।")


def _hi_evidence_lookup(d, ctx):
    out = (f"साक्ष E{d.get('evidence_id')} — {d.get('type')}"
           + (f", स्रोत-संदर्भ “{d.get('source_reference')}”"
              if d.get("source_reference") else "") + ".\n"
           f"संबंधित: {len(d.get('linked_relationships') or [])} पुष्ट संबंध, "
           f"{len(d.get('linked_events') or [])} समय-रेखा घटनाएँ, "
           f"{d.get('claims', 0)} संरचित दावे।\n"
           f"{len(d.get('cited_by_findings') or [])} निष्कर्ष और "
           f"{len(d.get('cited_by_hypotheses') or [])} कल्पनाओं द्वारा "
           "उद्धृत।")
    return out


def _hi_location_query(d, ctx):
    locs = d.get("locations") or []
    scope = _name(ctx, d.get("scope")) if d.get("scope") else "इस केस"
    lines = []
    for r in locs[:15]:
        line = f"  • {r['name']}"
        if r.get("latitude") is not None:
            line += f" ({r['latitude']:.4f}, {r['longitude']:.4f})"
        n = len(r.get("claims") or [])
        if n:
            line += f" — {n} संरचित दावे"
        lines.append(line)
    return (f"{scope} के स्थान: {len(locs)}।\n" + "\n".join(lines) +
            "\n\nस्थान पुष्ट रिकॉर्ड हैं; निर्देशांक उपस्थित होने पर "
            "भू-वैश्विक विश्लेषण संभव है।")


def _hi_impact_simulation(d, ctx):
    removed = d.get("edges_removed") or []
    dd = d.get("diff") or {}
    isolated = d.get("newly_isolated_entities") or []
    if not removed:
        body = (f"E{d.get('evidence_id')} हटाने से कोई पुष्ट संबंध नहीं "
                f"हटता — प्रत्येक जोड़ी अन्य साक्ष से समर्थित है।")
    else:
        body = (f"E{d.get('evidence_id')} हटाने से {len(removed)} पुष्ट "
                f"किनारा/किनारे हटेंगे:\n" +
                "\n".join(f"  • {e.get('edge')} — {e.get('rule', '')}"
                          for e in removed[:8]) +
                (f"\n  … और {len(removed) - 8} अन्य"
                 if len(removed) > 8 else ""))
        if isolated:
            body += ("\nनए अलगाव: " +
                     ", ".join(i.get("name") or i.get("node", "?")
                               for i in isolated[:5]) + ".")
    body += (f" नेटवर्क-घटक: {dd.get('components_before')} → "
             f"{dd.get('components_after')}.")
    return ("अनुकलन (कुछ नहीं बदला): " + body +
            "\n\nयह स्मृति-आधारित पुष्ट ग्राफ पर what-if है; कोई संचित "
            "रिकॉर्ड रचा, बदला या हटाया नहीं गया।")


def _hi_entity_search(d, ctx):
    hits = d.get("hits") or []
    if not hits:
        return (f"इस केस के पुष्ट रिकॉर्डों में “{d.get('query')}” से मेल"
                " खाता कोई रिकॉर्ड नहीं। खोज इकाइयाँ, संबंध, साक्ष, घटनाएँ, "
                "स्थान और दावे — केवल पुष्ट डेटा — ढूँढती है।")
    lines = "\n".join(f"  • {h['label']} ({h['kind']})" for h in hits[:20])
    return (f"पुष्ट रिकॉर्डों में “{d.get('query')}” के लिए "
            f"{d.get('hit_count', len(hits))} परिणाम:\n" + lines +
            "\n\nकेवल पुष्ट डेटा पर खोज।")


def _hi_unsupported(d, ctx):
    return ("मैं इनमें सहायता कर सकता हूँ: केस-सारांश, किसी इकाई का "
            "प्रोफ़ाइल, दो लोगों के बीच संबंध, किसी की नेटवर्क, "
            "समय-रेखा, विरोधाभास, अंतर (gaps), कल्पनाएँ, साक्ष-अनुসन्धान "
            "(E<id>), स्थान, प्रभाव-अनुकलन, और बहुभाषी खोज।")


# ------------------------------------------------------------------ Marathi
def _mr_case_overview(d, ctx):
    c = d.get("counts", {})
    case = d.get("case", {})
    out = (f"केस {case.get('number')} — {case.get('title')} "
           f"(स्थिती: {case.get('status')}, प्राधान्य: {case.get('priority')}).\n\n"
           f"पुष्ट नोंदी: {c.get('entities', 0)} एकक, "
           f"{c.get('relationships', 0)} संबंध, {c.get('evidence', 0)} पुरावा-नोंदी, "
           f"{c.get('timeline_events', 0)} काल-रेखा घटना, "
           f"{c.get('locations', 0)} ठिकाणे, {c.get('claims', 0)} संरचित दावे.\n\n"
           f"विश्लेषण: {c.get('findings', 0)} निष्कर्ष आणि "
           f"{c.get('hypotheses', 0)} गृहीतके नोंदवली आहेत. ")
    hf = d.get("high_findings") or []
    if hf:
        out += "महत्त्वाचे: " + "; ".join(f["title"] for f in hf) + ". "
    else:
        out += "सध्या कोणताही उच्च-गंभीरता निष्कर्ष चिन्हांकित नाही. "
    out += ("हे पुष्ट नोंदींवरील विश्लेषणात्मक निकाल आहेत — पुनरावलोकनाचा "
            "सुरुवातीचा बिंदू, निष्कर्ष नाहीत.")
    return out


def _mr_entity_profile(d, ctx):
    rels = d.get("relationships") or {}
    rel_desc = ", ".join(f"{k}×{v}" for k, v in sorted(rels.items()))
    out = (f"{d.get('canonical_name')} ({d.get('entity_type')}).\n\n"
           f"संबंध: {sum(rels.values())} पुष्ट संबंध"
           + (f" — {rel_desc}" if rel_desc else "") + ". ")
    linked = d.get("linked_entities") or []
    if linked:
        out += "जोडलेले: " + ", ".join(linked) + ". "
    out += (f"\nकाल-रेखा: {d.get('event_count', 0)} नोंदवलेली घटना.\n"
            f"संरचित दावे: {d.get('claim_count', 0)}.\n"
            f"निष्कर्षांत: {d.get('finding_count', 0)}; गृहीतांत: "
            f"{d.get('hypothesis_count', 0)}. केस-ग्राफमध्ये नेटवर्क-कोटी: "
            f"{d.get('degree', 0)}.\n\nसर्व पुष्ट नोंदींवर आधारित — "
            "वागणाचा निकाल नाही.")
    return out


def _mr_relationship_path(d, ctx):
    a, b = _name(ctx, d.get("a")), _name(ctx, d.get("b"))
    chain = " → ".join(_name(ctx, i) for i in d.get("path") or [])
    out = (f"पुष्ट संबंध: {a} → {b}, {d.get('hops')} पायरी.\n\n"
           f"मार्ग: {chain}\n" + _fmt_edges(d.get("edges") or [], ctx) +
           "\n\nहा मार्ग फक्त पुष्ट संबंधांमधून तयार झाला आहे — नोंदवलेला "
           "सहसंबंध, वागणाचा आरोप नाही.")
    return out


def _mr_neighbourhood(d, ctx):
    nbs = d.get("neighbours") or []
    lines = "\n".join(f"  • {n['name']} ({n['entity_type']}) — "
                      f"{n['distance']} पायरी अंतरावर" for n in nbs[:15])
    more = (f"\n  • … आणि {len(nbs) - 15} इतर" if len(nbs) > 15 else "")
    return (f"{_name(ctx, d.get('node'))} पासून {d.get('hops')} पायऱ्यांच्या "
            f"आत, पुष्ट नेटवर्कमध्ये {len(nbs)} इतर एकक आहेत:\n" + lines + more +
            "\n\nसर्व नोंदवलेले संबंध पुष्ट नोंदी आहेत.")


def _mr_timeline(d, ctx):
    events = d.get("events") or []
    scope = _name(ctx, d.get("scope")) if d.get("scope") else "केस"
    lines = "\n".join(
        f"  • {e['timestamp']} — {e['type']}: {e['entity']} "
        f"({e['location']})" + (f" (पुरावा E{e['evidence_id']})"
                                if e.get("evidence_id") else "")
        for e in events[:15])
    more = (f"\n  … आणि {d.get('dated_count', 0) - 15} इतर"
            if d.get("dated_count", 0) > 15 else "")
    return (f"{scope} ची काल-रेखा: {d.get('event_count', 0)} घटना, "
            f"{d.get('dated_count', 0)} तारखीबद्ध.\n" + lines + more +
            "\n\nघटना पुष्ट नोंदी आहेत; क्रम नोंदवलेल्या तारखीनुसार.")


def _mr_contradictions(d, ctx):
    items = d.get("contradictions") or []
    lines = "\n".join(f"  • [{it.get('severity') or '—'}] {it['title']}"
                      for it in items)
    return (f"पुष्ट नोंदींमध्ये {len(items)} संभावित विसंगती आढळली:\n"
            + lines +
            "\n\nहे पुष्ट नोंदींवरील विश्लेषणात्मक चिन्हे आहेत — कोणतीही "
            "नोंद खो आहे याचा निकाल नाही. तपासणी अधिकाऱ्यांचे पुनरावलोकन "
            "अवश्य.")


def _mr_gaps(d, ctx):
    items = d.get("gaps") or []
    lines = "\n".join(f"  • [{it.get('gap_type') or '—'}] {it['title']}"
                      for it in items)
    return (f"{len(items)} तपासणी-अंतर (gap) चिन्हांकित:\n" + lines +
            "\n\nअंतर हे दर्शवतात की कुठे पुष्ट डेटा पुरेसा नाही — पुढील "
            "तपासणीचा संकेत, निष्कर्ष नाही.")


def _mr_hypotheses(d, ctx):
    items = d.get("hypotheses") or []
    lines = "\n".join(f"  • [{it.get('band') or '—'}] {it['title']} "
                      f"(स्कोर {it.get('score', 0):.2f})" for it in items)
    return (f"नोंदवलेली {len(items)} गृहीतके, निश्चित विश्लेषणात्मक स्कोरानुसार:\n"
            + lines +
            "\n\nस्कोर पुष्ट संकेतांवरून, दिसणारे घटक सहित गणलेले — "
            "दोषाची शक्यता नाही.")


def _mr_evidence_lookup(d, ctx):
    out = (f"पुरावा E{d.get('evidence_id')} — {d.get('type')}"
           + (f", स्रोत-संदर्भ “{d.get('source_reference')}”"
              if d.get("source_reference") else "") + ".\n"
           f"जोडलेले: {len(d.get('linked_relationships') or [])} पुष्ट संबंध, "
           f"{len(d.get('linked_events') or [])} काल-रेखा घटना, "
           f"{d.get('claims', 0)} संरचित दावे.\n"
           f"{len(d.get('cited_by_findings') or [])} निष्कर्ष आणि "
           f"{len(d.get('cited_by_hypotheses') or [])} गृहीतकांनी "
           "उद्धृत.")
    return out


def _mr_location_query(d, ctx):
    locs = d.get("locations") or []
    scope = _name(ctx, d.get("scope")) if d.get("scope") else "हा केस"
    lines = []
    for r in locs[:15]:
        line = f"  • {r['name']}"
        if r.get("latitude") is not None:
            line += f" ({r['latitude']:.4f}, {r['longitude']:.4f})"
        n = len(r.get("claims") or [])
        if n:
            line += f" — {n} संरचित दावे"
        lines.append(line)
    return (f"{scope} साठीची ठिकाणे: {len(locs)}.\n" + "\n".join(lines) +
            "\n\nठिकाणे पुष्ट नोंदी आहेत; निर्देशांक उपलब्ध असल्यास "
            "भौगोलिक विश्लेषण शक्य.")


def _mr_impact_simulation(d, ctx):
    removed = d.get("edges_removed") or []
    dd = d.get("diff") or {}
    isolated = d.get("newly_isolated_entities") or []
    if not removed:
        body = (f"E{d.get('evidence_id')} काढल्यास कोणताही पुष्ट संबंध "
                f"काढला जात नाही — प्रत्येक जोडी इतर पुराव्यांनी आधारित आहे.")
    else:
        body = (f"E{d.get('evidence_id')} काढल्यास {len(removed)} पुष्ट "
                f"किनारे/किनारे काढले जातील:\n" +
                "\n".join(f"  • {e.get('edge')} — {e.get('rule', '')}"
                          for e in removed[:8]) +
                (f"\n  … आणि {len(removed) - 8} इतर"
                 if len(removed) > 8 else ""))
        if isolated:
            body += ("\nनवे अलगाव: " +
                     ", ".join(i.get("name") or i.get("node", "?")
                               for i in isolated[:5]) + ".")
    body += (f" नेटवर्क-घटक: {dd.get('components_before')} → "
             f"{dd.get('components_after')}.")
    return ("नुसारा (काही बदललेले नाही): " + body +
            "\n\nहे स्मरणातील पुष्ट ग्राफवर what-if आहे; कोणतीही संचित "
            "नोंद तयार, बदलली किंवा काढलेली नाही.")


def _mr_entity_search(d, ctx):
    hits = d.get("hits") or []
    if not hits:
        return (f"या केसच्या पुष्ट नोंदींमध्ये “{d.get('query')}” शी जुळणारी "
                "कोणतीही नोंद नाही. शोध एकक, संबंध, पुरावा, घटना, ठिकाणे आणि "
                "दावे — फक्त पुष्ट डेटा — शोधतो.")
    lines = "\n".join(f"  • {h['label']} ({h['kind']})" for h in hits[:20])
    return (f"पुष्ट नोंदींमध्ये “{d.get('query')}” साठी "
            f"{d.get('hit_count', len(hits))} परिणाम:\n" + lines +
            "\n\nफक्त पुष्ट डेटावरील शोध.")


def _mr_unsupported(d, ctx):
    return ("मी यांमध्ये मदत करू शकतो: केस-सारांश, एखाद्या एककाचा "
            "प्रोफाइल, दोन व्यक्तींमधील संबंध, एखाद्याचे नेटवर्क, "
            "काल-रेखा, विसंगती, अंतर (gaps), गृहीतके, पुरावा-अभिक्रमण "
            "(E<id>), ठिकाणे, प्रभाव-नुसारा, आणि बहुभाषी शोध.")


# ------------------------------------------------------------------ Urdu
def _ur_case_overview(d, ctx):
    c = d.get("counts", {})
    case = d.get("case", {})
    out = (f"کیس {case.get('number')} — {case.get('title')} "
           f"(حالت: {case.get('status')}, اہمیت: {case.get('priority')}).\n\n"
           f"تصدیق شدہ ریکارڈ: {c.get('entities', 0)} ایککیٹیاں، "
           f"{c.get('relationships', 0)} تعلق، {c.get('evidence', 0)} ثبوت، "
           f"{c.get('timeline_events', 0)} ٹائم لائن واقعات، "
           f"{c.get('locations', 0)} مقامات، {c.get('claims', 0)} ڈھانچے دار دعوے.\n\n"
           f"تجزیہ: {c.get('findings', 0)} نتائج اور "
           f"{c.get('hypotheses', 0)} مفروضے درج ہیں. ")
    hf = d.get("high_findings") or []
    if hf:
        out += "اہم: " + "; ".join(f["title"] for f in hf) + ". "
    else:
        out += "ابھی کوئی اعلیٰ شدت والا نتیجہ درج نہیں. "
    out += ("یہ تصدیق شدہ ریکارڈ پر تجزیاتی نتائج ہیں — جائزے کا آغاز,"
            " نتیجہ نہیں۔")
    return out


def _ur_entity_profile(d, ctx):
    rels = d.get("relationships") or {}
    rel_desc = ", ".join(f"{k}×{v}" for k, v in sorted(rels.items()))
    out = (f"{d.get('canonical_name')} ({d.get('entity_type')}).\n\n"
           f"تعلق: {sum(rels.values())} تصدیق شدہ تعلق"
           + (f" — {rel_desc}" if rel_desc else "") + ". ")
    linked = d.get("linked_entities") or []
    if linked:
        out += "منصوبے شدہ: " + ", ".join(linked) + ". "
    out += (f"\nٹائم لائن: {d.get('event_count', 0)} درج شدہ واقعات.\n"
            f"ڈھانچے دار دعوے: {d.get('claim_count', 0)}.\n"
            f"نتائج میں: {d.get('finding_count', 0)}; مفروضوں میں: "
            f"{d.get('hypothesis_count', 0)}. کیس گراف میں نیٹ ورک ڈگری: "
            f"{d.get('degree', 0)}.\n\nتمام تصدیق شدہ ریکارڈ پر مبنی — "
            "رازداری کا فیصلہ نہیں۔")
    return out


def _ur_relationship_path(d, ctx):
    a, b = _name(ctx, d.get("a")), _name(ctx, d.get("b"))
    chain = " ← ".join(_name(ctx, i) for i in reversed(d.get("path") or []))
    out = (f"تصدیق شدہ تعلق: {a} ← {b}, {d.get('hops')} قدم.\n\n"
           f"راستہ: {chain}\n" + _fmt_edges(d.get("edges") or [], ctx) +
           "\n\nیہ راستہ صرف تصدیق شدہ تعلقات سے بنایا گیا ہے — درج شدہ "
           "رابطہ، رازداری کا الزام نہیں۔")
    return out


def _ur_neighbourhood(d, ctx):
    nbs = d.get("neighbours") or []
    lines = "\n".join(f"  • {n['name']} ({n['entity_type']}) — "
                      f"{n['distance']} قدم دور" for n in nbs[:15])
    more = (f"\n  • … اور {len(nbs) - 15} دیگر" if len(nbs) > 15 else "")
    return (f"{_name(ctx, d.get('node'))} سے {d.get('hops')} قدموں کے اندر، "
            f"تصدیق شدہ نیٹ ورک میں {len(nbs)} دیگر ایککیٹیاں ہیں:\n" + lines + more +
            "\n\nتمام درج شدہ تعلق تصدیق شدہ ریکارڈ ہیں۔")


def _ur_timeline(d, ctx):
    events = d.get("events") or []
    scope = _name(ctx, d.get("scope")) if d.get("scope") else "کیس"
    lines = "\n".join(
        f"  • {e['timestamp']} — {e['type']}: {e['entity']} "
        f"({e['location']})" + (f" (ثبوت E{e['evidence_id']})"
                                if e.get("evidence_id") else "")
        for e in events[:15])
    more = (f"\n  … اور {d.get('dated_count', 0) - 15} دیگر"
            if d.get("dated_count", 0) > 15 else "")
    return (f"{scope} کی ٹائم لائن: {d.get('event_count', 0)} واقعات، "
            f"{d.get('dated_count', 0)} تاریخ یافتہ.\n" + lines + more +
            "\n\nواقعات تصدیق شدہ ریکارڈ ہیں؛ ترتیب درج شدہ وقت کے مطابق۔")


def _ur_contradictions(d, ctx):
    items = d.get("contradictions") or []
    lines = "\n".join(f"  • [{it.get('severity') or '—'}] {it['title']}"
                      for it in items)
    return (f"تصدیق شدہ ریکارڈ میں {len(items)} ممکنہ تضاد دریافت ہوا:\n"
            + lines +
            "\n\nیہ تصدیق شدہ ریکارڈ پر تجزیاتی نشانات ہیں — کسی ریکارڈ کے"
            " جھوٹے ہونے کا فیصلہ نہیں۔ تفتیشی افسر کی جانچ ضروری۔")


def _ur_gaps(d, ctx):
    items = d.get("gaps") or []
    lines = "\n".join(f"  • [{it.get('gap_type') or '—'}] {it['title']}"
                      for it in items)
    return (f"{len(items)} تحقیقی خلا درج:\n" + lines +
            "\n\nخلا بتاتے ہیں کہ کہاں تصدیق شدہ ڈیٹا ناکافی ہے — اگلے"
            " جائزے کی نشانی، نتیجہ نہیں۔")


def _ur_hypotheses(d, ctx):
    items = d.get("hypotheses") or []
    lines = "\n".join(f"  • [{it.get('band') or '—'}] {it['title']} "
                      f"(اسکور {it.get('score', 0):.2f})" for it in items)
    return (f"درج شدہ {len(items)} مفروضے، طے شدہ تجزیاتی اسکور کے مطابق:\n"
            + lines +
            "\n\nاسکور تصدیق شدہ اشاروں سے، نظر آنے والے اجزاء کے ساتھ"
            " گنے گئے — قصور کی امکانیت نہیں۔")


def _ur_evidence_lookup(d, ctx):
    out = (f"ثبوت E{d.get('evidence_id')} — {d.get('type')}"
           + (f"، ذریعہ حوالہ “{d.get('source_reference')}”"
              if d.get("source_reference") else "") + ".\n"
           f"منصوبے شدہ: {len(d.get('linked_relationships') or [])} تصدیق شدہ تعلق، "
           f"{len(d.get('linked_events') or [])} ٹائم لائن واقعات، "
           f"{d.get('claims', 0)} ڈھانچے دار دعوے.\n"
           f"{len(d.get('cited_by_findings') or [])} نتائج اور "
           f"{len(d.get('cited_by_hypotheses') or [])} مفروضوں سے"
           " حوالہ دیا گیا۔")
    return out


def _ur_location_query(d, ctx):
    locs = d.get("locations") or []
    scope = _name(ctx, d.get("scope")) if d.get("scope") else "اس کیس"
    lines = []
    for r in locs[:15]:
        line = f"  • {r['name']}"
        if r.get("latitude") is not None:
            line += f" ({r['latitude']:.4f}, {r['longitude']:.4f})"
        n = len(r.get("claims") or [])
        if n:
            line += f" — {n} ڈھانچے دار دعوے"
        lines.append(line)
    return (f"{scope} کے مقامات: {len(locs)}.\n" + "\n".join(lines) +
            "\n\nمقامات تصدیق شدہ ریکارڈ ہیں؛ اگر کوآرڈینیٹ موجود ہوں تو"
            " جغرافیائی تجزیہ ممکن ہے۔")


def _ur_impact_simulation(d, ctx):
    removed = d.get("edges_removed") or []
    dd = d.get("diff") or {}
    isolated = d.get("newly_isolated_entities") or []
    if not removed:
        body = (f"E{d.get('evidence_id')} ہٹانے سے کوئی تصدیق شدہ تعلق"
                f" نہیں ہٹتا — ہر جوڑی دیگر ثبوت سے معاون ہے۔")
    else:
        body = (f"E{d.get('evidence_id')} ہٹانے سے {len(removed)} تصدیق شدہ"
                f" کنارے ہٹیں گے:\n" +
                "\n".join(f"  • {e.get('edge')} — {e.get('rule', '')}"
                          for e in removed[:8]) +
                (f"\n  … اور {len(removed) - 8} دیگر"
                 if len(removed) > 8 else ""))
        if isolated:
            body += ("\nنئے جدا: " +
                     ", ".join(i.get("name") or i.get("node", "?")
                               for i in isolated[:5]) + ".")
    body += (f" نیٹ ورک اجزاء: {dd.get('components_before')} → "
             f"{dd.get('components_after')}.")
    return ("محاکما (کچھ تبدیل نہیں ہوا): " + body +
            "\n\nیہ یاداشت کے تصدیق شدہ گراف پر what-if ہے; کوئی محفوظ"
            " ریکارڈ بنایا، تبدیل یا ہٹایا نہیں گیا۔")


def _ur_entity_search(d, ctx):
    hits = d.get("hits") or []
    if not hits:
        return (f"اس کیس کے تصدیق شدہ ریکارڈ میں “{d.get('query')}” سے"
                " مماثل کوئی ریکارڈ نہیں۔ تلاش ایککیٹیاں، تعلق، ثبوت، واقعات،"
                " مقامات اور دعوے — صرف تصدیق شدہ ڈیٹا — دھوڑتی ہے۔")
    lines = "\n".join(f"  • {h['label']} ({h['kind']})" for h in hits[:20])
    return (f"تصدیق شدہ ریکارڈ میں “{d.get('query')}” کے لیے "
            f"{d.get('hit_count', len(hits))} نتائج:\n" + lines +
            "\n\nصرف تصدیق شدہ ڈیٹا پر تلاش۔")


def _ur_unsupported(d, ctx):
    return ("میں ان میں مدد کر سکتا ہوں: کیس خلاصہ، کسی ایککیٹی کا"
            " پروفائل، دو لوگوں کے درمیان تعلق، کسی کا نیٹ ورک،"
            " ٹائم لائن، تضاد، خلا (gaps)، مفروضے، ثبوت تلاش"
            " (E<id>)، مقامات، اثرِ محاکما، اور کثیر لسانی تلاش۔")


# ------------------------------------------------------------------ dispatch
_TEMPLATES: dict[str, dict[str, Callable[[dict, object], str]]] = {
    "hi": {
        "case_overview": _hi_case_overview, "entity_profile": _hi_entity_profile,
        "relationship_path": _hi_relationship_path,
        "neighbourhood": _hi_neighbourhood, "timeline": _hi_timeline,
        "contradictions": _hi_contradictions, "gaps": _hi_gaps,
        "hypotheses": _hi_hypotheses, "evidence_lookup": _hi_evidence_lookup,
        "location_query": _hi_location_query,
        "impact_simulation": _hi_impact_simulation,
        "entity_search": _hi_entity_search, "unsupported": _hi_unsupported,
    },
    "mr": {
        "case_overview": _mr_case_overview, "entity_profile": _mr_entity_profile,
        "relationship_path": _mr_relationship_path,
        "neighbourhood": _mr_neighbourhood, "timeline": _mr_timeline,
        "contradictions": _mr_contradictions, "gaps": _mr_gaps,
        "hypotheses": _mr_hypotheses, "evidence_lookup": _mr_evidence_lookup,
        "location_query": _mr_location_query,
        "impact_simulation": _mr_impact_simulation,
        "entity_search": _mr_entity_search, "unsupported": _mr_unsupported,
    },
    "ur": {
        "case_overview": _ur_case_overview, "entity_profile": _ur_entity_profile,
        "relationship_path": _ur_relationship_path,
        "neighbourhood": _ur_neighbourhood, "timeline": _ur_timeline,
        "contradictions": _ur_contradictions, "gaps": _ur_gaps,
        "hypotheses": _ur_hypotheses, "evidence_lookup": _ur_evidence_lookup,
        "location_query": _ur_location_query,
        "impact_simulation": _ur_impact_simulation,
        "entity_search": _ur_entity_search, "unsupported": _ur_unsupported,
    },
}


def render_answer(intent: str, data: dict, lang: str, ctx) -> str | None:
    """Re-render a deterministic answer's prose in ``lang`` from its
    structured ``data``. Returns None when the intent has no template for
    that language (the provider then keeps the English text and reports
    answer_language="en" honestly)."""
    fn = _TEMPLATES.get(lang, {}).get(intent)
    if fn is None:
        return None
    try:
        return fn(data, ctx)
    except Exception:  # noqa: BLE001 — a template bug must never break the
        # answer: fall back to the (validated) English text.
        return None
