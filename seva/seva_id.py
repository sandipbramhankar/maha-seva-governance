"""
Seva ID
========
One identifier per citizen request, issued at submission, carried unchanged
across every department that touches the request.

Format
------
    MH-THL-2026-GON-004712-7
    |  |   |    |   |      |
    |  |   |    |   |      +-- Verhoeff check digit
    |  |   |    |   +--------- six-digit sequence within district-year
    |  |   |    +------------- three-letter district revenue code
    |  |   +------------------ year of submission
    |  +---------------------- department (THL/REV/EDU/FOR)
    +------------------------- state

The check digit uses the Verhoeff algorithm, the same scheme Aadhaar uses, so a
single mistyped or transposed character is rejected before it reaches a
database. That matters because citizens read this number aloud over the phone
and write it on paper forms at the Seva Kendra.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict

from seva.models import Department
from seva.data.maharashtra import district_code

STATE_PREFIX = "MH"

DEPARTMENT_CODE: Dict[Department, str] = {
    Department.TAHSIL:    "THL",
    Department.REVENUE:   "REV",
    Department.EDUCATION: "EDU",
    Department.FOREST:    "FOR",
}
CODE_DEPARTMENT: Dict[str, Department] = {v: k for k, v in DEPARTMENT_CODE.items()}


# ---------------------------------------------------------------------------
# Verhoeff check digit
# ---------------------------------------------------------------------------

_D = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 2, 3, 4, 0, 6, 7, 8, 9, 5),
    (2, 3, 4, 0, 1, 7, 8, 9, 5, 6),
    (3, 4, 0, 1, 2, 8, 9, 5, 6, 7),
    (4, 0, 1, 2, 3, 9, 5, 6, 7, 8),
    (5, 9, 8, 7, 6, 0, 4, 3, 2, 1),
    (6, 5, 9, 8, 7, 1, 0, 4, 3, 2),
    (7, 6, 5, 9, 8, 2, 1, 0, 4, 3),
    (8, 7, 6, 5, 9, 3, 2, 1, 0, 4),
    (9, 8, 7, 6, 5, 4, 3, 2, 1, 0),
)
_P = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 5, 7, 6, 2, 8, 3, 0, 9, 4),
    (5, 8, 0, 3, 7, 9, 6, 1, 4, 2),
    (8, 9, 1, 6, 0, 4, 3, 5, 2, 7),
    (9, 4, 5, 3, 1, 2, 6, 8, 7, 0),
    (4, 2, 8, 6, 5, 7, 3, 9, 0, 1),
    (2, 7, 9, 3, 8, 0, 6, 4, 1, 5),
    (7, 0, 4, 6, 9, 1, 3, 2, 5, 8),
)
_INV = (0, 4, 3, 2, 1, 5, 6, 7, 8, 9)


def verhoeff_digit(number: str) -> int:
    """Check digit for a string of decimal digits."""
    c = 0
    for i, ch in enumerate(reversed(number)):
        c = _D[c][_P[(i + 1) % 8][int(ch)]]
    return _INV[c]


def verhoeff_valid(number_with_check: str) -> bool:
    """True when the trailing digit is the correct check digit."""
    c = 0
    for i, ch in enumerate(reversed(number_with_check)):
        c = _D[c][_P[i % 8][int(ch)]]
    return c == 0


# ---------------------------------------------------------------------------
# Issue and parse
# ---------------------------------------------------------------------------

class SevaIdIssuer:
    """
    Allocates sequential Seva IDs per (district, year). In production the
    counter lives in the database behind a unique constraint; this in-memory
    version keeps the demo self-contained and deterministic.
    """

    def __init__(self) -> None:
        self._counters: Dict[str, int] = {}

    def issue(self, department: Department, district: str,
              year: int | None = None) -> str:
        year = year or datetime.now(timezone.utc).year
        dcode = district_code(district)
        key = f"{dcode}-{year}"
        self._counters[key] = self._counters.get(key, 0) + 1
        seq = self._counters[key]

        body_digits = f"{year}{seq:06d}"
        check = verhoeff_digit(body_digits)
        return (
            f"{STATE_PREFIX}-{DEPARTMENT_CODE[department]}-"
            f"{year}-{dcode}-{seq:06d}-{check}"
        )

    def issued_count(self, district: str, year: int | None = None) -> int:
        year = year or datetime.now(timezone.utc).year
        return self._counters.get(f"{district_code(district)}-{year}", 0)


def parse(seva_id: str) -> Dict[str, object]:
    """
    Break a Seva ID into its parts and verify the check digit.

    Raises ValueError when the shape is wrong or the check digit fails, so a
    mistyped number never silently reaches a lookup.
    """
    parts = seva_id.strip().upper().split("-")
    if len(parts) != 6:
        raise ValueError(f"Seva ID must have six segments, got {len(parts)}: {seva_id!r}")

    state, dept_code, year_s, dist_code, seq_s, check_s = parts

    if state != STATE_PREFIX:
        raise ValueError(f"Unknown state prefix {state!r}")
    if dept_code not in CODE_DEPARTMENT:
        raise ValueError(f"Unknown department code {dept_code!r}")
    if not (year_s.isdigit() and seq_s.isdigit() and check_s.isdigit()):
        raise ValueError(f"Non-numeric segment in {seva_id!r}")
    if (len(year_s), len(seq_s), len(check_s)) != (4, 6, 1):
        raise ValueError(
            f"Segment lengths must be year=4, sequence=6, check=1 in {seva_id!r}"
        )
    if not verhoeff_valid(f"{year_s}{seq_s}{check_s}"):
        raise ValueError(f"Check digit failed for {seva_id!r} — likely a typo")

    return {
        "state":      state,
        "department": CODE_DEPARTMENT[dept_code],
        "year":       int(year_s),
        "district_code": dist_code,
        "sequence":   int(seq_s),
    }


def is_valid(seva_id: str) -> bool:
    try:
        parse(seva_id)
        return True
    except ValueError:
        return False


if __name__ == "__main__":
    issuer = SevaIdIssuer()
    for _ in range(12):
        last = issuer.issue(Department.TAHSIL, "Gondia", 2026)
    other = issuer.issue(Department.FOREST, "Gadchiroli", 2026)

    for sid in (last, other):
        info = parse(sid)
        print(f"{sid}   {info['department'].value:9s} seq={info['sequence']}")

    # Transpose the final two digits of the sequence: 000012 -> 000021
    head, seq_s, check_s = last.rsplit("-", 2)
    swapped = seq_s[:-2] + seq_s[-1] + seq_s[-2]
    transposed = f"{head}-{swapped}-{check_s}"

    # Change one digit of the sequence: 000012 -> 000013
    altered_seq = seq_s[:-1] + str((int(seq_s[-1]) + 1) % 10)
    altered = f"{head}-{altered_seq}-{check_s}"

    print()
    print(f"issued      {last:28s} valid={is_valid(last)}")
    print(f"transposed  {transposed:28s} valid={is_valid(transposed)}")
    print(f"one digit   {altered:28s} valid={is_valid(altered)}")
    print(f"wrong shape {'MH-THL-2026-GON-12-4':28s} valid={is_valid('MH-THL-2026-GON-12-4')}")
