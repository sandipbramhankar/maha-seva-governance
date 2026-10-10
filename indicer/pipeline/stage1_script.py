"""
Stage 1 — Script Normalisation
===============================
Detects the script of an input name string and, if Devanagari (or other
Indic script supported by indic_transliteration), transliterates it to
Harvard-Kyoto (HK) romanisation.

Output tuple: (romanised_string, detected_script)
  detected_script ∈ {'devanagari', 'latin', 'unknown'}
"""

import unicodedata
import re

try:
    from indic_transliteration import sanscript
    from indic_transliteration.sanscript import transliterate
    _TRANSLITERATION_AVAILABLE = True
except ImportError:
    _TRANSLITERATION_AVAILABLE = False
    import warnings
    warnings.warn(
        "indic_transliteration not installed; Devanagari input will be "
        "returned as-is. Run: pip install indic-transliteration",
        ImportWarning,
        stacklevel=2,
    )

# Unicode block ranges
_DEVANAGARI_RANGE = (0x0900, 0x097F)
_EXTENDED_DEVA_RANGE = (0x0900, 0x0DFF)  # covers most Indic scripts


def _char_is_devanagari(ch: str) -> bool:
    cp = ord(ch)
    return _DEVANAGARI_RANGE[0] <= cp <= _DEVANAGARI_RANGE[1]


def _char_is_indic(ch: str) -> bool:
    cp = ord(ch)
    return _EXTENDED_DEVA_RANGE[0] <= cp <= _EXTENDED_DEVA_RANGE[1]


def detect_script(name: str) -> str:
    """
    Returns 'devanagari', 'latin', or 'unknown'.
    Decision is based on the majority of alphabetic characters.
    """
    deva_count = 0
    latin_count = 0
    for ch in name:
        if _char_is_devanagari(ch):
            deva_count += 1
        elif ch.isalpha() and ord(ch) < 0x0250:  # basic Latin + IPA extension
            latin_count += 1

    if deva_count == 0 and latin_count == 0:
        return "unknown"
    return "devanagari" if deva_count >= latin_count else "latin"


def _transliterate_devanagari(name: str) -> str:
    """Transliterate Devanagari to HK romanisation."""
    if not _TRANSLITERATION_AVAILABLE:
        return name  # graceful degradation
    try:
        return transliterate(name, sanscript.DEVANAGARI, sanscript.HK)
    except Exception:
        return name


def normalise_script(name: str) -> tuple[str, str]:
    """
    Stage 1 entry point.

    Parameters
    ----------
    name : str
        Raw name string from any repository field.

    Returns
    -------
    (romanised, script) : tuple[str, str]
        romanised — HK-romanised or original Latin string (lowercased).
        script    — 'devanagari' | 'latin' | 'unknown'
    """
    if not name or not name.strip():
        return ("", "unknown")

    name = name.strip()
    script = detect_script(name)

    if script == "devanagari":
        romanised = _transliterate_devanagari(name)
        # HK output may contain digits (svara numerals); strip them
        romanised = re.sub(r"[0-9]", "", romanised)
        return (romanised.strip(), "devanagari")
    else:
        # For Latin input: keep letters, hyphens, spaces, periods
        cleaned = re.sub(r"[^A-Za-z\s.\-]", "", name)
        return (cleaned.strip(), script)


# ---------------------------------------------------------------------------
# Quick self-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    tests = [
        ("संदीप प्रभु ब्राह्मणकर", "devanagari"),
        ("Sandip Prabhu Bramhankar", "latin"),
        ("Dr. Anita S. Kumar", "latin"),
        ("", "unknown"),
    ]
    for inp, expected_script in tests:
        rom, scr = normalise_script(inp)
        status = "OK" if scr == expected_script else "FAIL"
        print(f"[{status}] '{inp}' → '{rom}' (script={scr})")