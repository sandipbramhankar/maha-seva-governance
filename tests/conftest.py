import pytest

from seva.data.mock_sources import DataFabric, PROFILE_BY_AADHAAR
from seva.engine.fraud import FraudGraph
from seva.models import Citizen

#: Filing dates for the linked group, so the temporal burst signal is testable.
RING_FILED = {"1101": "2026-09-02", "1102": "2026-09-04", "1103": "2026-09-09"}


@pytest.fixture(scope="session")
def fabric() -> DataFabric:
    return DataFabric()


@pytest.fixture(scope="session")
def graph(fabric) -> FraudGraph:
    return FraudGraph(fabric, filed_on=RING_FILED)


@pytest.fixture
def citizen():
    def _make(aadhaar_last4: str) -> Citizen:
        profile = PROFILE_BY_AADHAAR[aadhaar_last4]
        return Citizen(aadhaar_last4=aadhaar_last4, **profile.claim)
    return _make
