"""
Workflow
=========
The desks a request actually crosses, and the rule for moving between them.

The stage chains below are the real ones. A caste certificate in Maharashtra is
not one approval: the Talathi verifies the village record, the Circle Officer
checks it, the Naib Tehsildar holds an inquiry, and the Sub-Divisional Officer
issues. Validity is a separate body again. Every one of those desks is a place
a file can sit, and until each is a tracked stage with its own clock, nobody
can say where the delay is.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from seva.models import (
    ServiceType, Stage, StageEvent, SevaTicket, Verdict, utc_now_iso,
)

STAGE_CHAINS: Dict[ServiceType, List[Stage]] = {
    ServiceType.CASTE_CERTIFICATE: [
        Stage.SUBMITTED, Stage.AUTO_VERIFICATION, Stage.TALATHI,
        Stage.CIRCLE_OFFICER, Stage.NAIB_TEHSILDAR, Stage.SDO_REVIEW,
        Stage.ISSUED,
    ],
    ServiceType.CASTE_VALIDITY: [
        Stage.SUBMITTED, Stage.AUTO_VERIFICATION, Stage.TALATHI,
        Stage.NAIB_TEHSILDAR, Stage.SCRUTINY_COMMITTEE, Stage.ISSUED,
    ],
    ServiceType.INCOME_CERTIFICATE: [
        Stage.SUBMITTED, Stage.AUTO_VERIFICATION, Stage.TALATHI,
        Stage.NAIB_TEHSILDAR, Stage.TEHSILDAR, Stage.ISSUED,
    ],
    ServiceType.DOMICILE_CERTIFICATE: [
        Stage.SUBMITTED, Stage.AUTO_VERIFICATION, Stage.TALATHI,
        Stage.NAIB_TEHSILDAR, Stage.TEHSILDAR, Stage.ISSUED,
    ],
    ServiceType.SCHOLARSHIP: [
        Stage.SUBMITTED, Stage.AUTO_VERIFICATION, Stage.EDUCATION_OFFICER,
        Stage.ISSUED,
    ],
    ServiceType.SCHOOL_TRANSFER: [
        Stage.SUBMITTED, Stage.AUTO_VERIFICATION, Stage.EDUCATION_OFFICER,
        Stage.ISSUED,
    ],
    ServiceType.LAND_MUTATION: [
        Stage.SUBMITTED, Stage.AUTO_VERIFICATION, Stage.TALATHI,
        Stage.CIRCLE_OFFICER, Stage.TEHSILDAR, Stage.ISSUED,
    ],
    ServiceType.SEVEN_TWELVE_EXTRACT: [
        Stage.SUBMITTED, Stage.AUTO_VERIFICATION, Stage.TALATHI, Stage.ISSUED,
    ],
    ServiceType.TREE_FELLING_PERMIT: [
        Stage.SUBMITTED, Stage.AUTO_VERIFICATION, Stage.RANGE_FOREST_OFFICER,
        Stage.ISSUED,
    ],
    ServiceType.FOREST_LAND_NOC: [
        Stage.SUBMITTED, Stage.AUTO_VERIFICATION, Stage.RANGE_FOREST_OFFICER,
        Stage.SDO_REVIEW, Stage.ISSUED,
    ],
}

#: Who sits at each desk, by designation.
STAGE_ROLE: Dict[Stage, str] = {
    Stage.SUBMITTED:            "Citizen",
    Stage.AUTO_VERIFICATION:    "System",
    Stage.TALATHI:              "Talathi",
    Stage.CIRCLE_OFFICER:       "Circle Officer",
    Stage.NAIB_TEHSILDAR:       "Naib Tehsildar",
    Stage.TEHSILDAR:            "Tehsildar",
    Stage.SDO_REVIEW:           "Sub-Divisional Officer",
    Stage.SCRUTINY_COMMITTEE:   "Caste Scrutiny Committee",
    Stage.RANGE_FOREST_OFFICER: "Range Forest Officer",
    Stage.EDUCATION_OFFICER:    "Education Officer",
    Stage.ISSUED:               "Issued",
    Stage.REJECTED:             "Rejected",
}


def chain_for(service: ServiceType) -> List[Stage]:
    return list(STAGE_CHAINS.get(service, [
        Stage.SUBMITTED, Stage.AUTO_VERIFICATION, Stage.ISSUED,
    ]))


def next_stage(service: ServiceType, current: Stage) -> Optional[Stage]:
    chain = chain_for(service)
    if current not in chain:
        return None
    i = chain.index(current)
    return chain[i + 1] if i + 1 < len(chain) else None


@dataclass
class Officer:
    officer_id: str
    name:       str
    role:       str
    district:   str
    taluka:     str = ""


def open_stage(ticket: SevaTicket, stage: Stage, officer: Officer,
               at: Optional[str] = None) -> StageEvent:
    """Place the ticket on a desk and start that desk's clock."""
    event = StageEvent(
        stage=stage,
        officer_id=officer.officer_id,
        officer_name=officer.name,
        entered_at=at or utc_now_iso(),
    )
    ticket.history.append(event)
    ticket.current_stage = stage
    return event


def close_stage(ticket: SevaTicket, action: str, remark: str = "",
                overrode: Optional[List[str]] = None,
                at: Optional[str] = None) -> Optional[StageEvent]:
    """
    Close the open desk.

    `overrode` names the flags the officer waved through. That list is the
    point of the whole system: an officer may always override the machine, but
    the override is recorded against their name and counted.
    """
    for event in reversed(ticket.history):
        if event.is_open:
            event.exited_at = at or utc_now_iso()
            event.action = action
            event.remark = remark
            event.overrode_flags = list(overrode or [])
            return event
    return None


def advance(ticket: SevaTicket, officer: Officer, remark: str = "",
            overrode: Optional[List[str]] = None,
            at: Optional[str] = None) -> Optional[Stage]:
    """Move the ticket to the next desk in its chain."""
    close_stage(ticket, action="forwarded", remark=remark,
                overrode=overrode, at=at)
    nxt = next_stage(ticket.service, ticket.current_stage)
    if nxt is None:
        return None
    if nxt in (Stage.ISSUED, Stage.REJECTED):
        ticket.current_stage = nxt
        ticket.closed_at = at or utc_now_iso()
        ticket.outcome = "issued" if nxt is Stage.ISSUED else "rejected"
        return nxt
    open_stage(ticket, nxt, officer, at=at)
    return nxt


def reject(ticket: SevaTicket, officer: Officer, reason: str,
           at: Optional[str] = None) -> None:
    close_stage(ticket, action="rejected", remark=reason, at=at)
    ticket.current_stage = Stage.REJECTED
    ticket.closed_at = at or utc_now_iso()
    ticket.outcome = "rejected"


def requires_human(verdict: Verdict) -> bool:
    """Only a clean automated pass may skip a desk."""
    return verdict is not Verdict.APPROVE
