"""
Stage 2 — Structural Normalisation
====================================
Accepts the HK-romanised string from Stage 1 and returns a list of
Component namedtuples, each carrying:

  text  : str   — cleaned token text (lowercase)
  kind  : str   — 'EXPANDED' or 'INITIAL'

Rules applied (in order):
  1. Lowercase the whole string.
  2. Remove recognised honorific prefixes.
  3. Strip non-alphabetic characters (except hyphens within words and periods
     used as initial markers).
  4. Tokenise on whitespace.
  5. Classify each token:
       INITIAL   — single letter, OR 1–2 chars ending with '.'
       EXPANDED  — all other non-empty tokens
"""

import re
from dataclasses import dataclass
from typing import List

# ---------------------------------------------------------------------------
# Honorific / title prefixes to remove (case-insensitive)
# ---------------------------------------------------------------------------
_HONORIFICS = {
    # Indian honorifics
    "shri", "shree", "sri", "smt", "srimati", "km", "kumari",
    "late", "lata",
    # Academic / professional
    "dr", "dr.", "prof", "prof.", "rev", "rev.",
    # Western
    "mr", "mr.", "mrs", "mrs.", "ms", "ms.", "miss", "master",
    # Military / official
    "col", "lt", "maj", "brig", "gen", "adv",
}

# Compiled pattern: word boundaries on honorifics followed by space or period
_HONORIFIC_PAT = re.compile(
    r"\b(" + "|".join(re.escape(h) for h in sorted(_HONORIFICS, key=len, reverse=True)) + r")\.?\s*",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Component:
    text: str   # lowercase alphabetic content
    kind: str   # 'EXPANDED' or 'INITIAL'

    def __repr__(self) -> str:
        return f"Component({self.text!r}, {self.kind})"


def _strip_honorifics(s: str) -> str:
    return _HONORIFIC_PAT.sub(" ", s).strip()


def _clean_token(tok: str) -> str:
    """Remove leading/trailing non-alpha, preserve internal hyphens."""
    # Strip trailing periods (initial abbreviation marker handled separately)
    tok = tok.rstrip(".")
    # Remove any remaining non-alpha except hyphen
    tok = re.sub(r"[^a-z\-]", "", tok)
    return tok


def _classify(tok: str) -> str:
    """Return 'INITIAL' or 'EXPANDED'."""
    # If original token was a single letter (possibly with period), it's INITIAL
    # After _clean_token the period is gone; len == 1 → INITIAL
    if len(tok) <= 1:
        return "INITIAL"
    return "EXPANDED"


def structural_normalise(romanised: str) -> List[Component]:
    """
    Stage 2 entry point.

    Parameters
    ----------
    romanised : str
        HK-romanised (or Latin) name string from Stage 1.

    Returns
    -------
    List[Component]
        Ordered list of name components with kind classification.
        Empty list if input is blank.
    """
    if not romanised or not romanised.strip():
        return []

    s = romanised.lower()
    s = _strip_honorifics(s)

    # Replace hyphens that are NOT between letters with spaces
    s = re.sub(r"(?<![a-z])-|-(?![a-z])", " ", s)

    # Tokenise
    tokens = s.split()

    components: List[Component] = []
    for raw_tok in tokens:
        # Check if it looks like an initial BEFORE cleaning (has trailing period)
        is_initial_hint = raw_tok.endswith(".") or len(raw_tok.rstrip(".")) == 1
        cleaned = _clean_token(raw_tok)
        if not cleaned:
            continue
        kind = "INITIAL" if (is_initial_hint or _classify(cleaned) == "INITIAL") else "EXPANDED"
        components.append(Component(text=cleaned, kind=kind))

    return components


# ---------------------------------------------------------------------------
# Quick self-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    examples = [
        ("sandIpa prabhu bramhaNakara", [("sandipa", "EXPANDED"), ("prabhu", "EXPANDED"), ("bramhanakara", "EXPANDED")]),
        ("S. P. Bramhankar", [("s", "INITIAL"), ("p", "INITIAL"), ("bramhankar", "EXPANDED")]),
        ("Dr. Anita Kumar", [("anita", "EXPANDED"), ("kumar", "EXPANDED")]),
        ("Smt. Meera Devi", [("meera", "EXPANDED"), ("devi", "EXPANDED")]),
    ]
    for inp, expected in examples:
        result = structural_normalise(inp)
        print(f"Input : {inp!r}")
        print(f"Output: {result}")
        match = all(
            c.text == e[0] and c.kind == e[1]
            for c, e in zip(result, expected)
        ) and len(result) == len(expected)
        print(f"Match : {'OK' if match else 'FAIL'}\n")