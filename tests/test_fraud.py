"""Fraud graph: it must find the ring and leave everyone else alone."""
from seva.engine.fraud import _is_premises_address

RING = ("1101", "1102", "1103")
CLEAN = ("4821", "9034", "5567", "7712", "3390", "6648")


def test_ring_is_detected(graph):
    for aadhaar in RING:
        assert graph.assess(aadhaar).frs >= 70.0


def test_nobody_else_is_flagged(graph):
    for aadhaar in CLEAN:
        assert graph.assess(aadhaar).frs == 0.0, aadhaar


def test_sharing_a_village_is_not_evidence():
    """
    4821 and 9034 live in the same village. A village is not a household, and
    flagging neighbours would make the signal useless in rural Maharashtra.
    """
    assert not _is_premises_address("Kidangipar, Amgaon, Gondia")
    assert _is_premises_address("Plot 14, Belora, Pusad, Yavatmal")
    assert _is_premises_address("14/2, Belora, Pusad")


def test_ring_findings_name_what_was_shared(graph):
    findings = " ".join(graph.assess("1101").findings).lower()
    assert "address" in findings and "mobile" in findings and "surname" in findings


def test_ring_members_are_linked_to_each_other(graph):
    peers = graph.assess("1101").findings[0]
    assert "1102" in peers and "1103" in peers
