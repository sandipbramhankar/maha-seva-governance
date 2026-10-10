"""
Verification orchestrator
==========================
Runs one application through the whole stack and returns a report an officer
can act on without reading any code:

    cross-source checks   ->  what each repository says
    fraud graph           ->  who else is linked to this applicant
    score stack           ->  GTS, ERS, CGS
    agent consensus       ->  how the specialised agents voted
    audit entry           ->  hash-linked record of all of it

The verdict this produces is a recommendation with reasons attached. A human
still signs the certificate; what changes is that the human starts from
evidence rather than from a blank file, and that whatever they decide is
recorded against their name.
"""

from __future__ import annotations

from typing import Dict, Optional

from seva.models import (
    Citizen, ServiceType, VerificationReport, Verdict, MatchStatus,
)
from seva.data.mock_sources import DataFabric, Source
from seva.engine.verification import (
    run_checks, consistency_scores, identity_confidence,
)
from seva.engine.fraud import FraudGraph
from seva.engine.consensus import run_consensus
from seva.engine.scoring import (
    ScoreBundle, document_trust_score, policy_compliance_score,
    citizen_reliability_score, historical_behaviour_score,
    governance_trust_score, escalation_risk_score,
    composite_governance_score, decide, build_reasons,
    decisive_attributes, decisive_failures,
)
from seva.engine.audit import AuditChain


def assess(
    citizen: Citizen,
    service: ServiceType,
    fabric: DataFabric,
    graph: Optional[FraudGraph] = None,
    chain: Optional[AuditChain] = None,
    unavailable_agents: Optional[set[str]] = None,
) -> VerificationReport:
    """Full automated verification for one application."""

    # --- cross-source checks ---------------------------------------------
    checks = run_checks(citizen, fabric)
    dcs, wdcs = consistency_scores(checks)
    its = identity_confidence(checks) * 100.0

    # --- fraud graph ------------------------------------------------------
    graph = graph or FraudGraph(fabric)
    fraud = graph.assess(citizen.aadhaar_last4)

    # --- component scores -------------------------------------------------
    history_rec = fabric.fetch(citizen.aadhaar_last4, Source.SEVA_HISTORY)
    priors = history_rec.get("prior_certificates") or [] if history_rec.available else []

    dts = document_trust_score(checks)
    pcs = policy_compliance_score(checks, service, citizen.claimed_caste)
    crs = citizen_reliability_score(checks)
    hbs = historical_behaviour_score(priors, citizen.claimed_caste)

    gts = governance_trust_score(its=its, dts=dts, dcs=dcs, pcs=pcs,
                                 crs=crs, hbs=hbs, frs=fraud.frs)
    ers = escalation_risk_score(gts=gts, frs=fraud.frs, dcs=dcs, service=service)

    # --- agent consensus --------------------------------------------------
    consensus = run_consensus(checks, dcs=dcs, frs=fraud.frs,
                              unavailable=unavailable_agents)

    cgs = composite_governance_score(gts=gts, consensus=consensus.ncs,
                                     dcs=dcs, frs=fraud.frs, ers=ers)

    # Which decisive attributes actually failed, named so the guard can say so.
    decisive = decisive_attributes(service, citizen.claimed_caste)
    failed_decisive = [
        c.attribute for c in checks
        if c.attribute in decisive and c.status is MatchStatus.MISMATCH
    ]
    counts = decisive_failures(checks, service, citizen.claimed_caste)
    verdict, guard = decide(cgs, fraud.frs, ers, pcs=pcs,
                            failed_decisive=failed_decisive,
                            failure_counts=counts)

    # Quorum failure overrides everything: an incomplete vote is never a
    # decision, only a reason to involve a person.
    if not consensus.quorum_achieved:
        verdict = Verdict.ESCALATE
        guard = f"agent quorum not reached ({consensus.failure_reason})"

    bundle = ScoreBundle(
        its=its, dts=dts, dcs=dcs, pcs=pcs, crs=crs, hbs=hbs,
        frs=fraud.frs, gts=gts, ers=ers, cs=consensus.ncs, cgs=cgs,
        verdict=verdict, guard_triggered=guard,
    )
    reasons = build_reasons(checks, bundle)
    reasons.extend(f for f in fraud.findings
                   if not f.startswith("No shared identifiers"))

    report = VerificationReport(
        checks=checks, dcs=dcs, wdcs=wdcs,
        identity_score=round(its / 100.0, 4),
        fraud_risk=fraud.frs, trust_score=gts,
        escalation_risk=ers, composite=cgs,
        verdict=verdict, reasons=reasons,
    )

    # --- audit ------------------------------------------------------------
    if chain is not None:
        entry = chain.append(
            event="automated_verification",
            actor_id="SYSTEM",
            actor_name="Automated Verification",
            payload={
                "scores":    bundle.as_dict(),
                "consensus": consensus.as_dict(),
                "fraud":     fraud.as_dict(),
                "mismatches": [
                    {"attribute": c.attribute, "source": c.source,
                     "claimed": c.claimed, "found": c.found, "note": c.note}
                    for c in checks if c.status is MatchStatus.MISMATCH
                ],
            },
        )
        report.audit_hash = entry.entry_hash

    report.scores = bundle            # type: ignore[attr-defined]
    report.consensus = consensus      # type: ignore[attr-defined]
    report.fraud = fraud              # type: ignore[attr-defined]
    return report
