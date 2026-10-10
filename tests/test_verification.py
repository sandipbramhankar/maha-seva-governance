"""End-to-end verdicts, and the reasoning behind each one."""
import pytest

from seva.engine.audit import AuditChain
from seva.engine.orchestrator import assess
from seva.engine.verification import run_checks
from seva.models import MatchStatus, ServiceType, Verdict

CASTE = ServiceType.CASTE_CERTIFICATE

#: Every decision path the engine must handle, and where each must land.
EXPECTED = {
    "4821": (Verdict.APPROVE,     "every source agrees"),
    "9034": (Verdict.APPROVE,     "same person across scripts and spellings"),
    "5567": (Verdict.ESCALATE,    "caste contradicted by the village record"),
    "7712": (Verdict.ESCALATE,    "income contradicted by land, vehicle, subsidy"),
    "3390": (Verdict.INVESTIGATE, "three-generation proof does not close"),
    "1101": (Verdict.ESCALATE,    "coordinated group"),
    "1102": (Verdict.ESCALATE,    "coordinated group"),
    "1103": (Verdict.ESCALATE,    "coordinated group"),
    "6648": (Verdict.APPROVE,     "thin evidence but nothing contradicts it"),
}


@pytest.mark.parametrize("aadhaar,expected,why",
                         [(k, v[0], v[1]) for k, v in EXPECTED.items()])
def test_verdict(aadhaar, expected, why, citizen, fabric, graph):
    report = assess(citizen(aadhaar), CASTE, fabric, graph, AuditChain("T"))
    assert report.verdict is expected, (
        f"{aadhaar} ({why}) gave {report.verdict.value}: {report.reasons}"
    )


def test_every_verdict_carries_a_reason(citizen, fabric, graph):
    for aadhaar in EXPECTED:
        report = assess(citizen(aadhaar), CASTE, fabric, graph, AuditChain("T"))
        assert report.reasons, f"{aadhaar} produced no reason"
        assert all(r.strip() for r in report.reasons)


def test_devanagari_land_record_resolves_to_the_applicant(citizen, fabric):
    """
    The 1961 village record is in Devanagari and the application is in Latin.
    Resolving them is the reason indicer is in this system at all.
    """
    checks = run_checks(citizen("9034"), fabric)
    household = [c for c in checks
                 if c.attribute == "Household link" and "Bhulekh" in c.source]
    assert household and household[0].status is MatchStatus.MATCH
    assert "applicant's own name" in household[0].note


def test_land_in_the_fathers_name_is_not_an_identity_mismatch(citizen, fabric):
    """
    Land routinely stays in the father's name. Reporting that as a failed
    identity check would reject most genuine rural applicants; reporting it as
    an identity match would assert that two people are one.
    """
    checks = run_checks(citizen("5567"), fabric)
    identity = [c for c in checks if c.attribute == "Identity (name)"]
    assert all(c.status is not MatchStatus.MISMATCH for c in identity)

    household = [c for c in checks
                 if c.attribute == "Household link" and "Bhulekh" in c.source]
    assert household[0].status is MatchStatus.MATCH
    assert "father" in household[0].note.lower()


def test_caste_mismatch_names_the_village_record_and_its_year(citizen, fabric, graph):
    report = assess(citizen("5567"), CASTE, fabric, graph, AuditChain("T"))
    joined = " ".join(report.reasons)
    assert "1952" in joined and "OBC-Kunbi" in joined and "SC-Mahar" in joined


def test_creamy_layer_makes_income_decisive_for_obc(citizen, fabric, graph):
    """An OBC claim is subject to the creamy layer, so income decides too."""
    report = assess(citizen("7712"), CASTE, fabric, graph, AuditChain("T"))
    assert report.verdict is Verdict.ESCALATE
    joined = " ".join(report.reasons).lower()
    assert "subsidy" in joined or "hectare" in joined


def test_missing_records_do_not_count_against_the_applicant(citizen, fabric, graph):
    """
    An urban applicant with no land and no ration card must not be penalised
    for records that were never going to exist.
    """
    report = assess(citizen("6648"), CASTE, fabric, graph, AuditChain("T"))
    assert report.verdict is Verdict.APPROVE
    assert report.dcs == 100.0
