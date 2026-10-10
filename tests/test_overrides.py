"""
Officer action and the override record.

An officer may always overrule the engine. These tests pin the conditions
under which they may do it: holding the file, naming each flag, and giving a
reason that is recorded against their name.
"""
import pytest

from seva.engine.audit import AuditChain
from seva.engine.orchestrator import assess
from seva.models import Department, ServiceType, Stage, Verdict
from seva.seva_id import SevaIdIssuer
from seva.store import build_demo_store
from seva.workflow.overrides import (
    MIN_REASON_CHARS, OverrideRefused, open_flags, perform, validate_action,
)
from seva.workflow.stages import Officer, open_stage

CASTE = ServiceType.CASTE_CERTIFICATE

TALATHI = Officer("GON-TAL-004", "R. Ingle", "Talathi", "Gondia", "Amgaon")
OTHER = Officer("GON-TAL-009", "S. Kale", "Talathi", "Gondia", "Deori")

GOOD_REASON = (
    "Family known to this office since 1998; the 1952 entry was corrected "
    "by Tehsildar order dated 14 March 2019, copy on file."
)


def _ticket(citizen, fabric, graph, *, stage=Stage.TALATHI, officer=TALATHI):
    """A ticket that has been verified and is sitting on one officer's desk."""
    from seva.models import SevaTicket

    chain = AuditChain("MH-THL-2026-GON-000001-4")
    ticket = SevaTicket(
        seva_id="MH-THL-2026-GON-000001-4", service=CASTE,
        department=Department.TAHSIL, citizen=citizen,
        district="Gondia", taluka="Amgaon",
        submitted_at="2026-09-14T10:30:00+00:00",
    )
    ticket.verification = assess(citizen, CASTE, fabric, graph, chain)
    open_stage(ticket, stage, officer, at="2026-09-15T09:00:00+00:00")
    return ticket, chain


# ---------------------------------------------------------------------------
# What has to be answered
# ---------------------------------------------------------------------------

class TestOpenFlags:

    def test_a_clean_application_raises_nothing(self, citizen, fabric, graph):
        """The common case must cost an officer no extra keystrokes."""
        ticket, _ = _ticket(citizen("4821"), fabric, graph)
        assert open_flags(ticket) == []

    def test_a_caste_contradiction_is_decisive(self, citizen, fabric, graph):
        ticket, _ = _ticket(citizen("5567"), fabric, graph)
        flags = open_flags(ticket)
        caste = [f for f in flags if f.label == "Caste entry"]
        assert caste and caste[0].severity == "decisive"

    def test_several_sources_are_grouped_into_one_flag(self, citizen, fabric, graph):
        """Four repositories contradicting one claim is one thing to answer."""
        ticket, _ = _ticket(citizen("7712"), fabric, graph)
        labels = [f.label for f in open_flags(ticket)]
        assert len(labels) == len(set(labels))

    def test_the_flag_says_how_many_disagree(self, citizen, fabric, graph):
        ticket, _ = _ticket(citizen("7712"), fabric, graph)
        multi = [f for f in open_flags(ticket) if len(f.sources) > 1]
        assert multi
        assert "repositories disagree" in multi[0].detail

    def test_a_linked_group_raises_a_fraud_flag(self, citizen, fabric, graph):
        ticket, _ = _ticket(citizen("1101"), fabric, graph)
        fraud = [f for f in open_flags(ticket) if f.key == "fraud:graph"]
        assert fraud and fraud[0].severity == "decisive"

    def test_decisive_flags_are_listed_first(self, citizen, fabric, graph):
        ticket, _ = _ticket(citizen("7712"), fabric, graph)
        flags = open_flags(ticket)
        severities = [f.severity for f in flags]
        assert severities == sorted(severities, key=lambda s: s != "decisive")


# ---------------------------------------------------------------------------
# Who may act
# ---------------------------------------------------------------------------

class TestCustody:

    def test_only_the_officer_holding_the_file_may_act(self, citizen, fabric, graph):
        ticket, _ = _ticket(citizen("4821"), fabric, graph)
        with pytest.raises(OverrideRefused) as exc:
            validate_action(ticket, OTHER, "forward", "", [])
        assert exc.value.field == "officer_id"
        assert "R. Ingle" in exc.value.message

    def test_a_closed_file_cannot_be_acted_on_again(self, citizen, fabric, graph):
        ticket, chain = _ticket(citizen("4821"), fabric, graph)
        perform(ticket, TALATHI, "reject", GOOD_REASON, chain=chain)
        with pytest.raises(OverrideRefused) as exc:
            validate_action(ticket, TALATHI, "forward", GOOD_REASON, [])
        assert "already closed" in exc.value.message

    def test_an_unknown_action_is_refused(self, citizen, fabric, graph):
        ticket, _ = _ticket(citizen("4821"), fabric, graph)
        with pytest.raises(OverrideRefused) as exc:
            validate_action(ticket, TALATHI, "rubber-stamp", "", [])
        assert exc.value.field == "action"


# ---------------------------------------------------------------------------
# The override itself
# ---------------------------------------------------------------------------

class TestOverride:

    def test_a_clean_file_forwards_with_no_ceremony(self, citizen, fabric, graph):
        ticket, chain = _ticket(citizen("4821"), fabric, graph)
        result = perform(ticket, TALATHI, "forward", chain=chain)
        assert result.overrode == []
        assert result.to_stage != Stage.TALATHI.value

    def test_a_flagged_file_cannot_be_waved_through(self, citizen, fabric, graph):
        """This is the whole point: silence is not an option."""
        ticket, _ = _ticket(citizen("5567"), fabric, graph)
        with pytest.raises(OverrideRefused) as exc:
            validate_action(ticket, TALATHI, "forward", GOOD_REASON, [])
        assert exc.value.field == "overrode"
        assert "Caste entry" in exc.value.message

    def test_every_decisive_flag_must_be_named(self, citizen, fabric, graph):
        ticket, _ = _ticket(citizen("7712"), fabric, graph)
        flags = open_flags(ticket)
        decisive = [f.key for f in flags if f.severity == "decisive"]
        assert len(decisive) >= 1
        # Name all but one.
        with pytest.raises(OverrideRefused) as exc:
            validate_action(ticket, TALATHI, "forward", GOOD_REASON,
                            decisive[:-1])
        assert exc.value.field == "overrode"

    def test_an_override_needs_a_reason(self, citizen, fabric, graph):
        ticket, _ = _ticket(citizen("5567"), fabric, graph)
        keys = [f.key for f in open_flags(ticket) if f.severity == "decisive"]
        with pytest.raises(OverrideRefused) as exc:
            validate_action(ticket, TALATHI, "forward", "ok", keys)
        assert exc.value.field == "remark"
        assert str(MIN_REASON_CHARS) in exc.value.message

    @pytest.mark.parametrize("stock", [
        "verified and found correct", "As per rules.", "no objection",
        "ALL DOCUMENTS VERIFIED",
    ])
    def test_a_stock_phrase_is_not_a_reason(self, stock, citizen, fabric, graph):
        ticket, _ = _ticket(citizen("5567"), fabric, graph)
        keys = [f.key for f in open_flags(ticket) if f.severity == "decisive"]
        with pytest.raises(OverrideRefused):
            validate_action(ticket, TALATHI, "forward", stock, keys)

    def test_a_substantive_reason_lets_the_file_move(self, citizen, fabric, graph):
        ticket, chain = _ticket(citizen("5567"), fabric, graph)
        keys = [f.key for f in open_flags(ticket) if f.severity == "decisive"]
        result = perform(ticket, TALATHI, "forward", GOOD_REASON, keys,
                         chain=chain)
        assert "Caste entry" in result.overrode
        assert result.to_stage != Stage.TALATHI.value

    def test_overriding_a_flag_that_was_never_raised_is_refused(
            self, citizen, fabric, graph):
        ticket, _ = _ticket(citizen("4821"), fabric, graph)
        with pytest.raises(OverrideRefused) as exc:
            validate_action(ticket, TALATHI, "forward", GOOD_REASON,
                            ["check:Invented"])
        assert "not raised on this file" in exc.value.message

    def test_refusing_a_file_needs_a_reason_the_citizen_can_appeal(
            self, citizen, fabric, graph):
        ticket, _ = _ticket(citizen("5567"), fabric, graph)
        with pytest.raises(OverrideRefused) as exc:
            validate_action(ticket, TALATHI, "reject", "no", [])
        assert exc.value.field == "remark"
        assert "appeal" in exc.value.message

    def test_refusing_does_not_require_answering_the_flags(
            self, citizen, fabric, graph):
        """Refusing a flagged application is the engine's own recommendation."""
        ticket, chain = _ticket(citizen("5567"), fabric, graph)
        result = perform(ticket, TALATHI, "reject", GOOD_REASON, chain=chain)
        assert result.closed


# ---------------------------------------------------------------------------
# The record it leaves
# ---------------------------------------------------------------------------

class TestRecord:

    def test_the_override_is_written_onto_the_stage_event(
            self, citizen, fabric, graph):
        ticket, chain = _ticket(citizen("5567"), fabric, graph)
        keys = [f.key for f in open_flags(ticket) if f.severity == "decisive"]
        perform(ticket, TALATHI, "forward", GOOD_REASON, keys, chain=chain)

        closed = [e for e in ticket.history if e.exited_at]
        acted = [e for e in closed if e.officer_id == TALATHI.officer_id]
        assert acted and acted[-1].overrode_flags
        assert acted[-1].remark == GOOD_REASON

    def test_the_action_is_sealed_into_the_chain(self, citizen, fabric, graph):
        ticket, chain = _ticket(citizen("5567"), fabric, graph)
        before = len(chain.entries)
        keys = [f.key for f in open_flags(ticket) if f.severity == "decisive"]
        result = perform(ticket, TALATHI, "forward", GOOD_REASON, keys,
                         chain=chain)

        assert len(chain.entries) == before + 1
        entry = chain.entries[-1]
        assert entry.actor_id == TALATHI.officer_id
        assert entry.payload["overrode"]
        assert entry.payload["remark"] == GOOD_REASON
        assert result.audit_hash == entry.entry_hash
        assert chain.verify() == (True, None)

    def test_a_plain_forward_is_recorded_too(self, citizen, fabric, graph):
        """A file's history should show who held it, not only what went wrong."""
        ticket, chain = _ticket(citizen("4821"), fabric, graph)
        before = len(chain.entries)
        perform(ticket, TALATHI, "forward", chain=chain)
        assert len(chain.entries) == before + 1
        assert chain.entries[-1].payload["overrode"] == []

    def test_an_override_shows_up_on_the_integrity_view(
            self, citizen, fabric, graph):
        """
        The deterrent is not the reason box. It is that the override is
        attributed and counted where a supervisor can see it.
        """
        from seva import analytics

        store = build_demo_store(volume=40)
        ticket = next(
            (t for t in store.all()
             if not t.is_closed and t.verification is not None
             and open_flags(t)),
            None,
        )
        if ticket is None:
            pytest.skip("no flagged open ticket in this sample")

        holder = next(e for e in reversed(ticket.history) if e.is_open)
        officer = Officer(holder.officer_id, holder.officer_name, "Talathi",
                          ticket.district, ticket.taluka)
        keys = [f.key for f in open_flags(ticket) if f.severity == "decisive"]
        perform(ticket, officer, "forward", GOOD_REASON, keys,
                chain=store.chain(ticket.seva_id))

        rows = analytics.override_watch(store, store.views(), min_overrides=1)
        assert any(r["officer_id"] == holder.officer_id for r in rows)
