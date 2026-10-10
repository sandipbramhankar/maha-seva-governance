"""
Governance scoring
===================
Implements the score stack as specified in the system design figures:

  Fig 3  Governance Trust Score        GTS = Sum(Wi x Si) - (W_frs x FRS)
  Fig 7  Adaptive Human Escalation     ERS = Sum(Wi x Fi)
  Fig 8  Composite Governance Decision CGS = Sum(Wi x Si)

Every weight and threshold below is policy, held in one place so a department
can retune it by notification. The value in force is written into each ticket's
audit record, so a decision taken last year can still be explained with the
parameters that applied then.

The scores never decide alone. They order the queue and they justify an
escalation; a human still signs the certificate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from seva.models import (
    AttributeCheck, MatchStatus, ServiceType, Verdict,
)

# ---------------------------------------------------------------------------
# Fig 3 — Governance Trust Score
# ---------------------------------------------------------------------------

GTS_WEIGHTS: Dict[str, float] = {
    "ITS": 0.20,   # identity trust
    "DTS": 0.15,   # document trust
    "DCS": 0.20,   # cross-department consistency
    "PCS": 0.15,   # policy compliance
    "CRS": 0.10,   # citizen reliability
    "HBS": 0.10,   # historical behaviour
}
GTS_FRS_WEIGHT = 0.10   # fraud risk enters negatively


# ---------------------------------------------------------------------------
# Fig 7 — Escalation Risk Score
# ---------------------------------------------------------------------------

ERS_WEIGHTS: Dict[str, float] = {
    "GTS":  0.25,
    "FRS":  0.25,
    "PS":   0.15,   # policy sensitivity of the service
    "SC":   0.15,   # service category
    "RR":   0.10,   # regulatory requirement
    "CH":   0.05,   # citizen history
    "DCS":  0.05,
}
ERS_T_LOW  = 0.30
ERS_T_HIGH = 0.70

#: How politically and legally sensitive each service is. Caste and its
#: validity sit highest: a wrong decision there removes a constitutional
#: entitlement or grants one that was never due.
POLICY_SENSITIVITY: Dict[ServiceType, float] = {
    ServiceType.CASTE_CERTIFICATE:    0.75,
    ServiceType.CASTE_VALIDITY:       0.75,
    ServiceType.INCOME_CERTIFICATE:   0.50,
    ServiceType.DOMICILE_CERTIFICATE: 0.50,
    ServiceType.SCHOLARSHIP:          0.50,
    ServiceType.SCHOOL_TRANSFER:      0.25,
    ServiceType.LAND_MUTATION:        0.75,
    ServiceType.SEVEN_TWELVE_EXTRACT: 0.25,
    ServiceType.TREE_FELLING_PERMIT:  0.50,
    ServiceType.FOREST_LAND_NOC:      0.75,
}

#: Whether a separate statutory body must also verify the outcome.
MANDATORY_REVIEW: Dict[ServiceType, float] = {
    ServiceType.CASTE_CERTIFICATE:    1.00,   # scrutiny committee
    ServiceType.CASTE_VALIDITY:       1.00,
    ServiceType.FOREST_LAND_NOC:      1.00,   # forest clearance
    ServiceType.LAND_MUTATION:        1.00,
}


# ---------------------------------------------------------------------------
# Fig 8 — Composite Governance Score
# ---------------------------------------------------------------------------

CGS_WEIGHTS: Dict[str, float] = {
    "GTS": 0.30,
    "CS":  0.25,   # inter-agent consensus
    "DCS": 0.20,
    "FRS": 0.15,   # inverted
    "ERS": 0.10,   # inverted
}
CGS_T_APPROVE     = 0.75
CGS_T_INVESTIGATE = 0.50
CGS_T_REJECT      = 0.25

#: Fraud or escalation above these levels forces a human decision regardless of
#: how well the rest of the application scores.
FRS_CRITICAL = 70.0
ERS_CRITICAL = 0.70


@dataclass
class ScoreBundle:
    """Every intermediate score, kept so the decision can be re-derived."""
    its: float = 0.0
    dts: float = 0.0
    dcs: float = 0.0
    pcs: float = 0.0
    crs: float = 0.0
    hbs: float = 0.0
    frs: float = 0.0
    gts: float = 0.0
    ers: float = 0.0
    cs:  float = 0.0
    cgs: float = 0.0
    verdict: Verdict = Verdict.INVESTIGATE
    guard_triggered: Optional[str] = None
    reasons: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, object]:
        return {
            "ITS": round(self.its, 2), "DTS": round(self.dts, 2),
            "DCS": round(self.dcs, 2), "PCS": round(self.pcs, 2),
            "CRS": round(self.crs, 2), "HBS": round(self.hbs, 2),
            "FRS": round(self.frs, 2), "GTS": round(self.gts, 2),
            "ERS": round(self.ers, 4), "CS": round(self.cs, 4),
            "CGS": round(self.cgs, 4), "verdict": self.verdict.value,
            "guard": self.guard_triggered,
        }


# ---------------------------------------------------------------------------
# Component scores
# ---------------------------------------------------------------------------

def document_trust_score(checks: List[AttributeCheck]) -> float:
    """
    How much of the evidence base could actually be read, 0-100.

    A thin file scores low without being penalised as fraudulent: the engine
    reports weak evidence and lets a human gather more, which is the opposite
    of rejecting a poor applicant for having no land and no vehicle.
    """
    if not checks:
        return 0.0
    available = sum(1 for c in checks if c.status is not MatchStatus.NOT_AVAILABLE)
    return round(100.0 * available / len(checks), 2)


#: Categories subject to the creamy layer test. For these, income is not a
#: side issue on a caste certificate: a household above the limit loses the
#: entitlement however sound the caste entry is.
CREAMY_LAYER_CATEGORIES = ("obc", "nt", "sbc", "vjnt", "vj")

#: Non-creamy-layer household income limit.
CREAMY_LAYER_LIMIT = 800_000


def decisive_attributes(service: ServiceType,
                        claimed_caste: Optional[str] = None) -> tuple[str, ...]:
    """
    The attributes that decide this service. Failing one of these is not a
    deduction from an average, it is a disqualification.
    """
    base = {
        ServiceType.CASTE_CERTIFICATE:    ("Caste entry", "Lineage"),
        ServiceType.CASTE_VALIDITY:       ("Caste entry", "Lineage"),
        ServiceType.INCOME_CERTIFICATE:   ("Income evidence",),
        ServiceType.DOMICILE_CERTIFICATE: ("Residence", "Identity (name)"),
    }.get(service, ("Identity (name)",))

    if service in (ServiceType.CASTE_CERTIFICATE, ServiceType.CASTE_VALIDITY):
        cat = (claimed_caste or "").strip().lower()
        if any(cat.startswith(prefix) for prefix in CREAMY_LAYER_CATEGORIES):
            base = base + ("Income evidence",)
    return base


def decisive_failures(checks: List[AttributeCheck],
                      service: ServiceType,
                      claimed_caste: Optional[str] = None) -> Dict[str, int]:
    """
    For each decisive attribute, how many independent sources contradict it.

    The count matters on its own. One source disagreeing about income is a
    discrepancy worth a question. Four disagreeing about the same income is not
    four times one discrepancy, it is a different kind of finding, and a ratio
    that mixes it in with unrelated checks that passed will hide it.
    """
    decisive = decisive_attributes(service, claimed_caste)
    out: Dict[str, int] = {}
    for c in checks:
        if c.attribute in decisive and c.status is MatchStatus.MISMATCH:
            out[c.attribute] = out.get(c.attribute, 0) + 1
    return out


def policy_compliance_score(checks: List[AttributeCheck],
                            service: ServiceType,
                            claimed_caste: Optional[str] = None) -> float:
    """
    Compliance with the rules specific to this service, 0-100.

    Scored by attribute rather than by individual check. An attribute counts as
    failed if any source contradicts it, and each attribute counts once. This
    stops an attribute that happens to be covered by four repositories from
    outweighing one covered by a single record, which is an accident of which
    departments happen to be digitised and says nothing about eligibility.
    """
    decisive = decisive_attributes(service, claimed_caste)
    groups = {}
    for c in checks:
        if c.attribute not in decisive:
            continue
        if c.status is MatchStatus.NOT_AVAILABLE:
            groups.setdefault(c.attribute, None)
            continue
        prior = groups.get(c.attribute)
        failed = c.status is MatchStatus.MISMATCH
        groups[c.attribute] = failed if prior is None else (prior or failed)

    testable = {k: v for k, v in groups.items() if v is not None}
    if not testable:
        return 50.0   # nothing to test against: neither compliant nor not
    passed = sum(1 for v in testable.values() if not v)
    return round(100.0 * passed / len(testable), 2)


def citizen_reliability_score(checks: List[AttributeCheck]) -> float:
    """
    How internally consistent the application is, 0-100.

    Starts from full trust and deducts for each contradiction the citizen
    themselves introduced, weighted by how serious that attribute is.
    """
    score = 100.0
    for c in checks:
        if c.status is MatchStatus.MISMATCH:
            score -= 100.0 * c.weight
    return round(max(0.0, score), 2)


def historical_behaviour_score(prior_certificates: List[dict],
                               claimed_caste: Optional[str]) -> float:
    """
    Track record across earlier certificates, 0-100.

    A clean history scores high. A category that changed between certificates
    is the single strongest historical signal of a manufactured claim.
    """
    if not prior_certificates:
        return 70.0   # no history is neutral, not good and not bad
    score = 100.0
    if claimed_caste:
        for prior in prior_certificates:
            pc = (prior.get("caste") or "").strip().lower()
            if pc and pc != claimed_caste.strip().lower():
                score -= 45.0
    return round(max(0.0, score), 2)


# ---------------------------------------------------------------------------
# Fig 3 — GTS
# ---------------------------------------------------------------------------

def governance_trust_score(its: float, dts: float, dcs: float,
                           pcs: float, crs: float, hbs: float,
                           frs: float) -> float:
    """
    GTS = Sum(Wi x Si) - (W_frs x FRS), clamped to 0-100.

    All inputs are on a 0-100 scale. Fraud risk subtracts, so a high fraud
    signal pulls an otherwise tidy application down rather than being averaged
    away against it.
    """
    positive = (
        GTS_WEIGHTS["ITS"] * its +
        GTS_WEIGHTS["DTS"] * dts +
        GTS_WEIGHTS["DCS"] * dcs +
        GTS_WEIGHTS["PCS"] * pcs +
        GTS_WEIGHTS["CRS"] * crs +
        GTS_WEIGHTS["HBS"] * hbs
    )
    gts = positive - GTS_FRS_WEIGHT * frs
    return round(min(100.0, max(0.0, gts)), 2)


# ---------------------------------------------------------------------------
# Fig 7 — ERS
# ---------------------------------------------------------------------------

def escalation_risk_score(gts: float, frs: float, dcs: float,
                          service: ServiceType,
                          citizen_history: str = "neutral") -> float:
    """
    ERS = Sum(Wi x Fi) on a 0-1 scale, where 1 means certainly route to a human.

    Every factor is normalised so that higher always means more risk.
    """
    ch_map = {"positive": 0.00, "neutral": 0.25, "negative": 0.75}
    service_category = 0.75 if service in MANDATORY_REVIEW else 0.50

    factors = {
        "GTS":  1.0 - (gts / 100.0),
        "FRS":  frs / 100.0,
        "PS":   POLICY_SENSITIVITY.get(service, 0.50),
        "SC":   service_category,
        "RR":   MANDATORY_REVIEW.get(service, 0.0),
        "CH":   ch_map.get(citizen_history, 0.25),
        "DCS":  1.0 - (dcs / 100.0),
    }
    ers = sum(ERS_WEIGHTS[k] * v for k, v in factors.items())
    return round(min(1.0, max(0.0, ers)), 4)


# ---------------------------------------------------------------------------
# Fig 8 — CGS and the final verdict
# ---------------------------------------------------------------------------

def composite_governance_score(gts: float, consensus: float, dcs: float,
                               frs: float, ers: float) -> float:
    """CGS = Sum(Wi x Si) on a 0-1 scale, with risk factors inverted."""
    cgs = (
        CGS_WEIGHTS["GTS"] * (gts / 100.0) +
        CGS_WEIGHTS["CS"]  * consensus +
        CGS_WEIGHTS["DCS"] * (dcs / 100.0) +
        CGS_WEIGHTS["FRS"] * (1.0 - frs / 100.0) +
        CGS_WEIGHTS["ERS"] * (1.0 - ers)
    )
    return round(min(1.0, max(0.0, cgs)), 4)


#: A decisive attribute contradicted by this many independent repositories is
#: treated as a corroborated finding rather than a discrepancy, and goes to a
#: senior officer rather than back to the handling desk.
CORROBORATION_THRESHOLD = 3


def decide(cgs: float, frs: float, ers: float,
           pcs: float = 100.0,
           failed_decisive: Optional[List[str]] = None,
           failure_counts: Optional[Dict[str, int]] = None) -> tuple[Verdict, Optional[str]]:
    """
    Final governance action.

    Guard conditions run before the thresholds, because an average must never
    bury a specific disqualification. An application with twelve attributes
    that agree and one village caste entry that does not is not an
    eighty-percent application: it is an application with a contradiction at
    the only point that decides the matter.

    Three guards, in order of severity:
      1. a critical fraud signal
      2. a critical escalation signal
      3. any failure on an attribute decisive for this service
    """
    failed_decisive = failed_decisive or []

    if frs >= FRS_CRITICAL:
        return Verdict.ESCALATE, (
            f"fraud risk {frs:.0f} at or above critical {FRS_CRITICAL:.0f}"
        )
    if ers >= ERS_CRITICAL:
        return Verdict.ESCALATE, (
            f"escalation risk {ers:.2f} at or above critical {ERS_CRITICAL:.2f}"
        )

    if failed_decisive:
        what = ", ".join(sorted(set(failed_decisive)))

        # One decisive attribute contradicted by several independent
        # repositories at once.
        counts = failure_counts or {}
        corroborated = [a for a, k in counts.items()
                        if k >= CORROBORATION_THRESHOLD]
        if corroborated:
            attr = corroborated[0]
            return Verdict.ESCALATE, (
                f"{attr} is contradicted by {counts[attr]} independent "
                f"repositories, which no single clerical error explains"
            )

        # More decisive attributes failing than passing is not a review, it is
        # a refusal waiting for a human to confirm it. An even split is not a
        # majority: with two decisive attributes, one failure is a question for
        # the handling officer, not a case for the Sub-Divisional Officer.
        if pcs < 50.0:
            return Verdict.ESCALATE, (
                f"{what} failed, which decides eligibility for this service"
            )
        return Verdict.INVESTIGATE, (
            f"{what} failed, which decides eligibility for this service"
        )

    if cgs >= CGS_T_APPROVE:
        return Verdict.APPROVE, None
    if cgs >= CGS_T_INVESTIGATE:
        return Verdict.INVESTIGATE, None
    if cgs >= CGS_T_REJECT:
        return Verdict.ESCALATE, "composite score in the high-risk band"
    return Verdict.REJECT, None


def build_reasons(checks: List[AttributeCheck],
                  bundle: ScoreBundle) -> List[str]:
    """
    Plain-language reasons, ordered so the most serious appears first.

    This is what the officer reads and what the citizen is entitled to be told
    when an application is refused.
    """
    reasons = [c.note for c in checks
               if c.status is MatchStatus.MISMATCH and c.note]

    inconclusive = [c for c in checks
                    if c.status is MatchStatus.NOT_AVAILABLE
                    and "inconclusive" in c.note]
    for c in inconclusive:
        reasons.append(c.note)

    if bundle.guard_triggered:
        reasons.insert(0, f"Routed to a human because {bundle.guard_triggered}.")
    if not reasons:
        reasons.append("Every attribute that could be compared agreed across sources.")
    return reasons
