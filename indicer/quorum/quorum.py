"""
Quorum Module — Weighted Consensus and Audit Trail
====================================================
Implements the fault-tolerance / quorum algorithm from the patent:

  1. Agent weight renormalisation (agents that did not respond are excluded).
  2. Three-part quorum condition:
       (a) Cardinality  : at least min_cardinality agents responded.
       (b) Weight ratio : responding agents hold ≥ min_weight_ratio of total weight.
       (c) Mandatory    : all agents in mandatory_ids responded.
  3. Weighted consensus from responding agents.
  4. SHA-256 hash-linked audit record.

WORKED EXAMPLE (Table 5 from patent)
--------------------------------------
  Agent A1 : weight=0.35, mandatory=True,  responded=True,  confidence=0.88
  Agent A2 : weight=0.25, mandatory=False, responded=True,  confidence=0.85
  Agent A3 : weight=0.20, mandatory=False, responded=False
  Agent A4 : weight=0.20, mandatory=False, responded=True,  confidence=0.79

  Renormalised weights (A1, A2, A4 only):
    A1: 0.35/0.80 = 0.4375
    A2: 0.25/0.80 = 0.3125
    A4: 0.20/0.80 = 0.2500
  Weighted confidence = 0.4375×0.88 + 0.3125×0.85 + 0.25×0.79 = 0.8506
  Quorum: cardinality 3 ≥ 3 ✓ | weight 0.80 ≥ 0.60 ✓ | mandatory A1 present ✓
  → QUORUM ACHIEVED, consensus = 0.8506 → MERGE
"""

from __future__ import annotations

import hashlib
import json
import time
import random
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Set


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Agent:
    agent_id:          str
    weight:            float          # relative importance (unnormalised)
    mandatory:         bool = False   # must respond for quorum
    response_interval: float = 0.5   # simulated response latency (seconds)


@dataclass
class AgentResponse:
    agent_id:   str
    confidence: float              # pipeline confidence score this agent computed
    responded:  bool = True
    latency_ms: float = 0.0


@dataclass
class QuorumConfig:
    min_cardinality:  int = 3      # minimum number of responding agents
    min_weight_ratio: float = 0.60 # minimum fraction of total weight that must respond
    mandatory_ids:    Set[str] = field(default_factory=set)


@dataclass
class QuorumResult:
    quorum_achieved:   bool
    responding_agents: List[str]
    missing_mandatory: List[str]
    weight_ratio:      float
    cardinality:       int
    renorm_weights:    Dict[str, float]
    consensus_score:   Optional[float]
    failure_reason:    Optional[str]


@dataclass
class AuditRecord:
    timestamp:      str
    pair_id:        str
    quorum_result:  dict
    decision:       str
    previous_hash:  str
    record_hash:    str            # SHA-256 of (previous_hash + payload)


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def renormalise_weights(
    agents: List[Agent],
    responses: Dict[str, AgentResponse],
) -> Dict[str, float]:
    """
    Compute normalised weights for only the responding agents.
    Non-responding agents are excluded; remaining weights sum to 1.
    """
    responding_ids = {r.agent_id for r in responses.values() if r.responded}
    weight_map = {a.agent_id: a.weight for a in agents}

    total = sum(weight_map[aid] for aid in responding_ids if aid in weight_map)
    if total == 0:
        return {}
    return {
        aid: weight_map[aid] / total
        for aid in responding_ids
        if aid in weight_map
    }


def evaluate_quorum(
    agents: List[Agent],
    responses: Dict[str, AgentResponse],
    config: QuorumConfig,
) -> QuorumResult:
    """
    Three-part quorum test.

    Returns a QuorumResult indicating whether quorum is achieved and
    the breakdown of each condition.
    """
    total_weight = sum(a.weight for a in agents)
    responding = [r for r in responses.values() if r.responded]
    responding_ids = {r.agent_id for r in responding}
    mandatory_ids = config.mandatory_ids

    weight_ratio = (
        sum(a.weight for a in agents if a.agent_id in responding_ids) / total_weight
        if total_weight > 0 else 0.0
    )
    cardinality = len(responding)
    missing_mandatory = [mid for mid in mandatory_ids if mid not in responding_ids]

    renorm = renormalise_weights(agents, responses)

    failures = []
    if cardinality < config.min_cardinality:
        failures.append(f"cardinality {cardinality} < {config.min_cardinality}")
    if weight_ratio < config.min_weight_ratio:
        failures.append(f"weight_ratio {weight_ratio:.4f} < {config.min_weight_ratio}")
    if missing_mandatory:
        failures.append(f"mandatory agents missing: {missing_mandatory}")

    quorum_achieved = len(failures) == 0

    return QuorumResult(
        quorum_achieved=quorum_achieved,
        responding_agents=list(responding_ids),
        missing_mandatory=missing_mandatory,
        weight_ratio=weight_ratio,
        cardinality=cardinality,
        renorm_weights=renorm,
        consensus_score=None,       # filled by derive_consensus
        failure_reason="; ".join(failures) if failures else None,
    )


def derive_consensus(
    quorum_result: QuorumResult,
    responses: Dict[str, AgentResponse],
) -> float:
    """
    Weighted average confidence from responding agents using renormalised weights.

    Returns a value in [0, 1].
    """
    if not quorum_result.quorum_achieved:
        raise ValueError("Cannot derive consensus: quorum not achieved.")
    renorm = quorum_result.renorm_weights
    total = 0.0
    for aid, w in renorm.items():
        if aid in responses and responses[aid].responded:
            total += w * responses[aid].confidence
    return max(0.0, min(1.0, total))


def build_record(
    pair_id: str,
    quorum_result: QuorumResult,
    decision: str,
    previous_hash: str = "0" * 64,
) -> AuditRecord:
    """
    Build a hash-linked audit record for immutable logging.
    The record_hash is SHA-256( previous_hash || JSON(payload) ).
    """
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    payload = {
        "timestamp":    ts,
        "pair_id":      pair_id,
        "quorum":       asdict(quorum_result),
        "decision":     decision,
    }
    payload_str = json.dumps(payload, sort_keys=True, default=str)
    record_hash = hashlib.sha256((previous_hash + payload_str).encode()).hexdigest()

    return AuditRecord(
        timestamp=ts,
        pair_id=pair_id,
        quorum_result=asdict(quorum_result),
        decision=decision,
        previous_hash=previous_hash,
        record_hash=record_hash,
    )


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------

def run_simulation(
    agents: List[Agent],
    pair_confidences: Dict[str, float],   # agent_id → confidence score
    config: Optional[QuorumConfig] = None,
    failure_rate: float = 0.15,
    pair_id: str = "PAIR-001",
    previous_hash: str = "0" * 64,
    seed: Optional[int] = None,
) -> tuple[QuorumResult, Optional[float], AuditRecord]:
    """
    Simulate one quorum round.

    Parameters
    ----------
    agents           : list of Agent objects
    pair_confidences : dict mapping agent_id → the confidence score that agent
                       computed for this pair (via its own pipeline run)
    config           : QuorumConfig (defaults to min_cardinality=3, ratio=0.60)
    failure_rate     : probability that any non-mandatory agent fails to respond
    pair_id          : identifier for the pair being adjudicated
    previous_hash    : hash of the previous audit record (chain link)
    seed             : random seed for reproducibility

    Returns
    -------
    (quorum_result, consensus_score_or_None, audit_record)
    """
    if config is None:
        config = QuorumConfig(
            min_cardinality=3,
            min_weight_ratio=0.60,
            mandatory_ids={a.agent_id for a in agents if a.mandatory},
        )

    rng = random.Random(seed)

    responses: Dict[str, AgentResponse] = {}
    for agent in agents:
        # Mandatory agents always respond in this simulation
        did_respond = agent.mandatory or rng.random() > failure_rate
        responses[agent.agent_id] = AgentResponse(
            agent_id=agent.agent_id,
            confidence=pair_confidences.get(agent.agent_id, 0.5),
            responded=did_respond,
            latency_ms=rng.uniform(10, agent.response_interval * 1000),
        )

    qr = evaluate_quorum(agents, responses, config)
    consensus = None
    if qr.quorum_achieved:
        consensus = derive_consensus(qr, responses)
        qr.consensus_score = consensus

    # Determine decision string for the audit record
    if not qr.quorum_achieved:
        decision = "NO_QUORUM"
    elif consensus is None:
        decision = "NO_QUORUM"
    elif consensus >= 0.72:
        decision = "MERGE"
    elif consensus >= 0.45:
        decision = "DEFERRED"
    else:
        decision = "DISTINCT"

    record = build_record(pair_id, qr, decision, previous_hash)
    return qr, consensus, record


# ---------------------------------------------------------------------------
# Table 5 worked example (from patent)
# ---------------------------------------------------------------------------
def table5_example() -> None:
    """
    Reproduce the worked example from Table 5 of the provisional specification.
    """
    print("=" * 60)
    print("Table 5 — Quorum Worked Example")
    print("=" * 60)

    agents = [
        Agent("A1", weight=0.35, mandatory=True),
        Agent("A2", weight=0.25, mandatory=False),
        Agent("A3", weight=0.20, mandatory=False),
        Agent("A4", weight=0.20, mandatory=False),
    ]

    # A3 does NOT respond — pre-specified for the example
    pair_confidences = {"A1": 0.88, "A2": 0.85, "A3": 0.79, "A4": 0.79}

    # Build responses manually (A3 does not respond)
    from indicer.quorum.quorum import QuorumConfig, evaluate_quorum, derive_consensus, build_record, AgentResponse

    responses: Dict[str, AgentResponse] = {
        "A1": AgentResponse("A1", confidence=0.88, responded=True),
        "A2": AgentResponse("A2", confidence=0.85, responded=True),
        "A3": AgentResponse("A3", confidence=0.79, responded=False),
        "A4": AgentResponse("A4", confidence=0.79, responded=True),
    }

    config = QuorumConfig(
        min_cardinality=3,
        min_weight_ratio=0.60,
        mandatory_ids={"A1"},
    )

    qr = evaluate_quorum(agents, responses, config)
    consensus = derive_consensus(qr, responses) if qr.quorum_achieved else None
    qr.consensus_score = consensus

    print(f"Responding agents : {qr.responding_agents}")
    print(f"Missing mandatory : {qr.missing_mandatory}")
    print(f"Cardinality       : {qr.cardinality}")
    print(f"Weight ratio      : {qr.weight_ratio:.4f}")
    print(f"Renorm weights    : {qr.renorm_weights}")
    print(f"Quorum achieved   : {qr.quorum_achieved}")
    print(f"Consensus score   : {consensus:.4f}" if consensus else "Consensus: N/A")
    decision = "MERGE" if consensus and consensus >= 0.72 else "DEFERRED"
    print(f"Decision          : {decision}")

    record = build_record("PAIR-001", qr, decision)
    print(f"\nAudit record hash : {record.record_hash}")
    print("=" * 60)


if __name__ == "__main__":
    table5_example()