"""Deterministic transliteration: Devanagari (hi/mr) and Perso-Arabic (ur)
-> simplified Latin, plus a script-aware name normalizer.

The tables are *simplified ITRANS-style*: they approximate pronunciation
closely enough for name matching, not for typesetting. Documented
simplifications:

* retroflex and dental consonants collapse (ट and त -> "t");
* the nukta series is folded into its base letter;
* Urdu vocalic alef/waw/yeh are resolved by word position (initial ->
  consonantal a/w/y, otherwise vocalic u/i);
* diacritics are stripped after transliteration, so "Rajesh Kumar",
  "rajesh kumar" and "राजेश कुमार" all normalize to "rajesh kumar".

``normalize_for_match`` is the shared matching key used by multilingual
entity resolution and search. It is a pure function: same input, same
output, no data lookup.
"""

from __future__ import annotations

import re
import unicodedata

# -- Devanagari ---------------------------------------------------------------
# Multi-char entries (conjuncts) are tried before single-char ones.
_DEVANAGARI_TABLE: list[tuple[str, str]] = [
    ("\u0915\u094D\u0937", "ksh"),   # क्ष
    ("\u091C\u094D\u091E", "jn"),    # ज्ञ
    ("\u0930\u0947", "re"), ("\u0930\u094B", "ro"), ("\u0930\u0941", "ru"),
    ("\u0930\u0942", "ru"),
    ("\u093D", "sh"),   # ऽ avagraha (rare)
    ("\u0905", "a"), ("\u0906", "aa"), ("\u0907", "i"), ("\u0908", "ee"),
    ("\u0909", "u"), ("\u090A", "oo"), ("\u090B", "ri"), ("\u090F", "e"),
    ("\u0910", "ai"), ("\u0913", "o"), ("\u0914", "au"),
    ("\u093E", "aa"), ("\u093F", "i"), ("\u0940", "ee"), ("\u0941", "u"),
    ("\u0942", "oo"), ("\u0943", "ri"), ("\u0944", "ri"), ("\u0947", "e"),
    ("\u0948", "ai"), ("\u094B", "o"), ("\u094C", "au"),
    ("\u0901", "n"), ("\u0902", "n"), ("\u0903", "h"), ("\u093C", ""),
    ("\u094D", ""),    # halant / virama (consonant cluster marker)
    ("\u0915", "k"), ("\u0916", "kh"), ("\u0917", "g"), ("\u0918", "gh"),
    ("\u0919", "ng"), ("\u091A", "ch"), ("\u091B", "chh"), ("\u091C", "j"),
    ("\u091D", "jh"), ("\u091E", "ny"), ("\u091F", "t"), ("\u0920", "th"),
    ("\u0921", "d"), ("\u0922", "dh"), ("\u0923", "n"), ("\u0924", "t"),
    ("\u0925", "th"), ("\u0926", "d"), ("\u0927", "dh"), ("\u0928", "n"),
    ("\u092A", "p"), ("\u092B", "ph"), ("\u092C", "b"), ("\u092D", "bh"),
    ("\u092E", "m"), ("\u092F", "y"), ("\u0930", "r"), ("\u0932", "l"),
    ("\u0935", "v"), ("\u0936", "sh"), ("\u0937", "sh"), ("\u0938", "s"),
    ("\u0939", "h"),
]
_DEV_SINGLE = {k: v for k, v in _DEVANAGARI_TABLE if len(k) == 1}
_DEV_MULTI = [(k, v) for k, v in _DEVANAGARI_TABLE if len(k) > 1]

# -- Perso-Arabic (Urdu) -------------------------------------------------------
_ARABIC_TABLE: dict[str, str] = {
    "\u0621": "",    # hamza
    "\u0622": "a",   # alef with madda
    "\u0623": "a",   # alef with hamza above
    "\u0624": "u",   # waw with hamza
    "\u0625": "a",   # alef with hamza below
    "\u0626": "i",   # yeh with hamza
    "\u0628": "b",   # be
    "\u0629": "h",   # teh marbuta
    "\u062D": "h",   # heh (Arabic, not Persian)
    "\u0637": "t",   # tah
    "\u0640": "",    # tatweel
    "\u0644": "l",   # lam
    "\u0645": "m",   # meem
    "\u064B": "",    # fathatan
    "\u064C": "",    # dhammatan
    "\u064D": "",    # kasratan
    "\u0653": "",    # wasla
    "\u0656": "",    # subscript alef
    "\u0670": "",    # superscript alef
    "\u067E": "p",   # pe
    "\u062A": "t",   # te
    "\u0679": "tt",  # tet
    "\u062B": "th",  # the
    "\u062C": "j",   # jeem
    "\u0686": "ch",  # che
    "\u062E": "kh",  # kha
    "\u062F": "d",   # dal
    "\u068A": "dd",  # do
    "\u0630": "dh",  # dhal
    "\u0631": "r",   # re
    "\u0632": "z",   # ze
    "\u0633": "s",   # se
    "\u0634": "sh",  # sheen
    "\u0635": "s",   # sad
    "\u0636": "z",   # dad
    "\u067F": "t",   # tatweel-t
    "\u0638": "z",   # zha
    "\u0639": "a",   # ayn (approximated)
    "\u063A": "gh",  # ghain
    "\u0641": "f",   # fe
    "\u0642": "q",   # qaf
    "\u0643": "k",   # kaf
    "\u06AF": "g",   # gaf
    "\u0646": "n",   # noon
    "\u064E": "",    # fathah
    "\u064F": "u",   # dammah
    "\u0650": "i",   # kasra
    "\u0651": "",    # shadda
    "\u0652": "",    # sukun
    "\u0654": "",    # madda
    "\u0671": "i",   # alef maqsura
    "\u0681": "h",   # heh with madda
    "\u06BE": "e",   # yeh with small v
    "\u06CC": "i",   # yeh
    "\u06D2": "e",   # yeh (Urdu ے)
    "\u0698": "zh",  # jeh with underline
    "\u06A9": "k",   # kaf (kashida form, common in Urdu text)
    "\u06BA": "rr",  # reh with small v
    "\u06C1": "h",   # heh
    "\u06C3": "a",   # dagger alef
}

_DIGITS = {c: str(i) for i, c in
           enumerate("0123456789\u0966\u0967\u0968\u0969\u096A\u096B"
                     "\u096C\u096D\u096E\u096F\u0660\u0661\u0662\u0663"
                     "\u0664\u0665\u0666\u0667\u0668\u0669")}
_PUNCT = ".,;:!?\u2026\u060C\u061F"


def _devanagari_pass(text: str) -> str:
    """Per-character Devanagari mapping with conjunct + inherent-vowel
    handling: a consonant followed by another consonant (no halant between)
    carries the inherent 'a' (विक्रम -> "vikram"); a consonant at end of
    word or before a dependent vowel / halant / anusvara does not."""
    dependent = set("ािीुूृेैोौंॅ")
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if "\u0900" <= ch <= "\u097F":
            done = False
            for key, value in _DEV_MULTI:
                if text.startswith(key, i):
                    out.append(value)
                    i += len(key)
                    done = True
                    break
            if not done:
                value = _DEV_SINGLE.get(ch, ch)
                out.append(value)
                is_consonant = "\u0915" <= ch <= "\u0939"
                if is_consonant:
                    nxt = text[i + 1] if i + 1 < n else None
                    if (nxt is not None and "\u0915" <= nxt <= "\u0939"):
                        out.append("a")  # inherent vowel (क+र cluster)
                i += 1
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def _arabic_pass(text: str) -> str:
    out: list[str] = []
    prev_is_word_boundary = True
    for ch in text:
        if "\u0600" <= ch <= "\u06FF":
            if ch == "\u0627":          # alef: initial a, medial vowel
                value = "a" if prev_is_word_boundary else ""
            elif ch == "\u0648":        # waw
                value = "w" if prev_is_word_boundary else "u"
            elif ch == "\u06CC":        # yeh
                value = "y" if prev_is_word_boundary else "i"
            else:
                value = _ARABIC_TABLE.get(ch, "")
            out.append(value)
            prev_is_word_boundary = (value == "")
            continue
        if ch.isspace() or ch in _PUNCT:
            out.append(" ")
            prev_is_word_boundary = True
            continue
        out.append(ch)
        prev_is_word_boundary = False
    return "".join(out)


def transliterate(text: str) -> str:
    """Transliterate Devanagari / Perso-Arabic text to simplified Latin.

    Latin text passes through unchanged; non-Latin digits become ASCII.
    """
    if not text:
        return ""
    if any("\u0900" <= c <= "\u097F" for c in text):
        text = _devanagari_pass(text)
    if any("\u0600" <= c <= "\u06FF" for c in text):
        text = _arabic_pass(text)
    return "".join(_DIGITS.get(c, c) for c in text)


def strip_diacritics(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def normalize_for_match(name: str) -> str:
    """Script-aware canonical matching key.

    "Rajesh Kumar", "RAJESH KUMAR", "rajesh kumar", "राजेश कुमार" and
    "Pune" / "पुणे" all normalize to their simple Latin form. Doubled
    vowels are collapsed (aa->a, ee->e, oo->o) — this is a matching key,
    not a spelling, and the collapsing is what makes "राजेश कुमार"
    normalize to exactly "rajesh kumar".
    """
    text = transliterate(name or "")
    text = strip_diacritics(text)
    text = text.casefold()
    text = re.sub(r"[^0-9a-z]+", " ", text)
    text = re.sub(r"aa", "a", text)
    text = re.sub(r"ee", "e", text)
    text = re.sub(r"oo", "o", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()
