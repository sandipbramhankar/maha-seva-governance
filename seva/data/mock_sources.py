"""
Synthetic government data fabric
=================================
Stands in for the Aadhaar-linked repositories the platform reads during
automated verification. Every record here is invented. No real citizen data is
used anywhere in this project.

The profiles are built to exercise each decision path the engine must handle:

  clean           every source agrees
  name_variant    the same person spelled differently across sources, including
                  Devanagari against Latin. The engine must resolve these as one
                  person rather than flag a mismatch.
  caste_mismatch  the claimed caste contradicts the village caste entry
  income_mismatch declared income contradicts land, vehicle and subsidy evidence
  lineage_gap     father's and grandfather's records do not link to the claimant
  fraud_ring      unrelated applicants sharing an address and mobile number

Replacing this module with real API adapters is the only change needed to run
the same engine against production sources.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class Source(str, Enum):
    UIDAI        = "UIDAI eKYC"
    BHULEKH      = "Bhulekh 7/12"
    NFS          = "Ration Card (NFS)"
    PMKISAN      = "PM-KISAN"
    VAHAN        = "VAHAN"
    PAHAL        = "LPG Subsidy (PAHAL)"
    SEVA_HISTORY = "Prior Seva Records"


@dataclass
class SourceRecord:
    """One repository's answer for one Aadhaar holder."""
    source:    Source
    available: bool
    fields:    Dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self.fields.get(key, default)


@dataclass
class Profile:
    """A synthetic citizen plus what each repository holds about them."""
    aadhaar_last4: str
    scenario:      str
    claim:         Dict[str, Any]              # what the citizen states
    records:       Dict[Source, SourceRecord]
    note:          str = ""


def _rec(source: Source, **fields: Any) -> SourceRecord:
    return SourceRecord(source=source, available=True, fields=fields)


def _absent(source: Source) -> SourceRecord:
    return SourceRecord(source=source, available=False)


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------

PROFILES: List[Profile] = [

    # ---------------- clean ----------------
    Profile(
        aadhaar_last4="4821",
        scenario="clean",
        note="All seven sources agree. Should clear automated verification.",
        claim={
            "full_name": "Ramesh Tukaram Meshram",
            "dob": "1988-06-12",
            "father_name": "Tukaram Nagorao Meshram",
            "grandfather_name": "Nagorao Meshram",
            "district": "Gondia", "taluka": "Amgaon", "village": "Kidangipar",
            "claimed_caste": "SC-Mahar",
            "claimed_income": 94000,
            "mobile_last4": "7731",
        },
        records={
            Source.UIDAI: _rec(Source.UIDAI,
                name="Ramesh Tukaram Meshram", dob="1988-06-12",
                address="Kidangipar, Amgaon, Gondia", gender="M"),
            Source.BHULEKH: _rec(Source.BHULEKH,
                owner_name="Ramesh Tukaram Meshram", survey_no="142/2",
                area_hectare=0.81, caste_entry="SC-Mahar",
                village="Kidangipar", record_year=1954),
            Source.NFS: _rec(Source.NFS,
                head_of_family="Tukaram Nagorao Meshram", category="BPL",
                caste="SC-Mahar", members=5, card_no="MH15-XXXX-4412"),
            Source.PMKISAN: _rec(Source.PMKISAN,
                beneficiary="Ramesh T Meshram", land_hectare=0.81,
                status="active", instalments_received=8),
            Source.VAHAN: _absent(Source.VAHAN),
            Source.PAHAL: _rec(Source.PAHAL, subsidy_status="active",
                               last_credit="2026-08-14"),
            Source.SEVA_HISTORY: _rec(Source.SEVA_HISTORY,
                prior_certificates=[
                    {"type": "Income Certificate", "year": 2023,
                     "caste": "SC-Mahar", "income": 88000},
                ]),
        },
    ),

    # ---------------- name variant: Devanagari vs Latin ----------------
    Profile(
        aadhaar_last4="9034",
        scenario="name_variant",
        note=("Devanagari in land records, Latin elsewhere, plus three spellings "
              "of the surname. A string comparison rejects this applicant; the "
              "phonetic engine resolves all variants to one person."),
        claim={
            "full_name": "Sandip Prabhu Bramhankar",
            "dob": "1985-03-14",
            "father_name": "Prabhu Bramhankar",
            "grandfather_name": "Vithoba Brahmankar",
            "district": "Gondia", "taluka": "Amgaon", "village": "Kidangipar",
            "claimed_caste": "OBC-Kunbi",
            "claimed_income": 180000,
            "mobile_last4": "2290",
        },
        records={
            Source.UIDAI: _rec(Source.UIDAI,
                name="Sandeep Prabhu Brahmankar", dob="1985-03-14",
                address="Kidangipar, Amgaon, Gondia", gender="M"),
            Source.BHULEKH: _rec(Source.BHULEKH,
                owner_name="संदीप प्रभु ब्राह्मणकर", survey_no="87/1",
                area_hectare=1.42, caste_entry="OBC-Kunbi",
                village="Kidangipar", record_year=1961),
            Source.NFS: _rec(Source.NFS,
                head_of_family="Prabhu V Bramhanakar", category="APL",
                caste="OBC-Kunbi", members=4, card_no="MH15-XXXX-9981"),
            Source.PMKISAN: _rec(Source.PMKISAN,
                beneficiary="S P Bramhankar", land_hectare=1.42,
                status="active", instalments_received=11),
            Source.VAHAN: _rec(Source.VAHAN,
                owner="Sandip P Brahmankar", vehicle="Bajaj CT100",
                category="two-wheeler", registered="2019-04-02",
                approx_value=52000),
            Source.PAHAL: _rec(Source.PAHAL, subsidy_status="active",
                               last_credit="2026-09-02"),
            Source.SEVA_HISTORY: _rec(Source.SEVA_HISTORY, prior_certificates=[]),
        },
    ),

    # ---------------- caste mismatch ----------------
    Profile(
        aadhaar_last4="5567",
        scenario="caste_mismatch",
        note=("Claims SC-Mahar. Village caste entry from 1952 reads OBC-Kunbi "
              "and a 2019 certificate was issued as OBC. Must not auto-approve."),
        claim={
            "full_name": "Prakash Dattatray Shinde",
            "dob": "1992-11-03",
            "father_name": "Dattatray Shinde",
            "grandfather_name": "Maruti Shinde",
            "district": "Beed", "taluka": "Georai", "village": "Talwada",
            "claimed_caste": "SC-Mahar",
            "claimed_income": 120000,
            "mobile_last4": "6612",
        },
        records={
            Source.UIDAI: _rec(Source.UIDAI,
                name="Prakash Dattatray Shinde", dob="1992-11-03",
                address="Talwada, Georai, Beed", gender="M"),
            Source.BHULEKH: _rec(Source.BHULEKH,
                owner_name="Dattatray Maruti Shinde", survey_no="33/4",
                area_hectare=2.10, caste_entry="OBC-Kunbi",
                village="Talwada", record_year=1952),
            Source.NFS: _rec(Source.NFS,
                head_of_family="Dattatray Maruti Shinde", category="APL",
                caste="OBC-Kunbi", members=6, card_no="MH23-XXXX-3340"),
            Source.PMKISAN: _rec(Source.PMKISAN,
                beneficiary="Dattatray M Shinde", land_hectare=2.10,
                status="active", instalments_received=12),
            Source.VAHAN: _absent(Source.VAHAN),
            Source.PAHAL: _rec(Source.PAHAL, subsidy_status="active",
                               last_credit="2026-07-19"),
            Source.SEVA_HISTORY: _rec(Source.SEVA_HISTORY,
                prior_certificates=[
                    {"type": "Caste Certificate", "year": 2019,
                     "caste": "OBC-Kunbi", "income": 110000},
                ]),
        },
    ),

    # ---------------- income mismatch ----------------
    Profile(
        aadhaar_last4="7712",
        scenario="income_mismatch",
        note=("Declares Rs 85,000 a year. Holds 6.4 hectares, owns a 2023 SUV, "
              "and LPG subsidy was withdrawn in 2024 — the withdrawal alone "
              "implies household income above Rs 10 lakh."),
        claim={
            "full_name": "Vijay Ananta Deshmukh",
            "dob": "1979-02-21",
            "father_name": "Ananta Deshmukh",
            "grandfather_name": "Rambhau Deshmukh",
            "district": "Latur", "taluka": "Ausa", "village": "Kinigaon",
            "claimed_caste": "OBC-Mali",
            "claimed_income": 85000,
            "mobile_last4": "4409",
        },
        records={
            Source.UIDAI: _rec(Source.UIDAI,
                name="Vijay Ananta Deshmukh", dob="1979-02-21",
                address="Kinigaon, Ausa, Latur", gender="M"),
            Source.BHULEKH: _rec(Source.BHULEKH,
                owner_name="Vijay Ananta Deshmukh", survey_no="210/1, 211",
                area_hectare=6.40, caste_entry="OBC-Mali",
                village="Kinigaon", record_year=1958),
            Source.NFS: _rec(Source.NFS,
                head_of_family="Vijay Ananta Deshmukh", category="APL",
                caste="OBC-Mali", members=4, card_no="MH26-XXXX-7781"),
            Source.PMKISAN: _rec(Source.PMKISAN,
                beneficiary="Vijay A Deshmukh", land_hectare=6.40,
                status="suspended", instalments_received=4,
                suspension_reason="income tax payer"),
            Source.VAHAN: _rec(Source.VAHAN,
                owner="Vijay A Deshmukh", vehicle="Mahindra Scorpio-N",
                category="four-wheeler", registered="2023-11-08",
                approx_value=1890000),
            Source.PAHAL: _rec(Source.PAHAL, subsidy_status="withdrawn",
                               withdrawn_on="2024-03-31",
                               reason="declared income above threshold"),
            Source.SEVA_HISTORY: _rec(Source.SEVA_HISTORY,
                prior_certificates=[
                    {"type": "Income Certificate", "year": 2024,
                     "caste": "OBC-Mali", "income": 760000},
                ]),
        },
    ),

    # ---------------- lineage gap ----------------
    Profile(
        aadhaar_last4="3390",
        scenario="lineage_gap",
        note=("Claims ST-Gond through the grandfather, but no village record "
              "links the stated grandfather to the father. Three-generation "
              "proof fails even though the applicant's own details check out."),
        claim={
            "full_name": "Sunil Baburao Madavi",
            "dob": "1996-09-30",
            "father_name": "Baburao Madavi",
            "grandfather_name": "Lakshman Madavi",
            "district": "Gadchiroli", "taluka": "Armori", "village": "Deulgaon",
            "claimed_caste": "ST-Gond",
            "claimed_income": 72000,
            "mobile_last4": "8853",
        },
        records={
            Source.UIDAI: _rec(Source.UIDAI,
                name="Sunil Baburao Madavi", dob="1996-09-30",
                address="Deulgaon, Armori, Gadchiroli", gender="M"),
            Source.BHULEKH: _rec(Source.BHULEKH,
                owner_name="Baburao Madavi", survey_no="76/3",
                area_hectare=0.55, caste_entry="ST-Gond",
                village="Deulgaon", record_year=1971,
                predecessor_name="Devaji Madavi"),
            Source.NFS: _rec(Source.NFS,
                head_of_family="Baburao Madavi", category="BPL",
                caste="ST-Gond", members=5, card_no="MH33-XXXX-2219"),
            Source.PMKISAN: _rec(Source.PMKISAN,
                beneficiary="Baburao Madavi", land_hectare=0.55,
                status="active", instalments_received=9),
            Source.VAHAN: _absent(Source.VAHAN),
            Source.PAHAL: _rec(Source.PAHAL, subsidy_status="active",
                               last_credit="2026-08-28"),
            Source.SEVA_HISTORY: _rec(Source.SEVA_HISTORY, prior_certificates=[]),
        },
    ),

    # ---------------- fraud ring (three unrelated applicants) ----------------
    Profile(
        aadhaar_last4="1101",
        scenario="fraud_ring",
        note="Shares an address and mobile number with 1102 and 1103, who carry different surnames.",
        claim={
            "full_name": "Anil Kisan Rathod", "dob": "1994-04-18",
            "father_name": "Kisan Rathod", "grandfather_name": "Govind Rathod",
            "district": "Yavatmal", "taluka": "Pusad", "village": "Belora",
            "claimed_caste": "NT-D Banjara", "claimed_income": 68000,
            "mobile_last4": "9090",
        },
        records={
            Source.UIDAI: _rec(Source.UIDAI, name="Anil Kisan Rathod",
                dob="1994-04-18", address="Plot 14, Belora, Pusad, Yavatmal", gender="M"),
            Source.BHULEKH: _absent(Source.BHULEKH),
            Source.NFS: _rec(Source.NFS, head_of_family="Kisan Rathod",
                category="BPL", caste="NT-D Banjara", members=4,
                card_no="MH29-XXXX-1101"),
            Source.PMKISAN: _absent(Source.PMKISAN),
            Source.VAHAN: _absent(Source.VAHAN),
            Source.PAHAL: _rec(Source.PAHAL, subsidy_status="active",
                               last_credit="2026-09-11"),
            Source.SEVA_HISTORY: _rec(Source.SEVA_HISTORY, prior_certificates=[]),
        },
    ),
    Profile(
        aadhaar_last4="1102",
        scenario="fraud_ring",
        note="Same address and mobile as 1101 and 1103.",
        claim={
            "full_name": "Sagar Namdev Pawar", "dob": "1993-12-05",
            "father_name": "Namdev Pawar", "grandfather_name": "Sopan Pawar",
            "district": "Yavatmal", "taluka": "Pusad", "village": "Belora",
            "claimed_caste": "NT-D Banjara", "claimed_income": 71000,
            "mobile_last4": "9090",
        },
        records={
            Source.UIDAI: _rec(Source.UIDAI, name="Sagar Namdev Pawar",
                dob="1993-12-05", address="Plot 14, Belora, Pusad, Yavatmal", gender="M"),
            Source.BHULEKH: _absent(Source.BHULEKH),
            Source.NFS: _rec(Source.NFS, head_of_family="Namdev Pawar",
                category="BPL", caste="OBC-Mali", members=3,
                card_no="MH29-XXXX-1102"),
            Source.PMKISAN: _absent(Source.PMKISAN),
            Source.VAHAN: _absent(Source.VAHAN),
            Source.PAHAL: _rec(Source.PAHAL, subsidy_status="active",
                               last_credit="2026-09-11"),
            Source.SEVA_HISTORY: _rec(Source.SEVA_HISTORY, prior_certificates=[]),
        },
    ),
    Profile(
        aadhaar_last4="1103",
        scenario="fraud_ring",
        note="Same address and mobile as 1101 and 1102.",
        claim={
            "full_name": "Rahul Bhagwan Chavan", "dob": "1995-07-27",
            "father_name": "Bhagwan Chavan", "grandfather_name": "Tukaram Chavan",
            "district": "Yavatmal", "taluka": "Pusad", "village": "Belora",
            "claimed_caste": "NT-D Banjara", "claimed_income": 66000,
            "mobile_last4": "9090",
        },
        records={
            Source.UIDAI: _rec(Source.UIDAI, name="Rahul Bhagwan Chavan",
                dob="1995-07-27", address="Plot 14, Belora, Pusad, Yavatmal", gender="M"),
            Source.BHULEKH: _absent(Source.BHULEKH),
            Source.NFS: _rec(Source.NFS, head_of_family="Bhagwan Chavan",
                category="BPL", caste="NT-D Banjara", members=5,
                card_no="MH29-XXXX-1103"),
            Source.PMKISAN: _absent(Source.PMKISAN),
            Source.VAHAN: _absent(Source.VAHAN),
            Source.PAHAL: _rec(Source.PAHAL, subsidy_status="active",
                               last_credit="2026-09-11"),
            Source.SEVA_HISTORY: _rec(Source.SEVA_HISTORY, prior_certificates=[]),
        },
    ),

    # ---------------- sparse sources, urban applicant ----------------
    Profile(
        aadhaar_last4="6648",
        scenario="sparse",
        note=("Urban applicant with no land, no ration card and no DOB on the "
              "legacy record. Thin evidence must produce a review, not a "
              "rejection — absence of a record is not evidence of fraud."),
        claim={
            "full_name": "Pooja Santosh Kamble", "dob": "2001-01-19",
            "father_name": "Santosh Kamble", "grandfather_name": "Eknath Kamble",
            "district": "Mumbai Suburban", "taluka": "Kurla", "village": "",
            "claimed_caste": "SC-Mahar", "claimed_income": 145000,
            "mobile_last4": "3317",
        },
        records={
            Source.UIDAI: _rec(Source.UIDAI, name="Pooja Santosh Kamble",
                dob="2001-01-19", address="Kurla East, Mumbai Suburban", gender="F"),
            Source.BHULEKH: _absent(Source.BHULEKH),
            Source.NFS: _absent(Source.NFS),
            Source.PMKISAN: _absent(Source.PMKISAN),
            Source.VAHAN: _absent(Source.VAHAN),
            Source.PAHAL: _rec(Source.PAHAL, subsidy_status="active",
                               last_credit="2026-09-05"),
            Source.SEVA_HISTORY: _rec(Source.SEVA_HISTORY,
                prior_certificates=[
                    {"type": "Caste Certificate", "year": 2018,
                     "caste": "SC-Mahar", "income": None},
                ]),
        },
    ),
]


PROFILE_BY_AADHAAR: Dict[str, Profile] = {p.aadhaar_last4: p for p in PROFILES}


class DataFabric:
    """
    Read-only facade over the linked repositories.

    Swap this class for one that calls the real APIs and nothing else in the
    engine changes.
    """

    def __init__(self, profiles: Optional[List[Profile]] = None) -> None:
        self._profiles = {p.aadhaar_last4: p for p in (profiles or PROFILES)}

    def profile(self, aadhaar_last4: str) -> Optional[Profile]:
        return self._profiles.get(aadhaar_last4)

    def fetch(self, aadhaar_last4: str, source: Source) -> SourceRecord:
        p = self._profiles.get(aadhaar_last4)
        if p is None:
            return SourceRecord(source=source, available=False)
        return p.records.get(source, SourceRecord(source=source, available=False))

    def fetch_all(self, aadhaar_last4: str) -> Dict[Source, SourceRecord]:
        return {s: self.fetch(aadhaar_last4, s) for s in Source}

    def all_profiles(self) -> List[Profile]:
        return list(self._profiles.values())

    def cohort(self, **match: Any) -> List[Profile]:
        """Profiles whose claim matches every supplied key, used by the fraud graph."""
        out = []
        for p in self._profiles.values():
            if all(p.claim.get(k) == v for k, v in match.items()):
                out.append(p)
        return out


if __name__ == "__main__":
    fab = DataFabric()
    print(f"{len(fab.all_profiles())} synthetic profiles\n")
    for p in fab.all_profiles():
        present = sum(1 for r in p.records.values() if r.available)
        print(f"  {p.aadhaar_last4}  {p.scenario:16s} {present}/7 sources  "
              f"{p.claim['full_name']}")
