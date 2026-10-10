"""Audit chain integrity and the Right to Services clock."""
from datetime import datetime, timedelta, timezone

from seva.engine.audit import AuditChain
from seva.models import Citizen, Flag, SevaTicket, ServiceType, Department, Stage
from seva.workflow.stages import Officer, chain_for, open_stage
from seva.workflow.sla import read_clock


def _chain():
    c = AuditChain("MH-THL-2026-GON-000012-0")
    c.append("verified", "SYSTEM", "Automated Verification", {"CGS": 0.81})
    c.append("forwarded", "GON-TAL-004", "R. Ingle", {"remark": "field visit"})
    c.append("approved", "GON-SDO-01", "M. Chavan", {"overrode": []})
    return c


def test_a_fresh_chain_verifies():
    assert _chain().verify() == (True, None)


def test_altering_an_earlier_entry_breaks_the_chain():
    c = _chain()
    c.entries[1].payload["remark"] = "rewritten later"
    ok, broken = c.verify()
    assert not ok and "entry 2" in broken


def test_each_entry_links_to_the_one_before():
    c = _chain()
    for i in range(1, len(c.entries)):
        assert c.entries[i].previous_hash == c.entries[i - 1].entry_hash


def _ticket(age_days: float, service=ServiceType.CASTE_CERTIFICATE):
    now = datetime.now(timezone.utc)
    submitted = now - timedelta(days=age_days)
    t = SevaTicket(
        seva_id="MH-THL-2026-GON-000001-4", service=service,
        department=Department.TAHSIL,
        citizen=Citizen(full_name="Test Applicant", aadhaar_last4="0000"),
        district="Gondia", taluka="Amgaon",
        submitted_at=submitted.isoformat(),
    )
    open_stage(t, Stage.TALATHI,
               Officer("GON-TAL-004", "R. Ingle", "Talathi", "Gondia", "Amgaon"),
               at=submitted.isoformat())
    return t


def test_flag_escalates_as_the_statutory_period_is_consumed():
    chain = chain_for(ServiceType.CASTE_CERTIFICATE)
    assert read_clock(_ticket(3), chain).flag is Flag.GREEN
    assert read_clock(_ticket(18), chain).flag in (Flag.YELLOW, Flag.ORANGE)
    assert read_clock(_ticket(26), chain).flag is Flag.ORANGE
    assert read_clock(_ticket(34), chain).flag is Flag.RED


def test_a_breach_is_reported_as_breached():
    reading = read_clock(_ticket(40), chain_for(ServiceType.CASTE_CERTIFICATE))
    assert reading.breached
    assert "breached" in reading.reason.lower()


def test_the_reason_names_the_desk_holding_the_file():
    reading = read_clock(_ticket(26), chain_for(ServiceType.CASTE_CERTIFICATE))
    assert "Talathi" in reading.reason


def test_a_desk_holding_a_file_too_long_is_called_out():
    """Caste certificate: 30 days across 4 desks is 7.5 days each."""
    reading = read_clock(_ticket(20), chain_for(ServiceType.CASTE_CERTIFICATE))
    assert reading.stage_overrun
    assert "this desk has held it" in reading.reason.lower()
