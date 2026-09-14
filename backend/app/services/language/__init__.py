"""Multilingual support (stage 5) — language detection & transliteration.

Pure, deterministic, dependency-free. Supported languages:

* ``en``  English (Latin script)
* ``hi``  Hindi (Devanagari script)
* ``mr``  Marathi (Devanagari script)
* ``ur``  Urdu (Arabic-script / Perso-Arabic)

Nothing here writes to the database, calls a network service or claims a
language that the detector cannot actually distinguish. When the evidence
is thin the confidence is low and the signal list says exactly why — the
UI and the API surface that uncertainty instead of hiding it.
"""

from .detect import (SUPPORTED_LANGUAGES, LanguageInfo, detect_language)  # noqa: F401
from .transliterate import (normalize_for_match, strip_diacritics,  # noqa: F401
                            transliterate)
