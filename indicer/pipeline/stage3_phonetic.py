"""
Stage 3 — Indic Phonetic Encoding  (novel patent contribution)
===============================================================
Maps each Component produced by Stage 2 to a canonical symbol sequence
drawn from 12 consonant equivalence classes.

CONSONANT EQUIVALENCE CLASSES
------------------------------
  K  — velar stops + affricates:  k kh g gh c ch j jh
  T  — dental/retroflex stops:    t th d dh T Th D Dh
  P  — labial stops:              p ph b bh
  S  — sibilants:                 s z S sh
  M  — bilabial nasal:            m
  N  — other nasals:              n N ñ
  R  — rhotics:                   r R
  L  — laterals:                  l L
  V  — approximant:               v w
  Y  — palatal approx:            y
  H  — glottal:                   h
  X  — (vowels) — deleted

PROCESSING RULES (applied in order after mapping)
--------------------------------------------------
  (a) Scan input left-to-right with longest-match on digraph table.
  (b) Map each grapheme to its class symbol (vowels → delete / skip).
  (c) NASAL ASSIMILATION: any M or N immediately before a plosive class
      symbol (K, T, P) is normalised to N.
  (d) NON-INITIAL CLASS H DELETION: any H symbol that is NOT the very
      first symbol in the sequence is deleted.
  (e) ADJACENT DUPLICATE COLLAPSE: collapse runs of identical symbols
      to a single symbol (e.g. NN → N).

KEY RESULT
----------
  Bramhankar  → P-R-M-N-K-R
  Brahmankar  → P-R-M-N-K-R   (h is non-initial → deleted)
  Bramhanakar → P-R-M-N-K-R
  Bramhamkar  → P-R-M-N-K-R   (m→M nasal before K)
"""

from __future__ import annotations
from typing import List, Sequence
from indicer.pipeline.stage2_structural import Component

# ---------------------------------------------------------------------------
# Digraph table (order matters — scan longest first within a starting letter)
# Each entry: (grapheme_string, class_symbol)
# Graphemes are in Harvard-Kyoto (HK) romanisation; case-sensitive for
# retroflex capitals (T Th D Dh N R L S).
# ---------------------------------------------------------------------------
_DIGRAPH_TABLE: List[tuple[str, str]] = [
    # ---- Class K (velars + palatals) ----
    ("kh", "K"), ("gh", "K"), ("ch", "K"), ("jh", "K"),
    ("k",  "K"), ("g",  "K"), ("c",  "K"), ("j",  "K"),
    # ---- Class T (dentals / retroflexes) ----
    # HK retroflexes are UPPERCASE: T Th D Dh
    ("Th", "T"), ("Dh", "T"),
    ("th", "T"), ("dh", "T"),
    ("T",  "T"), ("D",  "T"),
    ("t",  "T"), ("d",  "T"),
    # ---- Class P (labials) ----
    ("ph", "P"), ("bh", "P"),
    ("p",  "P"), ("b",  "P"),
    # ---- Class S (sibilants) ----
    ("sh", "S"), ("S",  "S"),
    ("s",  "S"), ("z",  "S"),
    # ---- Class M (bilabial nasal) ----
    ("m",  "M"),
    # ---- Class N (other nasals) ----
    ("N",  "N"), ("ñ",  "N"),   # HK retroflex nasal N, palatal ñ
    ("n",  "N"),
    # ---- Class R (rhotics) ----
    ("R",  "R"),                 # HK retroflex R
    ("r",  "R"),
    # ---- Class L (laterals) ----
    ("L",  "L"),                 # HK retroflex L
    ("l",  "L"),
    # ---- Class V (approximants) ----
    ("v",  "V"), ("w",  "V"),
    # ---- Class Y ----
    ("y",  "Y"),
    # ---- Class H ----
    ("h",  "H"),
    # ---- Vowels (deleted — mapped to empty string) ----
    # HK vowels: a A i I u U e E o O ai au M H (anusvara/visarga handled below)
    # We list them explicitly so they are consumed and produce no symbol.
    ("ai", ""), ("au", ""),
    ("aa", ""), ("ii", ""), ("uu", ""),
    ("A",  ""), ("I",  ""), ("U",  ""),
    ("e",  ""), ("E",  ""), ("o",  ""), ("O",  ""),
    ("a",  ""),
    # HK anusvara (M with dot) and visarga (H with dot) — treat as nasal/deleted
    # They appear as plain M/H in standard HK output from indic_transliteration
]

# Build a lookup: first char → list of (grapheme, symbol) sorted by length desc
from collections import defaultdict
_FIRST_CHAR_MAP: dict[str, List[tuple[str, str]]] = defaultdict(list)
for _g, _s in _DIGRAPH_TABLE:
    if _g:
        _FIRST_CHAR_MAP[_g[0]].append((_g, _s))
# Sort each bucket: longest grapheme first (greedy longest-match)
for _k in _FIRST_CHAR_MAP:
    _FIRST_CHAR_MAP[_k].sort(key=lambda x: -len(x[0]))

_PLOSIVE_CLASSES = {"K", "T", "P"}


def _scan_symbols(text: str) -> List[str]:
    """
    Scan `text` left-to-right with longest-match and return the raw
    class symbol list (before post-processing rules).
    """
    symbols: List[str] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        matched = False
        for grapheme, sym in _FIRST_CHAR_MAP.get(ch, []):
            end = i + len(grapheme)
            if text[i:end] == grapheme:
                if sym:          # skip vowels (empty sym)
                    symbols.append(sym)
                i = end
                matched = True
                break
        if not matched:
            # Unknown character — skip
            i += 1
    return symbols


def _nasal_assimilation(symbols: List[str]) -> List[str]:
    """Replace M or N immediately before a plosive (K/T/P) with N."""
    out: List[str] = []
    for i, sym in enumerate(symbols):
        if sym in ("M", "N") and i + 1 < len(symbols) and symbols[i + 1] in _PLOSIVE_CLASSES:
            out.append("N")
        else:
            out.append(sym)
    return out


def _delete_non_initial_h(symbols: List[str]) -> List[str]:
    """Delete every H that is not the very first symbol in the sequence."""
    if not symbols:
        return symbols
    result = [symbols[0]]
    for sym in symbols[1:]:
        if sym != "H":
            result.append(sym)
    return result


def _collapse_adjacent(symbols: List[str]) -> List[str]:
    """Collapse runs of identical adjacent symbols to one."""
    if not symbols:
        return symbols
    out = [symbols[0]]
    for sym in symbols[1:]:
        if sym != out[-1]:
            out.append(sym)
    return out


def encode(component: Component) -> List[str]:
    """
    Full Stage-3 encoding for a single Component.

    Returns a list of class symbols, e.g. ['P', 'R', 'M', 'N', 'K', 'R'].
    Returns empty list for INITIAL components (single-letter abbreviations).
    """
    if component.kind == "INITIAL":
        # For initials we apply only the class mapping to get a single symbol
        raw = _scan_symbols(component.text)
        return raw[:1]  # at most one symbol

    syms = _scan_symbols(component.text)
    syms = _nasal_assimilation(syms)
    syms = _delete_non_initial_h(syms)
    syms = _collapse_adjacent(syms)
    return syms


def code_string(component: Component) -> str:
    """Return the hyphen-joined encoding, e.g. 'P-R-M-N-K-R'."""
    syms = encode(component)
    return "-".join(syms) if syms else ""


# ---------------------------------------------------------------------------
# Quick self-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    from indicer.pipeline.stage2_structural import Component

    cases = [
        # (input_text, kind, expected_code)
        ("bramhankar",  "EXPANDED", "P-R-M-N-K-R"),
        ("brahmankar",  "EXPANDED", "P-R-M-N-K-R"),
        ("bramhanakar", "EXPANDED", "P-R-M-N-K-R"),
        ("bramhamkar",  "EXPANDED", "P-R-M-N-K-R"),
        ("kumar",       "EXPANDED", "K-M-R"),
        ("sandipa",     "EXPANDED", "S-N-T-P"),
        ("sharma",      "EXPANDED", "S-R-M"),
        ("s",           "INITIAL",  "S"),
    ]
    print(f"{'Input':<20} {'Kind':<10} {'Expected':<15} {'Got':<15} Status")
    print("-" * 70)
    for text, kind, expected in cases:
        comp = Component(text=text, kind=kind)
        got = code_string(comp)
        status = "OK" if got == expected else "FAIL"
        print(f"{text:<20} {kind:<10} {expected:<15} {got:<15} {status}")