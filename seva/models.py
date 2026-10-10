"""
Core domain models
===================
Plain dataclasses so the engine runs without a web framework. The API layer
converts these to JSON at the boundary.

Vocabulary follows Maharashtra revenue practice: a citizen request becomes a
Seva ticket, moves through stages owned by named officers, and is bound by the
Maharashtra Right to Public Services Act, 2015 clock.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class Department(str, Enum):
    TAHSIL    = "Tahsil"
    REVENUE   = "Revenue"
    EDUCATION = "School & Education"
    FOREST    = "Forest"


class ServiceType(str, Enum):
    CASTE_CERTIFICATE       = "Caste Certificate"
    CASTE_VALIDITY          = "Caste Validity Certificate"
    INCOME_CERTIFICATE      = "Income Certificate"
    DOMICILE_CERTIFICATE    = "Domicile Certificate"
    SCHOLARSHIP             = "Post-Matric Scholarship"
    SCHOOL_TRANSFER         = "School Transfer Certificate"
    LAND_MUTATION           = "Land Record Mutation"
    SEVEN_TWELVE_EXTRACT    = "7/12 Extract"
    TREE_FELLING_PERMIT     = "Tree Felling Permission"
    FOREST_LAND_NOC         = "Forest Land NOC"


class Stage(str, Enum):
    SUBMITTED            = "Submitted"
    AUTO_VERIFICATION    = "Automated Verification"
    TALATHI              = "Talathi Verification"
    CIRCLE_OFFICER       = "Circle Officer Review"
    NAIB_TEHSILDAR       = "Naib Tehsildar Inquiry"
    TEHSILDAR            = "Tehsildar Approval"
    SDO_REVIEW           = "Sub-Divisional Officer Review"
    SCRUTINY_COMMITTEE   = "Caste Scrutiny Committee"
    RANGE_FOREST_OFFICER = "Range Forest Officer"
    EDUCATION_OFFICER    = "Education Officer"
    ISSUED               = "Certificate Issued"
    REJECTED             = "Rejected"


TERMINAL_STAGES = {Stage.ISSUED, Stage.REJECTED}


class Flag(str, Enum):
    """Severity of the SLA / integrity signal attached to a ticket."""
    GREEN  = "green"    # within time, no mismatch
    YELLOW = "yellow"   # half the SLA consumed, or a minor mismatch
    ORANGE = "orange"   # SLA nearly breached, or several mismatches
    RED    = "red"      # SLA breached, or a disqualifying mismatch


class MatchStatus(str, Enum):
    MATCH         = "match"
    MISMATCH      = "mismatch"
    NOT_AVAILABLE = "not_available"


class Verdict(str, Enum):
    APPROVE     = "APPROVE"
    INVESTIGATE = "INVESTIGATE"
    ESCALATE    = "ESCALATE"
    REJECT      = "REJECT"


# Statutory clock under the Maharashtra Right to Public Services Act, 2015.
SLA_DAYS: Dict[ServiceType, int] = {
    ServiceType.CASTE_CERTIFICATE:    30,
    ServiceType.CASTE_VALIDITY:       90,
    ServiceType.INCOME_CERTIFICATE:   15,
    ServiceType.DOMICILE_CERTIFICATE: 15,
    ServiceType.SCHOLARSHIP:          45,
    ServiceType.SCHOOL_TRANSFER:       7,
    ServiceType.LAND_MUTATION:        45,
    ServiceType.SEVEN_TWELVE_EXTRACT:  3,
    ServiceType.TREE_FELLING_PERMIT:  60,
    ServiceType.FOREST_LAND_NOC:      90,
}

SERVICE_DEPARTMENT: Dict[ServiceType, Department] = {
    ServiceType.CASTE_CERTIFICATE:    Department.TAHSIL,
    ServiceType.CASTE_VALIDITY:       Department.TAHSIL,
    ServiceType.INCOME_CERTIFICATE:   Department.TAHSIL,
    ServiceType.DOMICILE_CERTIFICATE: Department.TAHSIL,
    ServiceType.SCHOLARSHIP:          Department.EDUCATION,
    ServiceType.SCHOOL_TRANSFER:      Department.EDUCATION,
    ServiceType.LAND_MUTATION:        Department.REVENUE,
    ServiceType.SEVEN_TWELVE_EXTRACT: Department.REVENUE,
    ServiceType.TREE_FELLING_PERMIT:  Department.FOREST,
    ServiceType.FOREST_LAND_NOC:      Department.FOREST,
}


# ---------------------------------------------------------------------------
# Citizen and the documents they actually hold
# ---------------------------------------------------------------------------

@dataclass
class Citizen:
    """
    What the applicant supplies. Deliberately limited to documents a citizen
    already possesses: nothing here requires a visit to a government officer.
    """
    full_name:      str
    aadhaar_last4:  str                      # never store the full number
    dob:            Optional[str] = None     # ISO date
    father_name:    Optional[str] = None
    grandfather_name: Optional[str] = None
    mother_name:    Optional[str] = None
    address:        Optional[str] = None
    district:       Optional[str] = None
    taluka:         Optional[str] = None
    village:        Optional[str] = None
    mobile_last4:   Optional[str] = None
    claimed_caste:  Optional[str] = None     # e.g. "SC-Mahar", "OBC-Kunbi"
    claimed_income: Optional[int] = None     # annual, rupees

    def to_cir(self) -> Dict[str, Any]:
        """Common Internal Representation consumed by the indicer pipeline."""
        return {
            "full_name":  self.full_name,
            "dob":        self.dob,
            "address":    self.address,
            "identifier": self.aadhaar_last4,
        }


# ---------------------------------------------------------------------------
# Verification artefacts
# ---------------------------------------------------------------------------

@dataclass
class AttributeCheck:
    """One attribute compared between the citizen's claim and one source."""
    attribute: str
    source:    str
    claimed:   Optional[str]
    found:     Optional[str]
    status:    MatchStatus
    weight:    float = 0.10
    note:      str = ""

    @property
    def is_mismatch(self) -> bool:
        return self.status is MatchStatus.MISMATCH


@dataclass
class VerificationReport:
    """Output of the cross-source consistency engine for one ticket."""
    checks:            List[AttributeCheck] = field(default_factory=list)
    dcs:               float = 0.0    # Cross-Department Consistency Score, 0-100
    wdcs:              float = 0.0    # weighted variant, 0-1
    identity_score:    float = 0.0    # indicer name-match confidence, 0-1
    fraud_risk:        float = 0.0    # 0-100, higher is worse
    trust_score:       float = 0.0    # Governance Trust Score, 0-100
    escalation_risk:   float = 0.0    # 0-1
    composite:         float = 0.0    # Composite Governance Score, 0-1
    verdict:           Verdict = Verdict.INVESTIGATE
    reasons:           List[str] = field(default_factory=list)
    audit_hash:        str = ""

    @property
    def mismatches(self) -> List[AttributeCheck]:
        return [c for c in self.checks if c.is_mismatch]


# ---------------------------------------------------------------------------
# Workflow
# ---------------------------------------------------------------------------

@dataclass
class StageEvent:
    """One movement of the ticket, recorded immutably."""
    stage:       Stage
    officer_id:  str
    officer_name: str
    entered_at:  str
    exited_at:   Optional[str] = None
    action:      Optional[str] = None     # "forwarded", "approved", "returned"
    remark:      str = ""
    overrode_flags: List[str] = field(default_factory=list)

    @property
    def is_open(self) -> bool:
        return self.exited_at is None


@dataclass
class SevaTicket:
    """
    The unit of accountability. One citizen request, one identifier, tracked
    from submission to the certificate reaching the citizen's hand.
    """
    seva_id:      str
    service:      ServiceType
    department:   Department
    citizen:      Citizen
    district:     str
    taluka:       str
    village:      str = ""
    submitted_at: str = ""
    current_stage: Stage = Stage.SUBMITTED
    history:      List[StageEvent] = field(default_factory=list)
    verification: Optional[VerificationReport] = None
    closed_at:    Optional[str] = None
    outcome:      Optional[str] = None     # "issued" | "rejected"

    # -- derived -----------------------------------------------------------
    @property
    def sla_days(self) -> int:
        return SLA_DAYS[self.service]

    @property
    def is_closed(self) -> bool:
        return self.current_stage in TERMINAL_STAGES

    def age_days(self, now: Optional[datetime] = None) -> float:
        """Calendar days since submission, frozen at closure."""
        now = now or datetime.now(timezone.utc)
        start = datetime.fromisoformat(self.submitted_at)
        end = datetime.fromisoformat(self.closed_at) if self.closed_at else now
        return (end - start).total_seconds() / 86400.0

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["sla_days"] = self.sla_days
        d["age_days"] = round(self.age_days(), 2)
        return d


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
