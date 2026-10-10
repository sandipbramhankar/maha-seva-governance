"""
Ticket store
=============
Holds every Seva ticket and answers the questions the dashboard asks.

Two kinds of ticket live here, and the difference is deliberate:

  showcase tickets   the nine profiles in `mock_sources`, each run through the
                     real engine. indicer resolves the names, the fraud graph
                     runs, the scores are computed. These are the tickets you
                     open to see how a decision was reached.

  volume tickets     statewide background load. The workflow, the officer
                     assignment and the Right to Services clock are real and
                     computed. The verification scores are sampled from
                     distributions rather than derived from invented source
                     records, because manufacturing 2,500 plausible Aadhaar,
                     land and subsidy histories would add nothing a reviewer
                     could check.

Every ticket carries `engine_verified` so the dashboard can say which is which,
and no aggregate is presented as a measurement of real service delivery.

Replace this class with a database repository and nothing above it changes.
"""

from __future__ import annotations

import random
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional

from seva.models import (
    Citizen, Department, Flag, SevaTicket, ServiceType, Stage,
    SERVICE_DEPARTMENT, Verdict, utc_now_iso,
)
from seva.seva_id import SevaIdIssuer
from seva.data.maharashtra import DISTRICTS, DISTRICT_BY_NAME, district_code
from seva.data.officers import OfficerRegistry
from seva.data.mock_sources import DataFabric, PROFILES
from seva.engine.fraud import FraudGraph
from seva.engine.orchestrator import assess
from seva.engine.audit import AuditChain
from seva.workflow.stages import (
    Officer, chain_for, open_stage, close_stage, STAGE_ROLE,
)
from seva.workflow.sla import read_clock

#: Rough population in lakhs, used only to weight how many requests a district
#: generates. A district with ten times the people files roughly ten times the
#: applications, which is what makes a raw pending count misleading and a
#: per-capita or per-officer view necessary.
POPULATION_LAKH: Dict[str, float] = {
    "Thane": 110, "Pune": 94, "Mumbai Suburban": 94, "Nashik": 61,
    "Nagpur": 47, "Ahilyanagar": 45, "Solapur": 43, "Jalgaon": 42,
    "Kolhapur": 39, "Chhatrapati Sambhajinagar": 37, "Nanded": 34,
    "Mumbai City": 31, "Palghar": 30, "Satara": 30, "Amravati": 29,
    "Sangli": 28, "Yavatmal": 28, "Raigad": 26, "Buldhana": 26, "Beed": 26,
    "Latur": 25, "Chandrapur": 22, "Dhule": 20, "Jalna": 19, "Parbhani": 18,
    "Akola": 18, "Dharashiv": 16, "Nandurbar": 16, "Ratnagiri": 16,
    "Gondia": 13, "Wardha": 13, "Bhandara": 12, "Washim": 12, "Hingoli": 12,
    "Gadchiroli": 11, "Sindhudurg": 8,
}

#: Share of requests by service. Caste, income and domicile certificates
#: dominate the counter at any tehsil office in Maharashtra.
SERVICE_MIX: List[tuple[ServiceType, float]] = [
    (ServiceType.INCOME_CERTIFICATE,   0.26),
    (ServiceType.CASTE_CERTIFICATE,    0.19),
    (ServiceType.DOMICILE_CERTIFICATE, 0.17),
    (ServiceType.SEVEN_TWELVE_EXTRACT, 0.12),
    (ServiceType.SCHOLARSHIP,          0.08),
    (ServiceType.LAND_MUTATION,        0.06),
    (ServiceType.CASTE_VALIDITY,       0.05),
    (ServiceType.SCHOOL_TRANSFER,      0.03),
    (ServiceType.TREE_FELLING_PERMIT,  0.025),
    (ServiceType.FOREST_LAND_NOC,      0.015),
]

#: Districts where the demo shows a backlog, so the dashboard has something to
#: escalate. Multiplier applied to how long files sit.
STRESSED_DISTRICTS: Dict[str, float] = {
    "Gadchiroli": 2.3, "Nandurbar": 2.1, "Beed": 1.9,
    "Yavatmal": 1.8, "Dharashiv": 1.7, "Hingoli": 1.6,
}

_GIVEN = ["Ramesh", "Sunita", "Amol", "Prachi", "Ganesh", "Rekha", "Nilesh",
          "Sapna", "Vilas", "Madhuri", "Kiran", "Pooja", "Sachin", "Asha",
          "Rohit", "Varsha", "Datta", "Sheetal", "Akash", "Mangal"]
_SUR = ["Meshram", "Patil", "Kamble", "Jadhav", "Pawar", "Shinde", "Thakre",
        "Wankhede", "Gaikwad", "Chavan", "Rathod", "Madavi", "Sonawane",
        "Deshmukh", "Bhosale", "More", "Ingle", "Dhotre", "Raut", "Tekam"]


@dataclass
class TicketView:
    """A ticket flattened for the dashboard, with its clock already read."""
    ticket: SevaTicket
    flag: Flag
    reason: str
    age_days: float
    stage_days: float
    breached: bool
    engine_verified: bool
    verdict: Optional[str]
    officer_name: str
    officer_id: str

    def as_dict(self) -> Dict[str, object]:
        t = self.ticket
        return {
            "seva_id":    t.seva_id,
            "service":    t.service.value,
            "department": t.department.value,
            "citizen":    t.citizen.full_name,
            "district":   t.district,
            "taluka":     t.taluka,
            "stage":      t.current_stage.value,
            "role":       STAGE_ROLE.get(t.current_stage, ""),
            "officer":    self.officer_name,
            "officer_id": self.officer_id,
            "submitted":  t.submitted_at[:10],
            "age_days":   round(self.age_days, 1),
            "stage_days": round(self.stage_days, 1),
            "sla_days":   t.sla_days,
            "flag":       self.flag.value,
            "reason":     self.reason,
            "breached":   self.breached,
            "closed":     t.is_closed,
            "outcome":    t.outcome,
            "verdict":    self.verdict,
            "engine_verified": self.engine_verified,
        }


class TicketStore:
    def __init__(self, seed: int = 20261009) -> None:
        self._rng = random.Random(seed)
        self._tickets: Dict[str, SevaTicket] = {}
        self._chains: Dict[str, AuditChain] = {}
        self._engine_verified: set[str] = set()
        self._verdicts: Dict[str, str] = {}
        self.issuer = SevaIdIssuer()
        self.officers = OfficerRegistry(seed=seed)
        self.fabric = DataFabric()
        self.graph = FraudGraph(self.fabric, filed_on={
            "1101": "2026-09-02", "1102": "2026-09-04", "1103": "2026-09-09",
        })

    # -- access ------------------------------------------------------------
    def get(self, seva_id: str) -> Optional[SevaTicket]:
        return self._tickets.get(seva_id)

    def chain(self, seva_id: str) -> Optional[AuditChain]:
        return self._chains.get(seva_id)

    def all(self) -> List[SevaTicket]:
        return list(self._tickets.values())

    def view(self, ticket: SevaTicket, now: Optional[datetime] = None) -> TicketView:
        clock = read_clock(ticket, chain_for(ticket.service), now=now)
        officer_name, officer_id = "Unassigned", ""
        for ev in reversed(ticket.history):
            if ev.is_open:
                officer_name, officer_id = ev.officer_name, ev.officer_id
                break
        else:
            if ticket.history:
                officer_name = ticket.history[-1].officer_name
                officer_id = ticket.history[-1].officer_id
        return TicketView(
            ticket=ticket, flag=clock.flag, reason=clock.reason,
            age_days=clock.age_days, stage_days=clock.stage_days,
            breached=clock.breached,
            engine_verified=ticket.seva_id in self._engine_verified,
            verdict=self._verdicts.get(ticket.seva_id),
            officer_name=officer_name, officer_id=officer_id,
        )

    def views(self, now: Optional[datetime] = None) -> List[TicketView]:
        now = now or datetime.now(timezone.utc)
        return [self.view(t, now) for t in self._tickets.values()]

    # -- creation ----------------------------------------------------------
    def _place(self, ticket: SevaTicket, submitted: datetime,
               stress: float, now: datetime) -> None:
        """
        Walk the ticket through its chain to wherever it has realistically
        reached by `now`, opening and closing each desk with real timestamps.
        """
        chain = chain_for(ticket.service)
        dcode = district_code(ticket.district)
        per_stage = ticket.sla_days / max(
            len([s for s in chain if s not in (
                Stage.SUBMITTED, Stage.AUTO_VERIFICATION,
                Stage.ISSUED, Stage.REJECTED)]), 1)

        cursor = submitted
        sys_officer = Officer("SYSTEM", "Automated Verification", "System",
                              ticket.district)
        open_stage(ticket, Stage.AUTO_VERIFICATION, sys_officer,
                   at=cursor.isoformat())
        cursor += timedelta(seconds=4)
        close_stage(ticket, action="forwarded",
                    remark="Cross-source verification complete.",
                    at=cursor.isoformat())

        human_stages = [s for s in chain
                        if s not in (Stage.SUBMITTED, Stage.AUTO_VERIFICATION,
                                     Stage.ISSUED, Stage.REJECTED)]
        for stage in human_stages:
            officer = self.officers.officer_for(dcode, stage, ticket.taluka)
            if cursor >= now:
                break
            open_stage(ticket, stage, officer, at=cursor.isoformat())
            dwell = max(0.2, self._rng.gauss(per_stage * 0.75, per_stage * 0.5)) * stress
            exit_at = cursor + timedelta(days=dwell)
            if exit_at >= now:
                return                      # still sitting on this desk
            overrode: List[str] = []
            if self._rng.random() < 0.07:
                overrode = ["caste_entry_mismatch"]
            close_stage(ticket, action="forwarded",
                        remark="Verified and forwarded.", overrode=overrode,
                        at=exit_at.isoformat())
            cursor = exit_at

        if cursor < now:
            ticket.current_stage = Stage.ISSUED
            ticket.closed_at = cursor.isoformat()
            ticket.outcome = "issued"

    def seed_volume(self, total: int = 2400,
                    now: Optional[datetime] = None) -> int:
        """Generate statewide background load."""
        now = now or datetime.now(timezone.utc)
        weights = [POPULATION_LAKH.get(d.name, 15) for d in DISTRICTS]
        services = [s for s, _ in SERVICE_MIX]
        service_w = [w for _, w in SERVICE_MIX]

        made = 0
        for _ in range(total):
            district = self._rng.choices(DISTRICTS, weights=weights, k=1)[0]
            taluka = self._rng.choice(district.talukas)
            service = self._rng.choices(services, weights=service_w, k=1)[0]
            stress = STRESSED_DISTRICTS.get(district.name, 1.0)

            # A service in steady state receives a roughly constant number of
            # requests each week. Sampling ages uniformly over the window
            # reproduces that; a half-normal would pile every filing into the
            # last fortnight and show a backlog that is an artefact of the
            # generator rather than anything about the service.
            age = self._rng.uniform(0, 118)
            submitted = now - timedelta(days=age)

            citizen = Citizen(
                full_name=f"{self._rng.choice(_GIVEN)} {self._rng.choice(_SUR)}",
                aadhaar_last4=f"{self._rng.randint(1000, 9999)}",
                district=district.name, taluka=taluka,
            )
            department = SERVICE_DEPARTMENT[service]
            seva_id = self.issuer.issue(department, district.name,
                                        year=submitted.year)
            ticket = SevaTicket(
                seva_id=seva_id, service=service, department=department,
                citizen=citizen, district=district.name, taluka=taluka,
                submitted_at=submitted.isoformat(),
            )
            self._place(ticket, submitted, stress, now)
            self._tickets[seva_id] = ticket
            made += 1
        return made

    def seed_showcase(self, now: Optional[datetime] = None) -> List[str]:
        """
        The nine profiles, each run through the real engine.

        These are the tickets a reviewer opens to check the system's reasoning.
        """
        now = now or datetime.now(timezone.utc)
        ages = {"4821": 6, "9034": 11, "5567": 23, "7712": 34,
                "3390": 17, "1101": 9, "1102": 7, "1103": 4, "6648": 2}
        created: List[str] = []

        for profile in PROFILES:
            claim = dict(profile.claim)
            citizen = Citizen(aadhaar_last4=profile.aadhaar_last4, **claim)
            service = ServiceType.CASTE_CERTIFICATE
            department = SERVICE_DEPARTMENT[service]
            district = citizen.district or "Gondia"
            taluka = citizen.taluka or DISTRICT_BY_NAME[district].talukas[0]

            submitted = now - timedelta(days=ages.get(profile.aadhaar_last4, 10))
            seva_id = self.issuer.issue(department, district, year=submitted.year)
            ticket = SevaTicket(
                seva_id=seva_id, service=service, department=department,
                citizen=citizen, district=district, taluka=taluka,
                village=citizen.village or "",
                submitted_at=submitted.isoformat(),
            )

            chain = AuditChain(seva_id)
            report = assess(citizen, service, self.fabric, self.graph, chain)
            ticket.verification = report

            dcode = district_code(district)
            sys_officer = Officer("SYSTEM", "Automated Verification",
                                  "System", district)
            open_stage(ticket, Stage.AUTO_VERIFICATION, sys_officer,
                       at=submitted.isoformat())
            close_stage(ticket, action="forwarded",
                        remark=f"Automated verdict: {report.verdict.value}.",
                        at=(submitted + timedelta(seconds=4)).isoformat())

            # A clean pass moves on; anything else waits for a person.
            stage = Stage.TALATHI
            officer = self.officers.officer_for(dcode, stage, taluka)
            open_stage(ticket, stage, officer,
                       at=(submitted + timedelta(seconds=5)).isoformat())
            if report.verdict is Verdict.APPROVE:
                moved = submitted + timedelta(days=1.5)
                if moved < now:
                    close_stage(ticket, action="forwarded",
                                remark="No mismatch reported; forwarded.",
                                at=moved.isoformat())
                    nxt = Stage.CIRCLE_OFFICER
                    open_stage(ticket, nxt,
                               self.officers.officer_for(dcode, nxt, taluka),
                               at=moved.isoformat())

            self._tickets[seva_id] = ticket
            self._chains[seva_id] = chain
            self._engine_verified.add(seva_id)
            self._verdicts[seva_id] = report.verdict.value
            created.append(seva_id)
        return created


#: Typical spread of ticket ages per service, in days.
SLA_SPREAD: Dict[ServiceType, float] = {
    ServiceType.SEVEN_TWELVE_EXTRACT:  6,
    ServiceType.SCHOOL_TRANSFER:      10,
    ServiceType.INCOME_CERTIFICATE:   22,
    ServiceType.DOMICILE_CERTIFICATE: 22,
    ServiceType.CASTE_CERTIFICATE:    40,
    ServiceType.SCHOLARSHIP:          55,
    ServiceType.LAND_MUTATION:        55,
    ServiceType.CASTE_VALIDITY:      100,
    ServiceType.TREE_FELLING_PERMIT:  70,
    ServiceType.FOREST_LAND_NOC:     110,
}


def build_demo_store(volume: int = 2400) -> TicketStore:
    store = TicketStore()
    store.seed_volume(volume)
    store.seed_showcase()
    return store
