"""API surface."""
import pytest
from fastapi.testclient import TestClient

from seva.api.main import app

client = TestClient(app)


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_summary_is_internally_consistent():
    s = client.get("/api/summary").json()
    assert s["open"] + s["closed"] == s["total"]
    assert s["green"] + s["yellow"] + s["orange"] + s["red"] == s["open"]


def test_every_department_is_reported():
    names = {d["department"] for d in client.get("/api/departments").json()}
    assert names == {"Tahsil", "Revenue", "School & Education", "Forest"}


def test_all_districts_are_reported():
    rows = client.get("/api/districts").json()
    assert len(rows) == 36
    assert {r["division"] for r in rows} <= {
        "Konkan", "Pune", "Nashik", "Chhatrapati Sambhajinagar",
        "Amravati", "Nagpur",
    }


def test_taluka_drilldown():
    rows = client.get("/api/districts/Gondia/talukas").json()
    assert {r["taluka"] for r in rows} >= {"Gondia", "Amgaon", "Tirora"}


def test_unknown_district_is_rejected():
    assert client.get("/api/districts/Atlantis/talukas").status_code == 404


def test_showcase_tickets_carry_a_verdict():
    rows = client.get("/api/showcase").json()
    assert len(rows) == 9
    assert all(r["engine_verified"] and r["verdict"] for r in rows)


def test_ticket_detail_includes_reasoning_and_an_intact_chain():
    seva_id = client.get("/api/showcase").json()[0]["seva_id"]
    d = client.get(f"/api/tickets/{seva_id}").json()
    assert d["verification"]["reasons"]
    assert d["verification"]["checks"]
    assert d["audit"]["intact"] is True


def test_a_mistyped_seva_id_is_refused_before_lookup():
    r = client.get("/api/tickets/MH-THL-2026-GON-000999-9")
    assert r.status_code == 400
    assert "check digit" in r.json()["detail"].lower()


def test_validate_endpoint_reports_the_reason():
    assert client.get("/api/validate/MH-THL-2026-GON-000001-4").json()["valid"]
    bad = client.get("/api/validate/MH-THL-2026-GON-000001-5").json()
    assert not bad["valid"] and "check digit" in bad["error"].lower()


def test_apply_runs_the_engine_and_explains_itself():
    r = client.post("/api/apply", json={
        "full_name": "Prakash Dattatray Shinde", "aadhaar_last4": "5567",
        "dob": "1992-11-03", "father_name": "Dattatray Shinde",
        "grandfather_name": "Maruti Shinde", "district": "Beed",
        "taluka": "Georai", "claimed_caste": "SC-Mahar",
        "claimed_income": 120000,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["verdict"] == "ESCALATE"
    assert body["known_applicant"] is True
    assert any("1952" in reason for reason in body["reasons"])
    assert body["seva_id"].startswith("MH-THL-")


def test_apply_says_so_when_no_records_exist():
    r = client.post("/api/apply", json={
        "full_name": "Unknown Person", "aadhaar_last4": "0001",
        "district": "Pune", "taluka": "Haveli",
    }).json()
    assert r["known_applicant"] is False
    assert "no linked records" in r["note"].lower()


def test_apply_rejects_an_unknown_district():
    r = client.post("/api/apply", json={
        "full_name": "Test Person", "aadhaar_last4": "1234",
        "district": "Atlantis", "taluka": "Nowhere",
    })
    assert r.status_code == 400
