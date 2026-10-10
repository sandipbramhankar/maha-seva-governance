"""
Inter-agent consensus
======================
  Fig 4   Weighted voting across specialised agents, with the normalised
          consensus score NCS = (CS + 1) / 2.

Each agent looks at one dimension of the application and votes approve (+1),
investigate (0) or reject (-1). No agent can pass an application on its own and
no agent can sink one on its own; the weighted vote decides, and the fraud agent
carries enough weight that a strong fraud signal always forces a review.

Fault tolerance comes from indicer's quorum module: when an agent cannot reach
its data source, its weight is removed and the remaining weights are
renormalised, so a department API being down degrades the decision instead of
silently skewing it. If too few agents respond, the ticket is held rather than
decided on partial evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from indicer.quorum.quorum import (
    Agent, AgentResponse, QuorumConfig,
    evaluate_quorum, derive_consensus,
)

from seva.models import AttributeCheck, MatchStatus, Verdict

# Fig 4 agent weights. The scoring agent is advisory and does not vote.
AGENT_WEIGHTS: Dict[str, float] = {
    "identity_verification": 0.25,
    "document_validation":   0.20,
    "policy_compliance":     0.20,
    "department_coordination": 0.15,
    "fraud_detection":       0.15,
}

AGENT_LABELS: Dict[str, str] = {
    "identity_verification":   "Identity Verification Agent",
    "document_validation":     "Document Validation Agent",
    "policy_compliance":       "Policy Compliance Agent",
    "department_coordination": "Department Coordination Agent",
    "fraud_detection":         "Fraud Detection Agent",
}

#: Identity is decisive: if the platform cannot establish who is applying,
#: nothing downstream is meaningful, so this agent must always respond.
MANDATORY_AGENTS = {"identity_verification"}

MIN_CARDINALITY  = 3
MIN_WEIGHT_RATIO = 0.60

NCS_APPROVE     = 0.80
NCS_INVESTIGATE = 0.50


@dataclass
class AgentVote:
    agent_id:  str
    label:     str
    weight:    float
    vote:      int            # +1 approve, 0 investigate, -1 reject
    responded: bool
    rationale: str

    @property
    def vote_word(self) -> str:
        return {1: "Approve", 0: "Investigate", -1: "Reject"}[self.vote]


@dataclass
class ConsensusResult:
    votes:           List[AgentVote]
    quorum_achieved: bool
    weight_ratio:    float
    cardinality:     int
    cs:              float          # raw consensus, -1 to +1
    ncs:             float          # normalised, 0 to 1
    recommendation:  Verdict
    failure_reason:  Optional[str] = None

    def as_dict(self) -> Dict[str, object]:
        return {
            "quorum": self.quorum_achieved,
            "weight_ratio": round(self.weight_ratio, 4),
            "cardinality": self.cardinality,
            "CS": round(self.cs, 4),
            "NCS": round(self.ncs, 4),
            "recommendation": self.recommendation.value,
            "failure_reason": self.failure_reason,
            "votes": [
                {"agent": v.label, "weight": v.weight, "vote": v.vote_word,
                 "responded": v.responded, "why": v.rationale}
                for v in self.votes
            ],
        }


# ---------------------------------------------------------------------------
# Agent opinions
# ---------------------------------------------------------------------------

def _identity_vote(checks: List[AttributeCheck]) -> tuple[int, str]:
    rel = [c for c in checks if c.attribute == "Identity (name)"]
    comparable = [c for c in rel if c.status is not MatchStatus.NOT_AVAILABLE]
    if not comparable:
        return 0, "No source carried a name to compare against."
    bad = [c for c in comparable if c.status is MatchStatus.MISMATCH]
    if bad:
        return -1, (f"The applicant's name does not resolve against "
                    f"{len(bad)} of {len(comparable)} sources.")
    unresolved = [c for c in rel if "inconclusive" in c.note]
    if unresolved:
        return 0, "Name similarity was inconclusive against at least one source."
    return 1, f"Name resolved across all {len(comparable)} sources that held one."


def _document_vote(checks: List[AttributeCheck]) -> tuple[int, str]:
    if not checks:
        return 0, "Nothing to validate."
    available = [c for c in checks if c.status is not MatchStatus.NOT_AVAILABLE]
    coverage = len(available) / len(checks)
    if coverage < 0.40:
        return 0, (f"Only {coverage:.0%} of the expected records exist. Evidence "
                   f"is too thin to approve, and too thin to refuse.")
    return 1, f"{coverage:.0%} of the expected records were retrieved."


def _policy_vote(checks: List[AttributeCheck]) -> tuple[int, str]:
    decisive = [c for c in checks
                if c.attribute in ("Caste entry", "Lineage")
                and c.status is not MatchStatus.NOT_AVAILABLE]
    if not decisive:
        return 0, "No caste entry or lineage record was available to test."
    bad = [c for c in decisive if c.status is MatchStatus.MISMATCH]
    if bad:
        return -1, (f"{len(bad)} of {len(decisive)} eligibility checks failed, "
                    f"including the village caste entry.")
    return 1, "Caste entry and lineage both support the claim."


def _coordination_vote(checks: List[AttributeCheck], dcs: float) -> tuple[int, str]:
    if dcs >= 90.0:
        return 1, f"Departments agree on {dcs:.0f}% of comparable attributes."
    if dcs >= 65.0:
        return 0, f"Departments agree on only {dcs:.0f}% of comparable attributes."
    return -1, f"Departments disagree: consistency is {dcs:.0f}%."


def _fraud_vote(frs: float) -> tuple[int, str]:
    if frs >= 70.0:
        return -1, f"Fraud risk {frs:.0f} indicates a coordinated group."
    if frs >= 35.0:
        return 0, f"Fraud risk {frs:.0f} warrants a look at linked applicants."
    return 1, f"Fraud risk {frs:.0f}: no suspicious linkage found."


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------

def run_consensus(checks: List[AttributeCheck], dcs: float, frs: float,
                  unavailable: Optional[set[str]] = None) -> ConsensusResult:
    """
    Collect every agent's vote and reduce it to one recommendation.

    `unavailable` names agents whose data source could not be reached, which is
    how a department outage is represented.
    """
    unavailable = unavailable or set()

    opinions = {
        "identity_verification":   _identity_vote(checks),
        "document_validation":     _document_vote(checks),
        "policy_compliance":       _policy_vote(checks),
        "department_coordination": _coordination_vote(checks, dcs),
        "fraud_detection":         _fraud_vote(frs),
    }

    votes: List[AgentVote] = []
    agents: List[Agent] = []
    responses: Dict[str, AgentResponse] = {}

    for agent_id, weight in AGENT_WEIGHTS.items():
        vote, why = opinions[agent_id]
        responded = agent_id not in unavailable
        votes.append(AgentVote(
            agent_id=agent_id, label=AGENT_LABELS[agent_id], weight=weight,
            vote=vote, responded=responded,
            rationale=why if responded else "Data source unreachable.",
        ))
        agents.append(Agent(agent_id=agent_id, weight=weight,
                            mandatory=agent_id in MANDATORY_AGENTS))
        # indicer's quorum works on confidence in [0,1]; map the vote onto it
        responses[agent_id] = AgentResponse(
            agent_id=agent_id,
            confidence=(vote + 1) / 2.0,
            responded=responded,
        )

    config = QuorumConfig(
        min_cardinality=MIN_CARDINALITY,
        min_weight_ratio=MIN_WEIGHT_RATIO,
        mandatory_ids=set(MANDATORY_AGENTS),
    )
    qr = evaluate_quorum(agents, responses, config)

    if not qr.quorum_achieved:
        return ConsensusResult(
            votes=votes, quorum_achieved=False,
            weight_ratio=qr.weight_ratio, cardinality=qr.cardinality,
            cs=0.0, ncs=0.0, recommendation=Verdict.ESCALATE,
            failure_reason=qr.failure_reason,
        )

    # derive_consensus returns the weighted mean of the mapped confidences,
    # which is exactly NCS. CS is its -1..+1 counterpart.
    ncs = derive_consensus(qr, responses)
    cs = (ncs * 2.0) - 1.0

    if ncs >= NCS_APPROVE:
        rec = Verdict.APPROVE
    elif ncs >= NCS_INVESTIGATE:
        rec = Verdict.INVESTIGATE
    else:
        rec = Verdict.REJECT

    return ConsensusResult(
        votes=votes, quorum_achieved=True,
        weight_ratio=qr.weight_ratio, cardinality=qr.cardinality,
        cs=cs, ncs=ncs, recommendation=rec,
    )
