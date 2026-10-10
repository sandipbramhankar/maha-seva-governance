"""
Cross-source verification
==========================
Compares what the citizen claims against what the linked government
repositories already hold, and explains every disagreement in words an officer
can act on.

Identity resolution across sources is delegated to indicer, which is what makes
this workable in Maharashtra: the same person appears as "Sandip Prabhu
Bramhankar" on the application, "Sandeep Prabhu Brahmankar" on Aadhaar and
"संदीप प्रभु ब्राह्मणकर" in the 1961 village record. A string comparison calls
those three different people. indicer calls them one.

Nothing here asks the citizen to fetch a document from an officer. Every field
is read from a repository the government already maintains.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from indicer.pipeline.stage6_merge import run_pair, Decision

from seva.models import AttributeCheck, MatchStatus, Citizen
from seva.data.mock_sources import DataFabric, Source, SourceRecord
from seva.engine.names import (
    Relation, relate, lineage_consistent, parse as parse_name,
    same_token as same_name_token,
)

# ---------------------------------------------------------------------------
# Tunable parameters
#
# These are policy, not algorithm. A department changes them by notification
# without touching code, and every ticket records the values in force when it
# was decided.
# ---------------------------------------------------------------------------

#: Net annual agricultural income per hectare, rainfed Vidarbha / Marathwada.
NET_INCOME_PER_HECTARE = 55_000

#: Household income above which LPG subsidy is withdrawn under PAHAL.
PAHAL_INCOME_THRESHOLD = 1_000_000

#: A vehicle worth more than this multiple of declared annual income is a flag.
VEHICLE_VALUE_MULTIPLE = 6.0

#: Declared income below this fraction of evidenced income is a flag.
INCOME_UNDERSTATEMENT_RATIO = 0.60

#: Attribute weights for the weighted consistency score. Must sum to 1.0.
ATTRIBUTE_WEIGHTS: Dict[str, float] = {
    "Identity (name)":   0.18,
    "Date of birth":     0.12,
    "Caste entry":       0.25,
    "Lineage":           0.15,
    "Household link":    0.10,
    "Income evidence":   0.12,
    "Residence":         0.08,
}

#: A surname shared by a large share of the population carries less evidential
#: weight, so indicer is told how common it is.
COMMON_SURNAMES = {
    "patil", "pawar", "jadhav", "shinde", "more", "chavan", "kamble",
    "gaikwad", "bhosale", "sawant", "deshmukh", "kulkarni", "joshi",
}
RARE_SURNAMES = {"bramhankar", "brahmankar", "madavi", "meshram", "wankhede"}


def _surname_frequency(full_name: str) -> str:
    """Classify the surname so indicer can weight it correctly."""
    tokens = [t for t in full_name.replace(".", " ").split() if t]
    if not tokens:
        return "medium"
    surname = tokens[-1].lower()
    if surname in COMMON_SURNAMES:
        return "high"
    if surname in RARE_SURNAMES:
        return "low"
    return "medium"


def match_names(
    name_a: str,
    name_b: str,
    dob_a: Optional[str] = None,
    dob_b: Optional[str] = None,
) -> Tuple[Decision, float]:
    """
    Resolve two name strings through indicer.

    Returns the three-state decision and the confidence score. Handles
    Devanagari against Latin, initials against expanded forms, and the
    spelling variation that transliteration produces.
    """
    if not name_a or not name_b:
        return Decision.DEFERRED, 0.0
    result = run_pair(
        {"full_name": name_a, "dob": dob_a},
        {"full_name": name_b, "dob": dob_b},
        surname_freq=_surname_frequency(name_a),
    )
    return result.decision, result.score


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

#: Records that must stand in the applicant's own name. A mismatch here is a
#: genuine identity problem.
PERSONAL_SOURCES: Dict[Source, str] = {
    Source.UIDAI: "name",
    Source.VAHAN: "owner",
}

#: Records that may stand in the name of the applicant or of a forebear.
#: Agricultural land in Maharashtra routinely remains in the father's or
#: grandfather's name for a generation after their death, because mutation is
#: slow and costs money. Treating the father's name on a 7/12 extract as an
#: identity mismatch would reject most genuine rural applicants; treating it as
#: an identity *match* would be worse, because the system would be asserting
#: that two different people are one. It is neither: it is a household link,
#: and the right question is whether the record belongs to this family at all.
HOUSEHOLD_SOURCES: Dict[Source, str] = {
    Source.BHULEKH: "owner_name",
    Source.PMKISAN: "beneficiary",
}


def _check_household(citizen: Citizen,
                     records: Dict[Source, SourceRecord]) -> List[AttributeCheck]:
    """
    Establish whose name a property or benefit record stands in.

    Read through the Maharashtra naming convention rather than by string
    similarity, so the answer is a relationship ("the applicant's father")
    instead of a number that is too high to dismiss and too low to accept.
    """
    checks: List[AttributeCheck] = []
    accepted = {Relation.SELF, Relation.FATHER, Relation.GRANDFATHER}

    for source, field in HOUSEHOLD_SOURCES.items():
        rec = records.get(source)
        if rec is None or not rec.available:
            checks.append(AttributeCheck(
                attribute="Household link", source=source.value,
                claimed=citizen.full_name, found=None,
                status=MatchStatus.NOT_AVAILABLE,
                weight=ATTRIBUTE_WEIGHTS["Household link"],
                note="No record in this repository.",
            ))
            continue

        found = rec.get(field)
        relation, why = relate(
            found, citizen.full_name,
            citizen.father_name, citizen.grandfather_name,
        )
        if relation in accepted:
            status = MatchStatus.MATCH
        elif relation in (Relation.FAMILY, Relation.UNKNOWN):
            status = MatchStatus.NOT_AVAILABLE
        else:
            status = MatchStatus.MISMATCH

        checks.append(AttributeCheck(
            attribute="Household link", source=source.value,
            claimed=citizen.full_name, found=found, status=status,
            weight=ATTRIBUTE_WEIGHTS["Household link"],
            note=why,
        ))
    return checks


def _check_identity(citizen: Citizen,
                    records: Dict[Source, SourceRecord]) -> List[AttributeCheck]:
    """
    Match the applicant against records that must be theirs personally.

    Deliberately excludes land and benefit records: those are tested separately
    as household links, because they legitimately carry a forebear's name.
    """
    checks: List[AttributeCheck] = []
    name_fields = PERSONAL_SOURCES
    for source, field in name_fields.items():
        rec = records.get(source)
        if rec is None or not rec.available:
            checks.append(AttributeCheck(
                attribute="Identity (name)", source=source.value,
                claimed=citizen.full_name, found=None,
                status=MatchStatus.NOT_AVAILABLE,
                weight=ATTRIBUTE_WEIGHTS["Identity (name)"],
                note="No record in this repository.",
            ))
            continue

        found = rec.get(field)
        decision, score = match_names(
            citizen.full_name, found,
            citizen.dob, rec.get("dob") or citizen.dob,
        )
        if decision is Decision.MERGE:
            status, note = MatchStatus.MATCH, f"Resolved to the same person (confidence {score:.2f})."
        elif decision is Decision.DEFERRED:
            status, note = MatchStatus.NOT_AVAILABLE, (
                f"Name similarity {score:.2f} is inconclusive. Officer must confirm identity."
            )
        else:
            status, note = MatchStatus.MISMATCH, (
                f"Name does not resolve to the applicant (confidence {score:.2f})."
            )
        checks.append(AttributeCheck(
            attribute="Identity (name)", source=source.value,
            claimed=citizen.full_name, found=found, status=status,
            weight=ATTRIBUTE_WEIGHTS["Identity (name)"], note=note,
        ))
    return checks


def _check_dob(citizen: Citizen,
               records: Dict[Source, SourceRecord]) -> List[AttributeCheck]:
    rec = records.get(Source.UIDAI)
    if rec is None or not rec.available or not citizen.dob:
        return [AttributeCheck(
            attribute="Date of birth", source=Source.UIDAI.value,
            claimed=citizen.dob, found=None, status=MatchStatus.NOT_AVAILABLE,
            weight=ATTRIBUTE_WEIGHTS["Date of birth"],
            note="No Aadhaar date of birth to compare.",
        )]
    found = rec.get("dob")
    same = bool(found) and found.strip() == citizen.dob.strip()
    return [AttributeCheck(
        attribute="Date of birth", source=Source.UIDAI.value,
        claimed=citizen.dob, found=found,
        status=MatchStatus.MATCH if same else MatchStatus.MISMATCH,
        weight=ATTRIBUTE_WEIGHTS["Date of birth"],
        note="" if same else "Date of birth differs from the Aadhaar record.",
    )]


def _check_caste(citizen: Citizen,
                 records: Dict[Source, SourceRecord]) -> List[AttributeCheck]:
    """
    The decisive check for a caste certificate.

    The village caste entry carries the most weight because it predates the
    application by decades and cannot be created on demand.
    """
    checks: List[AttributeCheck] = []
    claimed = (citizen.claimed_caste or "").strip()
    if not claimed:
        return checks

    sources = [
        (Source.BHULEKH, "caste_entry", "Village caste entry"),
        (Source.NFS,     "caste",       "Ration card caste"),
    ]
    for source, field, label in sources:
        rec = records.get(source)
        if rec is None or not rec.available:
            checks.append(AttributeCheck(
                attribute="Caste entry", source=source.value,
                claimed=claimed, found=None, status=MatchStatus.NOT_AVAILABLE,
                weight=ATTRIBUTE_WEIGHTS["Caste entry"],
                note=f"{label} not on record.",
            ))
            continue
        found = (rec.get(field) or "").strip()
        same = found.lower() == claimed.lower()
        note = ""
        if not same and found:
            year = rec.get("record_year")
            dated = f" dated {year}" if year else ""
            note = (f"{label}{dated} reads {found}, the application claims "
                    f"{claimed}.")
        checks.append(AttributeCheck(
            attribute="Caste entry", source=source.value,
            claimed=claimed, found=found or None,
            status=MatchStatus.MATCH if same else MatchStatus.MISMATCH,
            weight=ATTRIBUTE_WEIGHTS["Caste entry"], note=note,
        ))

    # Any caste recorded on a certificate this person already holds
    hist = records.get(Source.SEVA_HISTORY)
    if hist is not None and hist.available:
        priors = hist.get("prior_certificates") or []
        for prior in priors:
            prior_caste = (prior.get("caste") or "").strip()
            if not prior_caste:
                continue
            same = prior_caste.lower() == claimed.lower()
            checks.append(AttributeCheck(
                attribute="Caste entry", source=Source.SEVA_HISTORY.value,
                claimed=claimed, found=prior_caste,
                status=MatchStatus.MATCH if same else MatchStatus.MISMATCH,
                weight=ATTRIBUTE_WEIGHTS["Caste entry"],
                note="" if same else (
                    f"A {prior['type']} issued in {prior['year']} records "
                    f"{prior_caste}. The category cannot change between "
                    f"certificates without an order."
                ),
            ))
    return checks


def _check_lineage(citizen: Citizen,
                   records: Dict[Source, SourceRecord]) -> List[AttributeCheck]:
    """
    Three-generation proof, read through the naming convention.

    The applicant's patronymic should be the father's given name, and the
    father's own patronymic should be the grandfather's. When the village
    records carry those names, the chain closes on the records themselves and
    the applicant never has to be sent to an officer to collect a letter.
    """
    checks: List[AttributeCheck] = []
    w = ATTRIBUTE_WEIGHTS["Lineage"]
    if not citizen.father_name:
        return checks

    app = parse_name(citizen.full_name)
    father = parse_name(citizen.father_name)

    # The applicant's own name should encode the father's given name.
    if app.patronymic and father.given:
        agrees = same_name_token(app.patronymic, father.given)
        checks.append(AttributeCheck(
            attribute="Lineage", source="Application",
            claimed=f"father: {citizen.father_name}",
            found=f"patronymic: {app.patronymic}",
            status=MatchStatus.MATCH if agrees else MatchStatus.MISMATCH,
            weight=w,
            note=("The applicant's patronymic matches the stated father's "
                  "given name." if agrees else
                  f"The applicant's patronymic is {app.patronymic}, but the "
                  f"father is stated as {citizen.father_name}. One of the two "
                  f"is wrong and the officer must establish which."),
        ))

    # The ration card head of family.
    nfs = records.get(Source.NFS)
    if nfs is not None and nfs.available:
        head = nfs.get("head_of_family")
        relation, why = relate(head, citizen.full_name,
                               citizen.father_name, citizen.grandfather_name)
        if relation in (Relation.SELF, Relation.FATHER, Relation.GRANDFATHER):
            status = MatchStatus.MATCH
        elif relation in (Relation.FAMILY, Relation.UNKNOWN):
            status = MatchStatus.NOT_AVAILABLE
        else:
            status = MatchStatus.MISMATCH
        checks.append(AttributeCheck(
            attribute="Lineage", source=Source.NFS.value,
            claimed=citizen.father_name, found=head, status=status,
            weight=w, note=f"Head of family: {why}",
        ))

    # The land record's preceding holder should be the grandfather.
    bhu = records.get(Source.BHULEKH)
    if bhu is not None and bhu.available and citizen.grandfather_name:
        predecessor = bhu.get("predecessor_name")
        owner = bhu.get("owner_name")

        if predecessor:
            relation, why = relate(predecessor, citizen.full_name,
                                   citizen.father_name, citizen.grandfather_name)
            agrees = relation is Relation.GRANDFATHER
            checks.append(AttributeCheck(
                attribute="Lineage", source=Source.BHULEKH.value,
                claimed=citizen.grandfather_name, found=predecessor,
                status=MatchStatus.MATCH if agrees else MatchStatus.MISMATCH,
                weight=w,
                note=("The preceding landholder is the stated grandfather, so "
                      "the third generation is proved by the record itself."
                      if agrees else
                      f"The land record names {predecessor} as the preceding "
                      f"holder. {why} Three-generation proof does not close."),
            ))
        else:
            # No explicit predecessor. The holder's own patronymic may still
            # carry the grandfather's name, but only when the holder is the
            # father: a record in the applicant's own name has the father as
            # its patronymic, which says nothing about the generation above.
            owner_relation, _ = relate(owner, citizen.full_name,
                                       citizen.father_name,
                                       citizen.grandfather_name)
            if owner_relation is Relation.GRANDFATHER:
                checks.append(AttributeCheck(
                    attribute="Lineage", source=Source.BHULEKH.value,
                    claimed=citizen.grandfather_name, found=owner,
                    status=MatchStatus.MATCH, weight=w,
                    note=("The land still stands in the grandfather's own "
                          "name, which closes the chain without a separate "
                          "document."),
                ))
            elif owner_relation is Relation.FATHER:
                confirms = lineage_consistent(owner, citizen.full_name,
                                              citizen.grandfather_name)
                if confirms is True:
                    checks.append(AttributeCheck(
                        attribute="Lineage", source=Source.BHULEKH.value,
                        claimed=citizen.grandfather_name, found=owner,
                        status=MatchStatus.MATCH, weight=w,
                        note=("The father's own patronymic on the land record "
                              "is the stated grandfather's given name, which "
                              "closes the chain without a separate document."),
                    ))
                elif confirms is False:
                    checks.append(AttributeCheck(
                        attribute="Lineage", source=Source.BHULEKH.value,
                        claimed=citizen.grandfather_name, found=owner,
                        status=MatchStatus.MISMATCH, weight=w,
                        note=(f"The land record gives the father's patronymic "
                              f"as {parse_name(owner).patronymic}, not the "
                              f"stated grandfather "
                              f"{citizen.grandfather_name}."),
                    ))
                else:
                    checks.append(AttributeCheck(
                        attribute="Lineage", source=Source.BHULEKH.value,
                        claimed=citizen.grandfather_name, found=owner,
                        status=MatchStatus.NOT_AVAILABLE, weight=w,
                        note=("The father's entry carries no patronymic, so "
                              "the grandfather cannot be tested against this "
                              "record."),
                    ))
            else:
                checks.append(AttributeCheck(
                    attribute="Lineage", source=Source.BHULEKH.value,
                    claimed=citizen.grandfather_name, found=owner,
                    status=MatchStatus.NOT_AVAILABLE, weight=w,
                    note=("The land stands in the applicant's own name and "
                          "names no earlier holder, so it cannot speak to the "
                          "generation above the father."),
                ))
    return checks


def _check_income(citizen: Citizen,
                  records: Dict[Source, SourceRecord]) -> List[AttributeCheck]:
    """
    Triangulate declared income against land, vehicle and subsidy evidence.

    Each signal is reported separately so the officer sees which one disagrees
    rather than a single opaque verdict.
    """
    checks: List[AttributeCheck] = []
    claimed = citizen.claimed_income
    w = ATTRIBUTE_WEIGHTS["Income evidence"]
    if claimed is None:
        return checks

    # --- land-implied income -------------------------------------------
    bhu = records.get(Source.BHULEKH)
    if bhu is not None and bhu.available:
        hectares = float(bhu.get("area_hectare") or 0)
        implied = int(hectares * NET_INCOME_PER_HECTARE)
        understated = implied > 0 and claimed < implied * INCOME_UNDERSTATEMENT_RATIO
        checks.append(AttributeCheck(
            attribute="Income evidence", source=Source.BHULEKH.value,
            claimed=f"Rs {claimed:,}",
            found=f"{hectares} ha implies about Rs {implied:,}",
            status=MatchStatus.MISMATCH if understated else MatchStatus.MATCH,
            weight=w,
            note=("" if not understated else
                  f"{hectares} hectares yields roughly Rs {implied:,} a year at "
                  f"Rs {NET_INCOME_PER_HECTARE:,} per hectare. The declared "
                  f"Rs {claimed:,} is well below that."),
        ))

    # --- LPG subsidy status ---------------------------------------------
    pahal = records.get(Source.PAHAL)
    if pahal is not None and pahal.available:
        status_txt = (pahal.get("subsidy_status") or "").lower()
        withdrawn = status_txt == "withdrawn"
        checks.append(AttributeCheck(
            attribute="Income evidence", source=Source.PAHAL.value,
            claimed=f"Rs {claimed:,}", found=f"subsidy {status_txt}",
            status=MatchStatus.MISMATCH if withdrawn else MatchStatus.MATCH,
            weight=w,
            note=("" if not withdrawn else
                  f"LPG subsidy was withdrawn on {pahal.get('withdrawn_on')}, "
                  f"which happens when household income exceeds "
                  f"Rs {PAHAL_INCOME_THRESHOLD:,}."),
        ))

    # --- PM-KISAN suspension --------------------------------------------
    pmk = records.get(Source.PMKISAN)
    if pmk is not None and pmk.available:
        st = (pmk.get("status") or "").lower()
        reason = pmk.get("suspension_reason")
        if st == "suspended" and reason:
            checks.append(AttributeCheck(
                attribute="Income evidence", source=Source.PMKISAN.value,
                claimed=f"Rs {claimed:,}", found=f"suspended: {reason}",
                status=MatchStatus.MISMATCH, weight=w,
                note=f"PM-KISAN benefit was suspended because the holder is {reason}.",
            ))

    # --- vehicle value ---------------------------------------------------
    vahan = records.get(Source.VAHAN)
    if vahan is not None and vahan.available:
        value = int(vahan.get("approx_value") or 0)
        disproportionate = claimed > 0 and value > claimed * VEHICLE_VALUE_MULTIPLE
        checks.append(AttributeCheck(
            attribute="Income evidence", source=Source.VAHAN.value,
            claimed=f"Rs {claimed:,}",
            found=f"{vahan.get('vehicle')} about Rs {value:,}",
            status=MatchStatus.MISMATCH if disproportionate else MatchStatus.MATCH,
            weight=w,
            note=("" if not disproportionate else
                  f"A vehicle worth about Rs {value:,} registered on "
                  f"{vahan.get('registered')} is {value/max(claimed,1):.1f} times "
                  f"the declared annual income."),
        ))
    return checks


def _check_residence(citizen: Citizen,
                     records: Dict[Source, SourceRecord]) -> List[AttributeCheck]:
    rec = records.get(Source.UIDAI)
    w = ATTRIBUTE_WEIGHTS["Residence"]
    if rec is None or not rec.available:
        return [AttributeCheck(
            attribute="Residence", source=Source.UIDAI.value,
            claimed=citizen.district, found=None,
            status=MatchStatus.NOT_AVAILABLE, weight=w,
            note="No Aadhaar address on record.",
        )]
    address = (rec.get("address") or "")
    district_ok = bool(citizen.district) and citizen.district.lower() in address.lower()
    return [AttributeCheck(
        attribute="Residence", source=Source.UIDAI.value,
        claimed=f"{citizen.taluka}, {citizen.district}", found=address,
        status=MatchStatus.MATCH if district_ok else MatchStatus.MISMATCH,
        weight=w,
        note="" if district_ok else (
            f"Aadhaar address does not fall in {citizen.district} district."
        ),
    )]


# ---------------------------------------------------------------------------
# Consistency scoring
# ---------------------------------------------------------------------------

def consistency_scores(checks: List[AttributeCheck]) -> Tuple[float, float]:
    """
    Cross-Department Consistency Score and its weighted variant.

    DCS counts attributes that matched out of those that could be compared.
    Attributes with no record are excluded rather than counted against the
    citizen, because a missing record says nothing about the claim.
    """
    comparable = [c for c in checks if c.status is not MatchStatus.NOT_AVAILABLE]
    if not comparable:
        return 0.0, 0.0

    matched = [c for c in comparable if c.status is MatchStatus.MATCH]
    dcs = 100.0 * len(matched) / len(comparable)

    total_w = sum(c.weight for c in comparable)
    wdcs = (sum(c.weight for c in matched) / total_w) if total_w else 0.0
    return round(dcs, 2), round(wdcs, 4)


def identity_confidence(checks: List[AttributeCheck]) -> float:
    """
    Best name-match confidence achieved against any source, read back from the
    notes indicer produced. Used as the Identity Trust Score input.
    """
    best = 0.0
    for c in checks:
        if c.attribute != "Identity (name)":
            continue
        if "confidence" in c.note:
            try:
                tail = c.note.split("confidence")[1]
                digits = "".join(ch for ch in tail if ch.isdigit() or ch == ".")
                best = max(best, float(digits.strip(".")))
            except (ValueError, IndexError):
                continue
    return round(min(best, 1.0), 4)


def run_checks(citizen: Citizen, fabric: DataFabric) -> List[AttributeCheck]:
    """Every check, in the order an officer reads them."""
    records = fabric.fetch_all(citizen.aadhaar_last4)
    checks: List[AttributeCheck] = []
    checks += _check_identity(citizen, records)
    checks += _check_household(citizen, records)
    checks += _check_dob(citizen, records)
    checks += _check_caste(citizen, records)
    checks += _check_lineage(citizen, records)
    checks += _check_income(citizen, records)
    checks += _check_residence(citizen, records)
    return checks
