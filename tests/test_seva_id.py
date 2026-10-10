"""Seva ID issue, parse and error detection."""
import pytest

from seva.models import Department
from seva.seva_id import (
    SevaIdIssuer, parse, is_valid, verhoeff_digit, verhoeff_valid,
)


def test_issue_and_parse_round_trip():
    issuer = SevaIdIssuer()
    sid = issuer.issue(Department.TAHSIL, "Gondia", 2026)
    info = parse(sid)
    assert info["department"] is Department.TAHSIL
    assert info["district_code"] == "GON"
    assert info["year"] == 2026
    assert info["sequence"] == 1


def test_sequence_is_per_district_year():
    issuer = SevaIdIssuer()
    issuer.issue(Department.TAHSIL, "Gondia", 2026)
    issuer.issue(Department.REVENUE, "Gondia", 2026)
    other = issuer.issue(Department.TAHSIL, "Pune", 2026)
    assert parse(other)["sequence"] == 1
    assert issuer.issued_count("Gondia", 2026) == 2


def test_single_digit_error_is_rejected():
    issuer = SevaIdIssuer()
    sid = issuer.issue(Department.TAHSIL, "Beed", 2026)
    head, seq, check = sid.rsplit("-", 2)
    altered = f"{head}-{seq[:-1]}{(int(seq[-1]) + 1) % 10}-{check}"
    assert is_valid(sid)
    assert not is_valid(altered)


@pytest.mark.parametrize("seq", ["000012", "004719", "123456", "000907"])
def test_adjacent_transposition_is_rejected(seq):
    body = f"2026{seq}"
    check = verhoeff_digit(body)
    for i in range(len(body) - 1):
        if body[i] == body[i + 1]:
            continue
        swapped = list(body)
        swapped[i], swapped[i + 1] = swapped[i + 1], swapped[i]
        assert not verhoeff_valid("".join(swapped) + str(check))


def test_malformed_shapes_are_rejected():
    for bad in ("MH-THL-2026-GON-12-4", "MH-XXX-2026-GON-000001-4",
                "XX-THL-2026-GON-000001-4", "MH-THL-2026-GON-000001",
                "MH-THL-20X6-GON-000001-4"):
        assert not is_valid(bad), bad
