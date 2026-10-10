"""The officer desk over HTTP."""
import pytest
from fastapi.testclient import TestClient

from seva.api.main import app, STORE
from seva.workflow.overrides import open_flags

client = TestClient(app)

GOOD_REASON = (
    "Family known to this office since 1998; the 1952 entry was corrected "
    "by Tehsildar order dated 14 March 2019, copy on file."
)


def _flagged_open_ticket():
    """An open ticket the engine raised something on."""
    for ticket in STORE.all():
        if ticket.is_closed or ticket.verification is None:
            continue
        if any(f.severity == "decisive" for f in open_flags(ticket)):
            return ticket
    pytest.skip("no flagged open ticket in the seeded store")


def _clean_open_ticket():
    for ticket in STORE.all():
        if ticket.is_closed or ticket.verification is None:
            continue
        if not open_flags(ticket):
            return ticket
    pytest.skip("no clean open ticket in the seeded store")


def _holder(ticket):
    return next(e for e in reversed(ticket.history) if e.is_open)


# ---------------------------------------------------------------------------

def test_officers_are_listed():
    rows = client.get("/api/officers").json()
    assert rows
    assert {"officer_id", "name", "role", "district"} <= set(rows[0])


def test_officers_can_be_filtered_by_district():
    rows = client.get("/api/officers?district=Gondia").json()
    assert rows and all(r["district"] == "Gondia" for r in rows)


def test_an_unknown_district_is_rejected():
    assert client.get("/api/officers?district=Atlantis").status_code == 400


def test_flags_endpoint_reports_what_must_be_answered():
    ticket = _flagged_open_ticket()
    body = client.get(f"/api/tickets/{ticket.seva_id}/flags").json()
    assert body["decisive_count"] >= 1
    assert body["held_by"]["officer_id"] == _holder(ticket).officer_id
    assert all({"key", "label", "detail", "severity"} <= set(f)
               for f in body["flags"])


def test_flags_endpoint_rejects_a_mistyped_id():
    assert client.get("/api/tickets/MH-THL-2026-GON-000001-9/flags"
                      ).status_code == 400


def test_waving_a_flagged_file_through_is_refused():
    ticket = _flagged_open_ticket()
    r = client.post(
        f"/api/tickets/{ticket.seva_id}/action",
        json={"officer_id": _holder(ticket).officer_id,
              "action": "forward", "remark": GOOD_REASON, "overrode": []},
    )
    assert r.status_code == 422
    assert r.json()["field"] == "overrode"


def test_an_override_without_a_reason_is_refused():
    ticket = _flagged_open_ticket()
    keys = [f.key for f in open_flags(ticket) if f.severity == "decisive"]
    r = client.post(
        f"/api/tickets/{ticket.seva_id}/action",
        json={"officer_id": _holder(ticket).officer_id,
              "action": "forward", "remark": "ok", "overrode": keys},
    )
    assert r.status_code == 422
    assert r.json()["field"] == "remark"


def test_another_officer_cannot_act_on_the_file():
    ticket = _flagged_open_ticket()
    others = [o for o in STORE.officers.all_officers()
              if o.officer_id != _holder(ticket).officer_id]
    r = client.post(
        f"/api/tickets/{ticket.seva_id}/action",
        json={"officer_id": others[0].officer_id,
              "action": "forward", "remark": GOOD_REASON, "overrode": []},
    )
    assert r.status_code == 422
    assert r.json()["field"] == "officer_id"


def test_an_unknown_officer_is_not_found():
    ticket = _flagged_open_ticket()
    r = client.post(
        f"/api/tickets/{ticket.seva_id}/action",
        json={"officer_id": "NO-SUCH-001", "action": "forward"},
    )
    assert r.status_code == 404


def test_a_clean_file_forwards_and_returns_the_updated_ticket():
    ticket = _clean_open_ticket()
    before = ticket.current_stage.value
    r = client.post(
        f"/api/tickets/{ticket.seva_id}/action",
        json={"officer_id": _holder(ticket).officer_id, "action": "forward"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["from_stage"] == before
    assert body["overrode"] == []
    assert body["ticket"]["seva_id"] == ticket.seva_id
    assert body["ticket"]["audit"]["intact"] is True


def test_an_override_is_recorded_and_the_chain_stays_intact():
    ticket = _flagged_open_ticket()
    keys = [f.key for f in open_flags(ticket) if f.severity == "decisive"]
    r = client.post(
        f"/api/tickets/{ticket.seva_id}/action",
        json={"officer_id": _holder(ticket).officer_id, "action": "forward",
              "remark": GOOD_REASON, "overrode": keys},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["overrode"]
    assert body["audit_hash"]

    detail = body["ticket"]
    assert detail["audit"]["intact"] is True
    overridden = [h for h in detail["history"] if h["overrode"]]
    assert overridden and overridden[-1]["remark"] == GOOD_REASON
