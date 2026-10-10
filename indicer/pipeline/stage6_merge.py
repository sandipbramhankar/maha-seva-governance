"""
Stage 6 — Three-State Merge Decision
======================================
Converts the composite confidence score from Stage 5 into one of three
outcomes:

  MERGE     — score ≥ THRESHOLD_HIGH  (records refer to the same entity)
  DEFERRED  — THRESHOLD_LOW ≤ score < THRESHOLD_HIGH  (requires human review)
  DISTINCT  — score < THRESHOLD_LOW   (records are different entities)

Default thresholds (tunable):
  THRESHOLD_HIGH     = 0.72   — normal MERGE threshold (DOB present)
  THRESHOLD_HIGH_NOD = 0.78   — stricter MERGE threshold when DOB absent
  THRESHOLD_LOW      = 0.45

The module also exposes `run_pair`, a convenience function that accepts
two Common Internal Representation (CIR) dicts, runs Stages 1–5, and
returns the MergeDecision.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, List
from enum import Enum

from indicer.pipeline.stage1_script import normalise_script
from indicer.pipeline.stage2_structural import structural_normalise
from indicer.pipeline.stage4_component import name_correspondence
from indicer.pipeline.stage5_confidence import composite_confidence, address_jaccard

THRESHOLD_HIGH:     float = 0.72   # MERGE threshold when DOB is available
THRESHOLD_HIGH_NOD: float = 0.88   # stricter MERGE threshold when DOB is absent
THRESHOLD_LOW:      float = 0.45


class Decision(str, Enum):
    MERGE    = "MERGE"
    DEFERRED = "DEFERRED"
    DISTINCT = "DISTINCT"


@dataclass
class MergeDecision:
    decision:   Decision
    score:      float
    detail:     dict   # full Stage-5 result dict

    def __repr__(self) -> str:
        return (
            f"MergeDecision({self.decision.value}, score={self.score:.4f})"
        )


def decide(
    confidence_result: dict,
    threshold_high:     float = THRESHOLD_HIGH,
    threshold_low:      float = THRESHOLD_LOW,
    dob_available:      bool  = True,
    threshold_high_nod: float = THRESHOLD_HIGH_NOD,
) -> MergeDecision:
    """
    Apply threshold rules to a Stage-5 confidence dict.

    Parameters
    ----------
    confidence_result  : dict returned by stage5_confidence.composite_confidence()
    threshold_high     : scores ≥ this → MERGE  (when DOB is present)
    threshold_low      : scores < this → DISTINCT; between → DEFERRED
    dob_available      : False when neither record has a DOB; raises the MERGE
                         threshold to threshold_high_nod so ambiguous same-name
                         pairs without DOB are deferred for human review.
    threshold_high_nod : stricter MERGE threshold used when dob_available=False
    """
    score = confidence_result["score"]
    effective_high = threshold_high if dob_available else threshold_high_nod
    if score >= effective_high:
        d = Decision.MERGE
    elif score >= threshold_low:
        d = Decision.DEFERRED
    else:
        d = Decision.DISTINCT
    return MergeDecision(decision=d, score=score, detail=confidence_result)


def _name_from_cir(cir: dict) -> str:
    """Extract the canonical name string from a CIR dict."""
    # CIR fields: full_name (single string), OR given_name + surname
    if "full_name" in cir and cir["full_name"]:
        return cir["full_name"]
    parts = []
    for field in ("given_name", "middle_name", "surname", "patronymic"):
        val = cir.get(field)
        if val:
            parts.append(val)
    return " ".join(parts)


def run_pair(
    cir1: dict,
    cir2: dict,
    surname_freq: str = "medium",
    threshold_high: float = THRESHOLD_HIGH,
    threshold_low:  float = THRESHOLD_LOW,
) -> MergeDecision:
    """
    Full pipeline run for a single record pair.

    Parameters
    ----------
    cir1, cir2 : Common Internal Representation dicts with keys:
        full_name     : str | None
        given_name    : str | None
        middle_name   : str | None
        surname       : str | None
        patronymic    : str | None
        dob           : str | None   (ISO date string or None)
        address       : str | None
        identifier    : str | None   (PAN, Aadhaar suffix, or similar)
    surname_freq : 'low' | 'medium' | 'high'
    """
    # --- Stage 1 ---
    name1_raw = _name_from_cir(cir1)
    name2_raw = _name_from_cir(cir2)
    rom1, _ = normalise_script(name1_raw)
    rom2, _ = normalise_script(name2_raw)

    # --- Stage 2 ---
    comps1 = structural_normalise(rom1)
    comps2 = structural_normalise(rom2)

    # --- Stages 3 + 4 ---
    name_score = name_correspondence(comps1, comps2)

    # --- Auxiliary attributes ---
    dob1, dob2 = cir1.get("dob"), cir2.get("dob")
    dob_match: Optional[bool] = None
    if dob1 and dob2:
        dob_match = (dob1.strip() == dob2.strip())

    addr_score = address_jaccard(cir1.get("address"), cir2.get("address"))

    id1, id2 = cir1.get("identifier"), cir2.get("identifier")
    id_match: Optional[bool] = None
    if id1 and id2:
        id_match = (id1.strip() == id2.strip())

    # --- Stage 5 ---
    conf = composite_confidence(
        name_score=name_score,
        dob_match=dob_match,
        addr_score=addr_score,
        id_match=id_match,
        surname_freq=surname_freq,
    )

    # --- Stage 6 ---
    # DOB is "available" only when BOTH records have a DOB field.
    # If either record lacks DOB (e.g. any pair involving Repo C), we apply
    # the stricter no-DOB threshold so ambiguous same-name pairs are deferred.
    dob_available = bool(cir1.get("dob")) and bool(cir2.get("dob"))
    return decide(
        conf,
        threshold_high=threshold_high,
        threshold_low=threshold_low,
        dob_available=dob_available,
    )


# ---------------------------------------------------------------------------
# Quick self-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    pairs = [
        (
            {"full_name": "संदीप ब्राह्मणकर", "dob": "1985-03-14"},
            {"full_name": "Sandip Brahmankar",  "dob": "1985-03-14"},
            "Devanagari ↔ Latin same person",
            "low",
        ),
        (
            {"full_name": "Anil Kumar Sharma", "dob": "1990-07-22"},
            {"full_name": "Anil K Sharma",     "dob": "1990-07-22"},
            "Initial middle name",
            "high",
        ),
        (
            {"full_name": "Meera Devi", "dob": None},
            {"full_name": "Meera D",    "dob": None},
            "No DOB (Repo-C type)",
            "medium",
        ),
        (
            {"full_name": "Ramesh Pawar", "dob": "1978-01-10"},
            {"full_name": "Suresh Pawar", "dob": "1978-01-10"},
            "Different given name, same DOB",
            "high",
        ),
    ]
    for c1, c2, label, freq in pairs:
        result = run_pair(c1, c2, surname_freq=freq)
        print(f"{label}: {result}")