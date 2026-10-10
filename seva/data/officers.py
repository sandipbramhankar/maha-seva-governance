"""
Officer registry
=================
Synthetic officers, one set per district, so every ticket has a named owner at
every stage. Names are invented.

The registry exists because accountability needs a person, not a desk. "Pending
with the Tehsil office" is what the current system reports and it is the reason
nothing moves. "Pending 41 days with Naib Tehsildar S. Kulkarni" is actionable.
"""

from __future__ import annotations

import random
from typing import Dict, List

from seva.models import Stage
from seva.workflow.stages import Officer, STAGE_ROLE
from seva.data.maharashtra import DISTRICTS

_FIRST = [
    "Sunil", "Anita", "Rajesh", "Manisha", "Prakash", "Vaishali", "Dilip",
    "Shubhangi", "Nitin", "Archana", "Sanjay", "Kavita", "Ravindra", "Smita",
    "Bhaskar", "Jyoti", "Ganesh", "Rupali", "Mahesh", "Sharmila", "Vikas",
    "Pallavi", "Ashok", "Nanda", "Deepak", "Surekha",
]
_LAST = [
    "Patil", "Deshmukh", "Kulkarni", "Shinde", "Pawar", "Jadhav", "More",
    "Gaikwad", "Kamble", "Sawant", "Thorat", "Chavan", "Bhosale", "Wagh",
    "Ingle", "Sonawane", "Rathod", "Dhage", "Khot", "Mane",
]

#: Stages staffed at district or sub-division level rather than per taluka.
_DISTRICT_LEVEL = {
    Stage.SDO_REVIEW, Stage.SCRUTINY_COMMITTEE, Stage.EDUCATION_OFFICER,
}


class OfficerRegistry:
    """Deterministic roster, so a rerun of the demo names the same people."""

    def __init__(self, seed: int = 20261009) -> None:
        self._rng = random.Random(seed)
        self._by_key: Dict[str, Officer] = {}
        self._build()

    def _name(self) -> str:
        return f"{self._rng.choice(_FIRST)} {self._rng.choice(_LAST)}"

    def _build(self) -> None:
        for district in DISTRICTS:
            for stage in (Stage.SDO_REVIEW, Stage.SCRUTINY_COMMITTEE,
                          Stage.EDUCATION_OFFICER):
                key = f"{district.code}|{stage.value}|"
                self._by_key[key] = Officer(
                    officer_id=f"{district.code}-{stage.name[:3]}-01",
                    name=self._name(), role=STAGE_ROLE[stage],
                    district=district.name,
                )
            for t_index, taluka in enumerate(district.talukas, start=1):
                for stage in (Stage.TALATHI, Stage.CIRCLE_OFFICER,
                              Stage.NAIB_TEHSILDAR, Stage.TEHSILDAR,
                              Stage.RANGE_FOREST_OFFICER):
                    key = f"{district.code}|{stage.value}|{taluka}"
                    self._by_key[key] = Officer(
                        officer_id=f"{district.code}-{stage.name[:3]}-{t_index:03d}",
                        name=self._name(), role=STAGE_ROLE[stage],
                        district=district.name, taluka=taluka,
                    )

    def officer_for(self, district_code: str, stage: Stage,
                    taluka: str = "") -> Officer:
        key = f"{district_code}|{stage.value}|{'' if stage in _DISTRICT_LEVEL else taluka}"
        found = self._by_key.get(key)
        if found is not None:
            return found
        return Officer(officer_id=f"{district_code}-GEN-001",
                       name="Unassigned", role=STAGE_ROLE.get(stage, "Officer"),
                       district=district_code, taluka=taluka)

    def all_officers(self) -> List[Officer]:
        return list(self._by_key.values())
