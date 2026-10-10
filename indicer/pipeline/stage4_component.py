"""
Stage 4 — Component Correspondence
=====================================
Computes a name-level similarity score from two lists of Components
(each already phonetically encoded by Stage 3).

ALGORITHM
---------
1. Encode each component list with Stage 3 to obtain symbol lists.
2. For every pair (c_i from list1, c_j from list2) compute a raw similarity:
     - EXPANDED vs EXPANDED : 1 − normalised_edit_distance(symbols1, symbols2)
       where edit distance is Wagner-Fischer on the symbol sequences.
     - INITIAL vs EXPANDED  : 1.0 if initial symbol == first symbol of
                              expanded code, else 0.0
     - BOTH INITIAL         : 1.0 if same letter, else 0.0
     - EXPANDED vs INITIAL  : same as INITIAL vs EXPANDED (symmetric)
3. Find the assignment of components between the two lists that maximises
   the sum of pair scores (optimal bipartite matching via permutation
   enumeration — sufficient for names with ≤ 8 components each).
4. Score = total_matched_score / max(len(list1), len(list2))
   (unmatched components contribute 0, penalising length mismatches).
"""

from __future__ import annotations
from itertools import permutations
from typing import List, Sequence

from indicer.pipeline.stage2_structural import Component
from indicer.pipeline.stage3_phonetic import encode


# ---------------------------------------------------------------------------
# Wagner-Fischer edit distance on lists
# ---------------------------------------------------------------------------

def _edit_distance(a: List[str], b: List[str]) -> int:
    """Levenshtein distance between two symbol lists."""
    m, n = len(a), len(b)
    if m == 0:
        return n
    if n == 0:
        return m
    # DP table
    dp = list(range(n + 1))
    for i in range(1, m + 1):
        prev = dp[0]
        dp[0] = i
        for j in range(1, n + 1):
            old = dp[j]
            if a[i - 1] == b[j - 1]:
                dp[j] = prev
            else:
                dp[j] = 1 + min(prev, dp[j], dp[j - 1])
            prev = old
    return dp[n]


def _normalised_edit_distance(a: List[str], b: List[str]) -> float:
    """Edit distance normalised to [0, 1] by max length."""
    if not a and not b:
        return 0.0
    max_len = max(len(a), len(b))
    return _edit_distance(a, b) / max_len


# ---------------------------------------------------------------------------
# Pair similarity
# ---------------------------------------------------------------------------

def _pair_sim(c1: Component, c2: Component) -> float:
    """Similarity between a single pair of components."""
    syms1 = encode(c1)
    syms2 = encode(c2)

    if c1.kind == "INITIAL" and c2.kind == "INITIAL":
        # Compare raw first letters
        return 1.0 if c1.text[0] == c2.text[0] else 0.0

    if c1.kind == "INITIAL":
        # syms1 has at most one symbol
        if not syms1 or not syms2:
            return 0.0
        return 1.0 if syms1[0] == syms2[0] else 0.0

    if c2.kind == "INITIAL":
        if not syms2 or not syms1:
            return 0.0
        return 1.0 if syms2[0] == syms1[0] else 0.0

    # Both EXPANDED
    if not syms1 and not syms2:
        return 1.0
    if not syms1 or not syms2:
        return 0.0
    return 1.0 - _normalised_edit_distance(syms1, syms2)


# ---------------------------------------------------------------------------
# Optimal bipartite assignment
# ---------------------------------------------------------------------------

def _optimal_assignment(comps1: List[Component], comps2: List[Component]) -> float:
    """
    Returns the maximum total pair similarity achievable by any
    one-to-one assignment of comps1 → comps2.

    Uses brute-force permutation enumeration (fine for ≤ 8 components).
    The shorter list is iterated over; unmatched items score 0.
    """
    if not comps1 or not comps2:
        return 0.0

    # Ensure comps1 is the shorter (or equal) list for fewer permutations
    if len(comps1) > len(comps2):
        comps1, comps2 = comps2, comps1

    # Pre-compute pairwise similarities
    sim_matrix = [
        [_pair_sim(comps1[i], comps2[j]) for j in range(len(comps2))]
        for i in range(len(comps1))
    ]

    # Find best permutation of comps2 indices for comps1
    best = 0.0
    indices = list(range(len(comps2)))
    for perm in permutations(indices, len(comps1)):
        total = sum(sim_matrix[i][perm[i]] for i in range(len(comps1)))
        if total > best:
            best = total
    return best


def name_correspondence(comps1: List[Component], comps2: List[Component]) -> float:
    """
    Stage 4 entry point.

    Returns a score in [0, 1] measuring how well the two component lists
    correspond to each other.

    Score = best_assignment_total / max(len(comps1), len(comps2))
    """
    if not comps1 and not comps2:
        return 1.0
    if not comps1 or not comps2:
        return 0.0

    best_total = _optimal_assignment(comps1, comps2)
    denom = max(len(comps1), len(comps2))
    return best_total / denom


# ---------------------------------------------------------------------------
# Quick self-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    from indicer.pipeline.stage2_structural import Component

    def comps(pairs):
        return [Component(text=t, kind=k) for t, k in pairs]

    cases = [
        (
            comps([("bramhankar", "EXPANDED"), ("sandipa", "EXPANDED")]),
            comps([("brahmankar", "EXPANDED"), ("sandipa", "EXPANDED")]),
            "≈ 1.0 (same phonetics)",
        ),
        (
            comps([("s", "INITIAL"), ("bramhankar", "EXPANDED")]),
            comps([("sandipa", "EXPANDED"), ("bramhankar", "EXPANDED")]),
            "≈ 0.75 (initial matches first symbol)",
        ),
        (
            comps([("kumar", "EXPANDED")]),
            comps([("sharma", "EXPANDED")]),
            "< 0.5 (different names)",
        ),
    ]
    for c1, c2, label in cases:
        score = name_correspondence(c1, c2)
        print(f"{label}: score = {score:.4f}")