"""
Fraud graph
============
Builds a heterogeneous graph over applicants and the identifiers they share,
then scores each applicant on how abnormal their position in that graph is.

  Fig 6   FRS = Sum(Wi x Si) over five risk components.

The signal this catches is the one a single-file review never can. An officer
looking at one application sees a plausible applicant. The graph sees that the
same plot number and the same mobile number carry three applications from three
different surnames, filed in the same week, each claiming the same reserved
category.

Edges are built only from identifiers the government already links, and a
shared identifier is a question, never a verdict: large joint families really do
share an address, and a village really does have one phone. Every edge that
raises the score is reported in words so the officer can dismiss it.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Set, Tuple

from seva.data.mock_sources import DataFabric, Profile, Source

# Fig 6 component weights
FRS_WEIGHTS: Dict[str, float] = {
    "community":  0.25,
    "centrality": 0.20,
    "link":       0.25,
    "behaviour":  0.20,
    "temporal":   0.10,
}

#: A household genuinely shares an address. Beyond this many distinct surnames
#: at one address, co-residence stops being the simplest explanation.
SURNAME_TOLERANCE = 2

#: Applications filed within this many days of each other count as a burst.
BURST_WINDOW_DAYS = 14


@dataclass
class GraphEdge:
    kind:   str        # "address" | "mobile" | "ration_card" | "survey_no"
    value:  str
    peers:  List[str] = field(default_factory=list)   # other aadhaar_last4


@dataclass
class FraudAssessment:
    aadhaar_last4: str
    frs:        float = 0.0
    components: Dict[str, float] = field(default_factory=dict)
    edges:      List[GraphEdge] = field(default_factory=list)
    findings:   List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, object]:
        return {
            "FRS": round(self.frs, 2),
            "components": {k: round(v, 2) for k, v in self.components.items()},
            "findings": list(self.findings),
            "shared": [
                {"kind": e.kind, "value": e.value, "peers": e.peers}
                for e in self.edges
            ],
        }


def _surname(full_name: str) -> str:
    tokens = [t for t in (full_name or "").replace(".", " ").split() if t]
    return tokens[-1].lower() if tokens else ""


#: Words that mark an address as naming specific premises rather than a locality.
PREMISES_MARKERS = (
    "plot", "house", "h.no", "hno", "flat", "gala", "room", "survey",
    "gat ", "cts ", "khasra", "door", "block", "shop", "bldg", "building",
)


def _is_premises_address(address: str) -> bool:
    """
    True when an address identifies a dwelling rather than a village or ward.

    Two people sharing "Kidangipar, Amgaon, Gondia" are neighbours in a village
    of several thousand. Two people sharing "Plot 14, Belora" are claiming the
    same front door. Only the second is evidence of anything, so only the second
    creates an edge.
    """
    a = (address or "").strip().lower()
    if not a:
        return False
    if any(marker in a for marker in PREMISES_MARKERS):
        return True
    # A leading number also identifies premises: "14/2, Belora, Pusad".
    first = a.split(",")[0].strip()
    return any(ch.isdigit() for ch in first)


class FraudGraph:
    """
    Index of shared identifiers across every applicant the platform has seen.

    In production this is a graph database query scoped to the district. The
    in-memory index keeps the demo reproducible and fast.
    """

    def __init__(self, fabric: DataFabric,
                 filed_on: Optional[Dict[str, str]] = None) -> None:
        self.fabric = fabric
        self.filed_on = filed_on or {}
        self._by_address: Dict[str, Set[str]] = defaultdict(set)
        self._by_mobile:  Dict[str, Set[str]] = defaultdict(set)
        self._by_card:    Dict[str, Set[str]] = defaultdict(set)
        self._by_survey:  Dict[str, Set[str]] = defaultdict(set)
        self._build()

    # -- index ------------------------------------------------------------
    def _build(self) -> None:
        for p in self.fabric.all_profiles():
            a4 = p.aadhaar_last4

            uidai = p.records.get(Source.UIDAI)
            if uidai is not None and uidai.available:
                addr = (uidai.get("address") or "").strip().lower()
                if addr and _is_premises_address(addr):
                    self._by_address[addr].add(a4)

            mobile = p.claim.get("mobile_last4")
            if mobile:
                self._by_mobile[str(mobile)].add(a4)

            nfs = p.records.get(Source.NFS)
            if nfs is not None and nfs.available:
                card = (nfs.get("card_no") or "").strip()
                if card:
                    self._by_card[card].add(a4)

            bhu = p.records.get(Source.BHULEKH)
            if bhu is not None and bhu.available:
                survey = (bhu.get("survey_no") or "").strip()
                village = (bhu.get("village") or "").strip().lower()
                if survey:
                    self._by_survey[f"{village}:{survey}"].add(a4)

    def _edges_for(self, a4: str) -> List[GraphEdge]:
        p = self.fabric.profile(a4)
        if p is None:
            return []
        edges: List[GraphEdge] = []

        def add(index: Dict[str, Set[str]], key: Optional[str], kind: str) -> None:
            if not key:
                return
            peers = sorted(index.get(key, set()) - {a4})
            if peers:
                edges.append(GraphEdge(kind=kind, value=key, peers=peers))

        uidai = p.records.get(Source.UIDAI)
        if uidai is not None and uidai.available:
            addr = (uidai.get("address") or "").strip().lower()
            if _is_premises_address(addr):
                add(self._by_address, addr, "address")
        add(self._by_mobile, str(p.claim.get("mobile_last4") or ""), "mobile")

        nfs = p.records.get(Source.NFS)
        if nfs is not None and nfs.available:
            add(self._by_card, (nfs.get("card_no") or "").strip(), "ration_card")

        bhu = p.records.get(Source.BHULEKH)
        if bhu is not None and bhu.available:
            village = (bhu.get("village") or "").strip().lower()
            survey = (bhu.get("survey_no") or "").strip()
            if survey:
                add(self._by_survey, f"{village}:{survey}", "survey_no")
        return edges

    def _cluster(self, a4: str) -> Set[str]:
        """Everyone reachable from this applicant through shared identifiers."""
        seen: Set[str] = {a4}
        frontier = [a4]
        while frontier:
            current = frontier.pop()
            for edge in self._edges_for(current):
                for peer in edge.peers:
                    if peer not in seen:
                        seen.add(peer)
                        frontier.append(peer)
        return seen

    # -- scoring ----------------------------------------------------------
    def assess(self, a4: str) -> FraudAssessment:
        p = self.fabric.profile(a4)
        out = FraudAssessment(aadhaar_last4=a4)
        if p is None:
            return out

        edges = self._edges_for(a4)
        out.edges = edges
        cluster = self._cluster(a4)
        peers = sorted(cluster - {a4})

        # --- community: how large is the connected group ------------------
        size = len(cluster)
        community = 0.0 if size <= 1 else min(100.0, (size - 1) * 35.0)
        if size > 1:
            out.findings.append(
                f"Linked to {size - 1} other applicant(s) through shared "
                f"identifiers: {', '.join(peers)}."
            )

        # --- centrality: how many distinct identifiers are shared ---------
        centrality = min(100.0, len(edges) * 40.0)
        for e in edges:
            out.findings.append(
                f"Shared {e.kind.replace('_', ' ')} {e.value!r} with "
                f"{', '.join(e.peers)}."
            )

        # --- link anomaly: links that a family would not produce -----------
        link = 0.0
        surnames = {_surname(self.fabric.profile(x).claim.get("full_name", ""))
                    for x in cluster if self.fabric.profile(x)}
        surnames.discard("")
        if len(surnames) > SURNAME_TOLERANCE:
            link += 60.0
            out.findings.append(
                f"{len(surnames)} different surnames share these identifiers "
                f"({', '.join(sorted(surnames))}), which co-residence alone "
                f"does not explain."
            )
        household_edges = [e for e in edges if e.kind in ("address", "mobile")]
        if len(household_edges) >= 2 and len(surnames) > 1:
            link += 40.0
            out.findings.append(
                "Both address and mobile number are shared across different "
                "surnames."
            )
        link = min(100.0, link)

        # --- behaviour: identical claims across the cluster ---------------
        behaviour = 0.0
        claimed = (p.claim.get("claimed_caste") or "").strip().lower()
        if claimed and peers:
            same_claim = [
                x for x in peers
                if (self.fabric.profile(x).claim.get("claimed_caste") or "")
                .strip().lower() == claimed
            ]
            if len(same_claim) >= 2:
                behaviour += 70.0
                out.findings.append(
                    f"{len(same_claim) + 1} linked applicants all claim "
                    f"{p.claim.get('claimed_caste')}."
                )
            # Someone in the group whose own household record contradicts
            # their own claim. Another applicant's card showing a different
            # caste is normal and is not counted; only a self-contradiction is.
            for x in sorted(cluster):
                prof = self.fabric.profile(x)
                if prof is None:
                    continue
                nfs = prof.records.get(Source.NFS)
                if nfs is None or not nfs.available:
                    continue
                own_claim = (prof.claim.get("claimed_caste") or "").strip().lower()
                card_caste = (nfs.get("caste") or "").strip().lower()
                if own_claim and card_caste and card_caste != own_claim:
                    behaviour += 30.0
                    who = "This applicant" if x == a4 else f"Applicant {x} in the same group"
                    out.findings.append(
                        f"{who} claims {prof.claim.get('claimed_caste')} but "
                        f"their own ration card records {nfs.get('caste')}."
                    )
                    break
        behaviour = min(100.0, behaviour)

        # --- temporal: a burst of filings from one group ------------------
        temporal = 0.0
        dates = [self.filed_on.get(x) for x in cluster if self.filed_on.get(x)]
        if len(dates) >= 2:
            try:
                parsed = sorted(datetime.fromisoformat(d) for d in dates)
                span = (parsed[-1] - parsed[0]).days
                if span <= BURST_WINDOW_DAYS:
                    temporal = 80.0
                    out.findings.append(
                        f"{len(dates)} linked applications filed within "
                        f"{span} day(s) of each other."
                    )
            except ValueError:
                pass

        out.components = {
            "community":  community,
            "centrality": centrality,
            "link":       link,
            "behaviour":  behaviour,
            "temporal":   temporal,
        }
        out.frs = round(
            sum(FRS_WEIGHTS[k] * v for k, v in out.components.items()), 2
        )
        if not out.findings:
            out.findings.append("No shared identifiers with any other applicant.")
        return out


if __name__ == "__main__":
    fab = DataFabric()
    filed = {"1101": "2026-09-02", "1102": "2026-09-04", "1103": "2026-09-09"}
    graph = FraudGraph(fab, filed_on=filed)
    for p in fab.all_profiles():
        a = graph.assess(p.aadhaar_last4)
        print(f"{p.aadhaar_last4}  {p.scenario:16s} FRS={a.frs:6.2f}  {a.components}")
        for f in a.findings:
            print(f"        - {f}")
