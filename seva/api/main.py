"""
HTTP API
=========
Read endpoints for the governance dashboard, plus one write endpoint that runs
a fresh application through the verification engine.

The store is built once at startup and held in memory. Swapping it for a
database repository is a change to `seva.store` alone.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from seva import analytics
from seva.models import (
    Citizen, MatchStatus, ServiceType, SERVICE_DEPARTMENT, SLA_DAYS, Stage,
)
from seva.data.maharashtra import DISTRICTS, DIVISIONS, DISTRICT_BY_NAME
from seva.seva_id import parse as parse_seva_id, is_valid as seva_id_valid
from seva.store import build_demo_store
from seva.engine.orchestrator import assess
from seva.engine.audit import AuditChain
from seva.workflow.stages import STAGE_ROLE, chain_for
from seva.workflow.sla import read_clock

WEB_DIR = Path(__file__).resolve().parents[2] / "web"

app = FastAPI(
    title="Seva Governance API",
    description=(
        "Ticket-based governance for Maharashtra citizen services. "
        "All data in this deployment is synthetic."
    ),
    version="0.1.0",
)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

STORE = build_demo_store(volume=2400)


def _views():
    return STORE.views()


# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------

@app.get("/api/reference")
def reference() -> Dict[str, Any]:
    return {
        "divisions": DIVISIONS,
        "districts": [
            {"name": d.name, "code": d.code, "division": d.division,
             "talukas": d.talukas}
            for d in DISTRICTS
        ],
        "services": [
            {"name": s.value, "department": SERVICE_DEPARTMENT[s].value}
            for s in ServiceType
        ],
        "departments": sorted({d.value for d in SERVICE_DEPARTMENT.values()}),
    }


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@app.get("/api/summary")
def summary() -> Dict[str, Any]:
    return analytics.summary(_views())


@app.get("/api/districts")
def districts(department: Optional[str] = None) -> List[Dict[str, Any]]:
    return analytics.by_district(_views(), department=department)


@app.get("/api/districts/{district}/talukas")
def talukas(district: str, department: Optional[str] = None) -> List[Dict[str, Any]]:
    if district not in DISTRICT_BY_NAME:
        raise HTTPException(404, f"Unknown district: {district}")
    return analytics.by_taluka(_views(), district, department=department)


@app.get("/api/departments")
def departments() -> List[Dict[str, Any]]:
    return analytics.by_department(_views())


@app.get("/api/bottlenecks")
def bottlenecks() -> List[Dict[str, Any]]:
    return analytics.bottlenecks(_views())


@app.get("/api/overrides")
def overrides(min_overrides: int = 2) -> List[Dict[str, Any]]:
    return analytics.override_watch(STORE, _views(), min_overrides=min_overrides)


@app.get("/api/red-flags")
def red_flags(limit: int = 40, department: Optional[str] = None,
              district: Optional[str] = None) -> List[Dict[str, Any]]:
    return analytics.red_flag_queue(_views(), limit=limit,
                                    department=department, district=district)


@app.get("/api/trend")
def trend(weeks: int = 12) -> List[Dict[str, Any]]:
    return analytics.weekly_trend(_views(), weeks=weeks)


# ---------------------------------------------------------------------------
# Tickets
# ---------------------------------------------------------------------------

@app.get("/api/showcase")
def showcase() -> List[Dict[str, Any]]:
    """The tickets that were run through the real engine."""
    out = []
    for v in _views():
        if v.engine_verified:
            out.append(v.as_dict())
    out.sort(key=lambda r: r["seva_id"])
    return out


def _ticket_detail(seva_id: str) -> Dict[str, Any]:
    ticket = STORE.get(seva_id)
    if ticket is None:
        raise HTTPException(404, f"No ticket with Seva ID {seva_id}")

    view = STORE.view(ticket)
    clock = read_clock(ticket, chain_for(ticket.service))
    chain = STORE.chain(seva_id)

    detail: Dict[str, Any] = {
        **view.as_dict(),
        "village": ticket.village,
        "clock": clock.as_dict(),
        "chain": [
            {"stage": s.value, "role": STAGE_ROLE.get(s, "")}
            for s in chain_for(ticket.service)
        ],
        "history": [
            {"stage": e.stage.value, "role": STAGE_ROLE.get(e.stage, ""),
             "officer": e.officer_name, "officer_id": e.officer_id,
             "entered": e.entered_at, "exited": e.exited_at,
             "action": e.action, "remark": e.remark,
             "overrode": e.overrode_flags}
            for e in ticket.history
        ],
        "citizen_detail": {
            "full_name": ticket.citizen.full_name,
            "aadhaar_last4": ticket.citizen.aadhaar_last4,
            "dob": ticket.citizen.dob,
            "father_name": ticket.citizen.father_name,
            "grandfather_name": ticket.citizen.grandfather_name,
            "claimed_caste": ticket.citizen.claimed_caste,
            "claimed_income": ticket.citizen.claimed_income,
        },
    }

    report = ticket.verification
    if report is not None:
        detail["verification"] = {
            "verdict":   report.verdict.value,
            "dcs":       report.dcs,
            "wdcs":      report.wdcs,
            "identity":  report.identity_score,
            "fraud_risk": report.fraud_risk,
            "trust":     report.trust_score,
            "escalation": report.escalation_risk,
            "composite": report.composite,
            "audit_hash": report.audit_hash,
            "reasons":   report.reasons,
            "scores":    getattr(report, "scores").as_dict(),
            "consensus": getattr(report, "consensus").as_dict(),
            "fraud":     getattr(report, "fraud").as_dict(),
            "checks": [
                {"attribute": c.attribute, "source": c.source,
                 "claimed": c.claimed, "found": c.found,
                 "status": c.status.value, "note": c.note}
                for c in report.checks
            ],
        }
    if chain is not None:
        ok, broken = chain.verify()
        detail["audit"] = {
            "entries": chain.as_list(),
            "intact": ok,
            "broken_at": broken,
        }
    return detail


@app.get("/api/tickets/{seva_id}")
def ticket(seva_id: str) -> Dict[str, Any]:
    if not seva_id_valid(seva_id):
        raise HTTPException(
            400,
            f"{seva_id} is not a valid Seva ID. Check the number: a single "
            f"mistyped or transposed digit is rejected by the check digit.",
        )
    return _ticket_detail(seva_id)


@app.get("/api/tickets")
def list_tickets(district: Optional[str] = None,
                 department: Optional[str] = None,
                 flag: Optional[str] = None,
                 open_only: bool = True,
                 limit: int = Query(100, le=500)) -> List[Dict[str, Any]]:
    rows = _views()
    if open_only:
        rows = [v for v in rows if not v.ticket.is_closed]
    if district:
        rows = [v for v in rows if v.ticket.district == district]
    if department:
        rows = [v for v in rows if v.ticket.department.value == department]
    if flag:
        rows = [v for v in rows if v.flag.value == flag]
    rows.sort(key=lambda v: -v.age_days)
    return [v.as_dict() for v in rows[:limit]]


# ---------------------------------------------------------------------------
# Citizen submission
# ---------------------------------------------------------------------------

class Application(BaseModel):
    full_name:        str = Field(..., min_length=2)
    aadhaar_last4:    str = Field(..., min_length=4, max_length=4)
    dob:              Optional[str] = None
    father_name:      Optional[str] = None
    grandfather_name: Optional[str] = None
    district:         str
    taluka:           str
    village:          str = ""
    claimed_caste:    Optional[str] = None
    claimed_income:   Optional[int] = None
    mobile_last4:     Optional[str] = None
    service:          str = ServiceType.CASTE_CERTIFICATE.value


@app.post("/api/apply")
def apply(application: Application) -> Dict[str, Any]:
    """
    Run a submitted application through automated verification.

    Nothing here asks the applicant for a document issued by an officer. The
    engine reads the linked repositories itself and reports what they say.
    """
    if application.district not in DISTRICT_BY_NAME:
        raise HTTPException(400, f"Unknown district: {application.district}")
    try:
        service = next(s for s in ServiceType if s.value == application.service)
    except StopIteration:
        raise HTTPException(400, f"Unknown service: {application.service}")

    citizen = Citizen(
        full_name=application.full_name,
        aadhaar_last4=application.aadhaar_last4,
        dob=application.dob,
        father_name=application.father_name,
        grandfather_name=application.grandfather_name,
        district=application.district,
        taluka=application.taluka,
        village=application.village,
        claimed_caste=application.claimed_caste,
        claimed_income=application.claimed_income,
        mobile_last4=application.mobile_last4,
    )
    department = SERVICE_DEPARTMENT[service]
    seva_id = STORE.issuer.issue(department, application.district)
    chain = AuditChain(seva_id)
    report = assess(citizen, service, STORE.fabric, STORE.graph, chain)

    known = STORE.fabric.profile(application.aadhaar_last4) is not None
    return {
        "seva_id":  seva_id,
        "service":  service.value,
        "department": department.value,
        "sla_days": SLA_DAYS[service],
        "known_applicant": known,
        "note": (
            "" if known else
            "No linked records exist for this Aadhaar in the demo data, so "
            "every source reports 'not available'. Try one of the showcase "
            "applicants to see the engine resolve real evidence."
        ),
        "verdict":  report.verdict.value,
        "reasons":  report.reasons,
        "scores":   getattr(report, "scores").as_dict(),
        "consensus": getattr(report, "consensus").as_dict(),
        "fraud":    getattr(report, "fraud").as_dict(),
        "audit_hash": report.audit_hash,
        "checks": [
            {"attribute": c.attribute, "source": c.source,
             "claimed": c.claimed, "found": c.found,
             "status": c.status.value, "note": c.note}
            for c in report.checks
        ],
    }


@app.get("/api/validate/{seva_id}")
def validate(seva_id: str) -> Dict[str, Any]:
    """Check-digit validation, the same test the counter clerk's screen runs."""
    try:
        parsed = parse_seva_id(seva_id)
        return {"valid": True, **{k: (v.value if hasattr(v, "value") else v)
                                  for k, v in parsed.items()}}
    except ValueError as exc:
        return {"valid": False, "error": str(exc)}


@app.get("/api/health")
def health() -> Dict[str, Any]:
    return {"status": "ok", "tickets": len(STORE.all())}


# ---------------------------------------------------------------------------
# Static dashboard
# ---------------------------------------------------------------------------

if WEB_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(str(WEB_DIR / "index.html"))
