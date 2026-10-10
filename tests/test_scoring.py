"""Score stack, checked against the worked examples in the design figures."""
import pytest

from seva.engine.scoring import (
    CGS_T_APPROVE, FRS_CRITICAL, composite_governance_score, decide,
    escalation_risk_score, governance_trust_score, decisive_attributes,
)
from seva.models import ServiceType, Verdict


def test_gts_matches_the_figure_3_worked_example():
    gts = governance_trust_score(its=90, dts=85, dcs=80, pcs=95,
                                 crs=75, hbs=70, frs=20)
    assert gts == pytest.approx(73.50, abs=0.01)


def test_cgs_matches_the_figure_8_worked_example():
    cgs = composite_governance_score(gts=82, consensus=0.75, dcs=80,
                                     frs=22, ers=0.40)
    assert cgs == pytest.approx(0.771, abs=0.001)


def test_fraud_overrides_an_otherwise_healthy_score():
    """A high average must never bury a specific red flag."""
    verdict, guard = decide(cgs=0.95, frs=FRS_CRITICAL + 5, ers=0.2)
    assert verdict is Verdict.ESCALATE and "fraud" in guard


def test_a_decisive_failure_blocks_approval():
    verdict, guard = decide(cgs=0.93, frs=0, ers=0.2, pcs=75.0,
                            failed_decisive=["Lineage"])
    assert verdict is not Verdict.APPROVE
    assert "Lineage" in guard


def test_several_sources_contradicting_one_attribute_escalates():
    verdict, guard = decide(cgs=0.80, frs=0, ers=0.3, pcs=66.7,
                            failed_decisive=["Income evidence"],
                            failure_counts={"Income evidence": 4})
    assert verdict is Verdict.ESCALATE
    assert "4 independent repositories" in guard


def test_one_source_contradicting_is_a_question_not_a_case():
    verdict, _ = decide(cgs=0.80, frs=0, ers=0.3, pcs=66.7,
                        failed_decisive=["Lineage"],
                        failure_counts={"Lineage": 1})
    assert verdict is Verdict.INVESTIGATE


def test_an_even_split_is_not_a_majority():
    """With two decisive attributes, one failure is not a refusal."""
    verdict, _ = decide(cgs=0.82, frs=0, ers=0.3, pcs=50.0,
                        failed_decisive=["Lineage"],
                        failure_counts={"Lineage": 1})
    assert verdict is Verdict.INVESTIGATE


def test_a_clean_application_is_approved():
    verdict, guard = decide(cgs=CGS_T_APPROVE + 0.05, frs=0, ers=0.2)
    assert verdict is Verdict.APPROVE and guard is None


def test_income_is_decisive_only_for_creamy_layer_categories():
    obc = decisive_attributes(ServiceType.CASTE_CERTIFICATE, "OBC-Kunbi")
    sc = decisive_attributes(ServiceType.CASTE_CERTIFICATE, "SC-Mahar")
    assert "Income evidence" in obc
    assert "Income evidence" not in sc


def test_escalation_rises_as_trust_falls():
    low = escalation_risk_score(gts=90, frs=0, dcs=95,
                                service=ServiceType.CASTE_CERTIFICATE)
    high = escalation_risk_score(gts=30, frs=80, dcs=40,
                                 service=ServiceType.CASTE_CERTIFICATE)
    assert 0.0 <= low < high <= 1.0
