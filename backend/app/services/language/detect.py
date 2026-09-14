"""Deterministic language detection for en / hi / mr / ur.

Method (documented, no libraries, no network):

1. **Script census** — count Devanagari, Perso-Arabic and Latin letters;
   the dominant script decides the candidate language family.
2. **Lexicon disambiguation** — within the dominant script, function
   words and well-known proper nouns that differ between the languages are
   counted (distinct words present, not occurrences):
   * Devanagari -> Hindi vs Marathi via their distinct function words
     (है/क्या/और/में vs आढळून/आणि/झाले/येथे/…).
   * Perso-Arabic -> Urdu via its function words (ہے/کا/اور/نہیں/تھا…).
   * Latin -> English via a small function-word set.
3. **Confidence** is computed from the evidence, not asserted:
   a clear lexicon win scores 0.6–0.95; a thin or ambiguous sample scores
   low (0.3–0.5) and says so in ``signals``. A tie in Devanagari resolves
   to ``mr`` (this deployment's region default) with low confidence.

Unknown/undetectable text returns ``None`` — callers then fall back to the
existing English rule-based path and leave the document language unset.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

SUPPORTED_LANGUAGES = ("en", "hi", "mr", "ur")

LANGUAGE_NAMES = {
    "en": "English",
    "hi": "Hindi",
    "mr": "Marathi",
    "ur": "Urdu",
}

# -- script ranges -----------------------------------------------------------
_RE_DEVANAGARI = re.compile(r"[\u0900-\u097F]")
_RE_ARABIC = re.compile(r"[\u0600-\u06FF\u0750-\u077F]")
_RE_LATIN = re.compile(r"[A-Za-z]")

# Distinct function words / landmarks (lowercase, per-script). A word counts
# once per document, not per occurrence.
_HINDI_WORDS = frozenset("""
है का की के और क्या कि में पर से रहा रही थी था किया जब फिर नहीं
तुम आप मैं दिल्ली भारत यह वह इस उस तो भी कहते कहती बताया खुद
कोई हर बाद पहले वाला सी लेकिन हाल अपने नाम दिन
""".split())

_MRATHI_WORDS = frozenset("""
आणि आहे नाही होता होती होत्या झाले करतो करते या त्या हे ही ह्या
पुणे महाराष्ट्र येथे काय आपण मी तुम्ही आमचा आमची सांग दिसून
आढळून गेला आला आली त्याला त्याची वरील मध्ये पासून नाते सोबत
म्हणून कारण पण किंवा वृत्त अहवाल तिथी दुसरा
""".split())

_URDU_WORDS = frozenset("""
ہے کا کی کے اور نہیں تھا تھی اس وہ یہ اسے سے پر میں جو تم آپ
لاہور کراچی حیدرآباد بھارت پاکستان ہندوستان دلہی پونہ ممبئی
دیکھا نظر ملا رکھ کہا کیا ہوا زیر تاریخ وقت رابطہ فون ریکارڈ
""".split())

_ENGLISH_WORDS = frozenset("""
the and at in on was were from by with observed report reports records
called vehicle location date time case police station person name phone
near arrived arrived. registered transferred linked
""".split())

# Public stopword lexicons — the multilingual extractor uses these to keep
# the unknown-name pattern from treating function words as person names.
LEXICON_STOPWORDS: dict[str, frozenset] = {
    "hi": _HINDI_WORDS,
    "mr": _MRATHI_WORDS,
    "ur": _URDU_WORDS,
}

# Extended name-filter stopwords (superset of the detection lexicons):
# verb/adverb/noun forms that a 2-word window must never treat as a person
# name. Detection scoring is unaffected (it uses the lexicons above).
NAME_STOPWORDS: dict[str, frozenset] = {
    "hi": _HINDI_WORDS | frozenset("""
    देखा देखी देखा। गया गयी गए हुई हुई। हुआ हुए किया की के से को पर
    में बात बातचीत संवाद कॉल रिपोर्ट एक इस उस यह वह ही भी तो
    """.split()),
    "mr": _MRATHI_WORDS | frozenset("""
    झाला झाली झाले झालेले झाल्या दिसून आढळून आला आली आले गेला
    गेली गेले संवाद संपर्क बात कॉल फोन अहवाल एक हा ही हे त्या या
    यांचा त्यांचा
    """.split()),
    "ur": _URDU_WORDS | frozenset("""
    ہوا ہوئی ہويا دیکھا دیکھی دیکھنے ملا ملے ملاقات رابطہ بات مکالمہ
    کال کیا کیہ ہے تھا تھی نہیں کو نے کا کی کے اسے ہم تم آپ جس کیا
    ایک یہ وہ اس سے پر میں جو اور تو بھی اب پھر سب کچھ کر رہے
    """.split()),
}


@dataclass(frozen=True)
class LanguageInfo:
    """Result of detection. ``code`` is one of SUPPORTED_LANGUAGES (or
    None when undetectable); ``confidence`` is 0..1 and ``signals`` lists
    the concrete evidence the decision was based on."""

    code: str | None
    name: str | None
    script: str
    confidence: float
    signals: list[str] = field(default_factory=list)


_WORD_RE = re.compile(r"[\u0900-\u097F]+|[\u0600-\u06FF]+|[A-Za-z']+")


def _text_words(text: str) -> set[str]:
    """Script-aware word set (whitespace + script danda are separators).

    Word-level (not substring) matching: "या" must not count inside "गया",
    and a trailing danda does not corrupt the word ("है।" -> "है").
    """
    text = (text.replace("\u0964", " ").replace("\u0965", " ")
             .replace("\u06D4", " ").replace("\u061F", " ")
             .replace("\u060C", " "))
    return set(_WORD_RE.findall(text.casefold()))


def _words_present(text: str, lexicon: frozenset) -> list[str]:
    words = _text_words(text)
    return sorted(w for w in lexicon if w in words)


def detect_language(text: str) -> LanguageInfo | None:
    """Detect the dominant language of ``text`` (en/hi/mr/ur) or None."""
    if not text or not text.strip():
        return None

    dev = len(_RE_DEVANAGARI.findall(text))
    ara = len(_RE_ARABIC.findall(text))
    lat = len(_RE_LATIN.findall(text))
    total = dev + ara + lat
    if total == 0:
        return None

    dominant = max((("devanagari", dev), ("arabic", ara), ("latin", lat)),
                   key=lambda x: x[1])
    script, count = dominant
    ratio = count / total

    if script == "devanagari":
        hi = _words_present(text, _HINDI_WORDS)
        mr = _words_present(text, _MRATHI_WORDS)
        signals = [f"dominant script devanagari ({count}/{total} chars, "
                   f"{ratio:.0%})"]
        signals += [f"hindi lexicon hits: {', '.join(hi[:8])}" if hi
                    else "no hindi lexicon hits"]
        signals += [f"marathi lexicon hits: {', '.join(mr[:8])}" if mr
                    else "no marathi lexicon hits"]
        if len(hi) > len(mr):
            code, winner = "hi", hi
        elif len(mr) > len(hi):
            code, winner = "mr", mr
        else:
            # Tie (including 0-0): region default, flagged as weak evidence.
            code = "mr"
            signals.append("hi/mr tie — resolved to mr (deployment region "
                           "default); confidence is low by design")
            winner = mr
        diff = abs(len(hi) - len(mr))
        conf = 0.60 + 0.07 * diff
        conf = min(conf, 0.95)
        if diff == 0:
            conf = 0.35 if not winner else 0.50
        return LanguageInfo(code=code, name=LANGUAGE_NAMES[code],
                            script="devanagari", confidence=round(conf, 3),
                            signals=signals)

    if script == "arabic":
        ur = _words_present(text, _URDU_WORDS)
        signals = [f"dominant script perso-arabic ({count}/{total} chars, "
                   f"{ratio:.0%})"]
        signals += [f"urdu lexicon hits: {', '.join(ur[:8])}" if ur
                    else "no urdu lexicon hits"]
        extra = []
        if len(ur) >= 2:
            conf = min(0.60 + 0.05 * len(ur), 0.92)
        elif len(ur) == 1:
            conf, extra = 0.40, ["only one urdu lexicon hit — low confidence"]
        else:
            conf, extra = 0.30, ["arabic script without urdu lexicon hits — "
                                 "may be another arabic-script language"]
        return LanguageInfo(code="ur", name=LANGUAGE_NAMES["ur"],
                            script="arabic", confidence=round(conf, 3),
                            signals=signals + extra)

    # latin
    en = _words_present(text, _ENGLISH_WORDS)
    signals = [f"dominant script latin ({count}/{total} chars, {ratio:.0%})"]
    signals += [f"english lexicon hits: {', '.join(en[:8])}" if en
                else "no english lexicon hits"]
    if len(en) >= 3:
        conf = min(0.75 + 0.04 * len(en), 0.95)
    elif len(en) == 2:
        conf = 0.60
    elif len(en) == 1:
        conf = 0.45
    else:
        return LanguageInfo(code=None, name=None, script="latin",
                            confidence=0.0,
                            signals=signals + ["undetermined — not clearly "
                                               "english; left unclassified"])
    return LanguageInfo(code="en", name=LANGUAGE_NAMES["en"], script="latin",
                        confidence=round(conf, 3), signals=signals)


def detect_question_language(text: str) -> str:
    """Script-aware language for an *investigator's question*.

    ``detect_language`` weighs character counts, so a question that names
    entities in Latin script ("Rajesh Kumar आणि Vikram Rao जोडलेले
    का आहेत?") can tip to 'en' even though the investigator is writing
    in Marathi. For questions the script of the non-Latin text is the
    intent signal: any Devanagari/Arabic in the question means the
    question is in that script's language (Latin fragments are names,
    numbers or loanwords). hi vs mr still uses the lexicons on the
    Devanagari words only. Pure-Latin text -> 'en' (the canonical layer).
    """
    if not text or not text.strip():
        return "en"
    if _RE_DEVANAGARI.search(text):
        # word runs (not single chars — _RE_DEVANAGARI is a char class)
        dev = " ".join(re.findall(r"[\u0900-\u097F]+", text))
        hi = _words_present(dev, _HINDI_WORDS)
        mr = _words_present(dev, _MRATHI_WORDS)
        return "hi" if len(hi) > len(mr) else "mr"
    if _RE_ARABIC.search(text):
        return "ur"
    return "en"
