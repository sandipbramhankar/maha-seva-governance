"""
Stage 5 — Multi-Attribute Confidence Scoring
=============================================
Combines name similarity (from Stage 4) with auxiliary attribute
similarities (DOB, address, identifier) into a single composite
confidence score.

ATTRIBUTE INDICATORS
--------------------
  name_score   : float [0,1]   — from Stage 4 (mandatory)
  dob_match    : bool | None   — True/False if both present, None if either missing
  addr_score   : float | None  — Jaccard on address tokens (None if either missing)
  id_match     : bool | None   — True/False if both present, None if either missing

SURNAME FREQUENCY MULTIPLIER
-----------------------------
  Surname frequency class affects how much evidential weight the name alone carries:
    'low'    (rare  surnames) → multiplier 1.40
    'medium'                 → multiplier 1.00
    'high'   (common names)  → multiplier 0.65

WEIGHT SCHEDULE (before renormalisation)
-----------------------------------------
  name_score : base_weight = 0.55
  dob_match  : base_weight = 0.25
  addr_score : base_weight = 0.10
  id_match   : base_weight = 0.10

  Only attributes whose values are not None contribute; weights are
  renormalised to sum to 1.0 before combining.

  name base_weight is further multiplied by the surname frequency multiplier
  *before* renormalisation.
"""

from __future__ import annotations
from typing import Optional


_FREQ_MULTIPLIER = {
    "low":    1.40,
    "medium": 1.00,
    "high":   0.65,
}

_BASE_WEIGHTS = {
    "name": 0.55,
    "dob":  0.25,
    "addr": 0.10,
    "id":   0.10,
}


def _bool_to_score(b: bool) -> float:
    return 1.0 if b else 0.0


def composite_confidence(
    name_score: float,
    dob_match: Optional[bool] = None,
    addr_score: Optional[float] = None,
    id_match: Optional[bool] = None,
    surname_freq: str = "medium",
) -> dict:
    """
    Stage 5 entry point.

    Parameters
    ----------
    name_score   : similarity score from Stage 4 in [0, 1].
    dob_match    : True/False if both records have DOB, else None.
    addr_score   : float [0,1] address similarity, or None if unavailable.
    id_match     : True/False if both records have an identifier, else None.
    surname_freq : 'low' | 'medium' | 'high'

    Returns
    -------
    dict with keys:
      'score'             : float — composite confidence in [0, 1]
      'name_weight'       : float — effective weight used for name
      'dob_weight'        : float — effective weight for DOB (0 if absent)
      'addr_weight'       : float — effective weight for address (0 if absent)
      'id_weight'         : float — effective weight for ID (0 if absent)
      'freq_multiplier'   : float — the surname frequency multiplier applied
      'attributes_used'   : list[str]
    """
    freq_mult = _FREQ_MULTIPLIER.get(surname_freq, 1.0)

    # Build map of attribute → (raw_score, base_weight)
    candidates = {
        "name": (float(name_score), _BASE_WEIGHTS["name"] * freq_mult),
    }
    if dob_match is not None:
        candidates["dob"] = (_bool_to_score(dob_match), _BASE_WEIGHTS["dob"])
    if addr_score is not None:
        candidates["addr"] = (float(addr_score), _BASE_WEIGHTS["addr"])
    if id_match is not None:
        candidates["id"] = (_bool_to_score(id_match), _BASE_WEIGHTS["id"])

    # Renormalise weights
    total_weight = sum(w for _, w in candidates.values())
    if total_weight == 0:
        return {
            "score": 0.0,
            "name_weight": 0.0, "dob_weight": 0.0,
            "addr_weight": 0.0, "id_weight": 0.0,
            "freq_multiplier": freq_mult,
            "attributes_used": [],
        }

    norm = {k: w / total_weight for k, (_, w) in candidates.items()}

    # Composite score
    score = sum(candidates[k][0] * norm[k] for k in candidates)
    # Clamp to [0, 1]
    score = max(0.0, min(1.0, score))

    return {
        "score": score,
        "name_weight":  norm.get("name", 0.0),
        "dob_weight":   norm.get("dob",  0.0),
        "addr_weight":  norm.get("addr", 0.0),
        "id_weight":    norm.get("id",   0.0),
        "freq_multiplier": freq_mult,
        "attributes_used": list(candidates.keys()),
    }


def address_jaccard(addr1: Optional[str], addr2: Optional[str]) -> Optional[float]:
    """
    Compute Jaccard similarity between two address strings at the token
    level.  Returns None if either is missing or empty.
    """
    if not addr1 or not addr2:
        return None
    tokens1 = set(addr1.lower().split())
    tokens2 = set(addr2.lower().split())
    if not tokens1 and not tokens2:
        return 1.0
    inter = tokens1 & tokens2
    union = tokens1 | tokens2
    return len(inter) / len(union)


# ---------------------------------------------------------------------------
# Quick self-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    cases = [
        dict(name_score=0.92, dob_match=True,  addr_score=0.80, id_match=None, surname_freq="low",    label="rare surname, DOB match"),
        dict(name_score=0.92, dob_match=True,  addr_score=0.80, id_match=None, surname_freq="high",   label="common surname, DOB match"),
        dict(name_score=0.85, dob_match=None,  addr_score=None, id_match=None, surname_freq="medium", label="name only, Repo-C pair"),
        dict(name_score=0.30, dob_match=False, addr_score=0.10, id_match=None, surname_freq="medium", label="poor match"),
    ]
    for kw in cases:
        label = kw.pop("label")
        result = composite_confidence(**kw)
        print(f"{label}: score = {result['score']:.4f}  (freq×{result['freq_multiplier']})")