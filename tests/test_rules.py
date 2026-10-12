"""
tests/test_rules.py
-------------------
Unit tests for the deterministic rules engine modules.

Tests cover:
    - Policy validity checks (active, lapsed, expired)
    - Waiting period evaluation (initial, specific disease, PED)
    - IRDAI exclusion and non-payable checks
    - Sub-limit and room-rent capping with proportionate deduction
    - Co-pay percentage application
    - Fairness verification (no proxy attribute leakage)
    - Full engine integration (apply_rules)

Usage:
    python -m pytest tests/test_rules.py -v
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest

from schemas.pre_auth_request import (
    AdmissionType,
    CostCategory,
    CostEstimate,
    CostLineItem,
    Diagnosis,
    Gender,
    Hospital,
    HospitalCategory,
    NetworkTier,
    Patient,
    PlanType,
    Policy,
    PreAuthRequest,
    Procedure,
    RequestStatus,
    SourceFormat,
    SubLimitMap,
)
from rules.models import (
    AdjudicationResult,
    Deduction,
    DeductionCategory,
    PolicyStatusInfo,
    Recommendation,
    WaitingPeriodInfo,
)
from retrieval.vector_store import RetrievedClause


# ============================================================================
# Fixtures — Synthetic Pre-Auth Request
# ============================================================================


def _make_request(
    policy_number: str = "POL-ACTIVE-001",
    plan_type: PlanType = PlanType.INDIVIDUAL,
    sum_insured: Decimal = Decimal("500000.00"),
    policy_start_date: date = date(2023, 1, 1),
    co_pay_pct: Decimal = Decimal("0.00"),
    sub_limits: dict | None = None,
    icd10_code: str = "I21.0",
    diagnosis_desc: str = "Acute ST-elevation myocardial infarction (STEMI)",
    is_pre_existing: bool = False,
    procedure_desc: str = "Primary PCI with drug-eluting stent",
    admission_type: AdmissionType = AdmissionType.EMERGENCY,
    network_tier: NetworkTier = NetworkTier.CASHLESS_NETWORK,
    hospital_name: str = "Synthetic Metro Hospital",
    hospital_city: str = "Mumbai",
    patient_name: str = "Rajesh Kumar",
    patient_age: int = 45,
    line_items: list[CostLineItem] | None = None,
    total_amount: Decimal = Decimal("250000.00"),
    admission_date: date | None = None,
) -> PreAuthRequest:
    """Create a test PreAuthRequest with sensible defaults."""

    if line_items is None:
        line_items = [
            CostLineItem(item="Room Rent (5 days)", amount=Decimal("40000.00"),
                         category=CostCategory.ROOM_RENT),
            CostLineItem(item="Surgeon Fee", amount=Decimal("80000.00"),
                         category=CostCategory.SURGEON_FEE),
            CostLineItem(item="Stent (DES)", amount=Decimal("30000.00"),
                         category=CostCategory.IMPLANTS),
            CostLineItem(item="Diagnostics", amount=Decimal("25000.00"),
                         category=CostCategory.DIAGNOSTIC),
            CostLineItem(item="Pharmacy", amount=Decimal("35000.00"),
                         category=CostCategory.PHARMACY),
            CostLineItem(item="ICU Charges (2 days)", amount=Decimal("20000.00"),
                         category=CostCategory.ICU_CHARGES),
            CostLineItem(item="Consultation", amount=Decimal("15000.00"),
                         category=CostCategory.CONSULTATION_FEE),
            CostLineItem(item="Nursing", amount=Decimal("5000.00"),
                         category=CostCategory.NURSING),
        ]
        total_amount = sum(item.amount for item in line_items)

    if sub_limits is None:
        sub_limits_map = SubLimitMap(limits={"room_rent_per_day": Decimal("5000.00")})
    else:
        sub_limits_map = SubLimitMap(limits={k: Decimal(str(v)) for k, v in sub_limits.items()})

    if admission_date is None:
        admission_date = date(2025, 6, 15)

    return PreAuthRequest(
        request_id=uuid.uuid4(),
        submitted_at=date.today(),
        source_format=SourceFormat.JSON,
        status=RequestStatus.PENDING,
        admission_date=admission_date,
        patient=Patient(
            full_name=patient_name,
            age=patient_age,
            gender=Gender.MALE,
            policy_number=policy_number,
        ),
        policy=Policy(
            policy_number=policy_number,
            plan_type=plan_type,
            sum_insured=sum_insured,
            policy_start_date=policy_start_date,
            co_pay_pct=co_pay_pct,
            sub_limits=sub_limits_map,
        ),
        hospital=Hospital(
            name=hospital_name,
            city=hospital_city,
            network_tier=network_tier,
            category=HospitalCategory.MULTI_SPECIALTY,
        ),
        diagnosis=Diagnosis(
            icd10_code=icd10_code,
            description=diagnosis_desc,
            is_pre_existing=is_pre_existing,
        ),
        procedure=Procedure(
            description=procedure_desc,
            admission_type=admission_type,
        ),
        cost_estimate=CostEstimate(
            line_items=line_items,
            total_amount=total_amount,
        ),
    )


def _make_clauses() -> list[RetrievedClause]:
    """Create synthetic RetrievedClause objects for testing."""
    return [
        RetrievedClause(
            chunk_text=(
                "SECTION 7 — POLICY STATUS\n"
                "7.1 Active Policy: Claims are admissible only when the policy is in "
                "active status with all due premiums paid.\n"
                "7.2 Lapsed Policy: If the premium due is not paid within the grace "
                "period of 30 days, the policy shall lapse."
            ),
            source_file="policy_wordings/individual_health_standard.txt",
            section="SECTION 7",
            document_type="policy_wording",
            similarity_score=0.85,
            chunk_id="individual_health_standard.txt::chunk_0006",
        ),
        RetrievedClause(
            chunk_text=(
                "SECTION 3 — WAITING PERIODS\n"
                "3.1 Initial Waiting Period: No claim shall be admissible during the "
                "first 30 days of the first policy period, except claims arising from "
                "an accident.\n"
                "3.2 Specific Disease Waiting Period: Claims arising from cataract "
                "(H25, H26), hernia (K40-K46), gallstones (K80) shall be admissible "
                "only after 24 continuous months."
            ),
            source_file="policy_wordings/individual_health_standard.txt",
            section="SECTION 3",
            document_type="policy_wording",
            similarity_score=0.80,
            chunk_id="individual_health_standard.txt::chunk_0003",
        ),
        RetrievedClause(
            chunk_text=(
                "Room Rent Sub-Limit:\n"
                "Sum Insured Rs. 3L - Rs. 5L: Rs. 5,000/day room rent limit.\n"
                "Proportionate Deduction: If actual room rent exceeds the eligible "
                "limit, proportionate deduction applies to surgeon fees, anaesthesia, "
                "consultation, diagnostics, and pharmacy charges."
            ),
            source_file="benefit_tables/room_rent_schedule.txt",
            section="Room Rent Sub-Limits",
            document_type="benefit_table",
            similarity_score=0.75,
            chunk_id="room_rent_schedule.txt::chunk_0001",
        ),
        RetrievedClause(
            chunk_text=(
                "IRDAI GUIDELINES ON NON-PAYABLE ITEMS IN HEALTH INSURANCE\n"
                "Circular No.: IRDAI/HLT/CIR/MISC/116/05/2024\n"
                "Date: 29-May-2024\n"
                "LIST I — ITEMS THAT ARE NOT PART OF TREATMENT (ALWAYS NON-PAYABLE)\n"
                "1. Toiletries 2. Personal comfort items 3. Administrative charges"
            ),
            source_file="irdai_circulars/irdai_non_payables_schedule.txt",
            section="LIST I",
            document_type="irdai_circular",
            circular_date="29-May-2024",
            circular_number="IRDAI/HLT/CIR/MISC/116/05/2024",
            similarity_score=0.70,
            chunk_id="irdai_non_payables_schedule.txt::chunk_0001",
        ),
    ]


def _make_policy_status(
    is_active: bool = True,
    status: str = "ACTIVE",
    remaining_si: Decimal = Decimal("500000.00"),
    days: int = 1000,
) -> PolicyStatusInfo:
    """Create a PolicyStatusInfo for testing."""
    return PolicyStatusInfo(
        is_active=is_active,
        status=status,
        remaining_sum_insured=remaining_si,
        days_since_inception=days,
    )


def _make_wp(
    initial: bool = True,
    specific: bool = True,
    ped: bool = True,
    days: int = 1000,
) -> WaitingPeriodInfo:
    """Create a WaitingPeriodInfo for testing."""
    return WaitingPeriodInfo(
        initial_wp_clear=initial,
        specific_disease_wp_clear=specific,
        ped_wp_clear=ped,
        days_elapsed=days,
    )


# ============================================================================
# Tests: Policy Validity
# ============================================================================


class TestPolicyValidity:
    """Tests for rules/policy_validity.py."""

    def test_active_policy_passes(self):
        from rules.policy_validity import check_policy_validity

        request = _make_request()
        result = check_policy_validity(request, _make_policy_status(), _make_clauses())

        assert result["is_valid"] is True
        assert len(result["deductions"]) == 0
        assert "ACTIVE" in result["reasoning"]

    def test_lapsed_policy_denied(self):
        from rules.policy_validity import check_policy_validity

        request = _make_request()
        status = _make_policy_status(is_active=False, status="LAPSED")
        result = check_policy_validity(request, status, _make_clauses())

        assert result["is_valid"] is False
        assert len(result["deductions"]) == 1
        assert result["deductions"][0].category == DeductionCategory.POLICY_INVALID
        assert "LAPSED" in result["reasoning"]

    def test_expired_policy_denied(self):
        from rules.policy_validity import check_policy_validity

        request = _make_request()
        status = _make_policy_status(is_active=False, status="EXPIRED")
        result = check_policy_validity(request, status, _make_clauses())

        assert result["is_valid"] is False
        assert len(result["deductions"]) == 1


# ============================================================================
# Tests: Waiting Period
# ============================================================================


class TestWaitingPeriod:
    """Tests for rules/waiting_period.py."""

    def test_all_clear(self):
        from rules.waiting_period import check_waiting_period

        request = _make_request()
        result = check_waiting_period(request, _make_wp(), _make_clauses())

        assert result["is_clear"] is True
        assert len(result["deductions"]) == 0

    def test_initial_wp_not_clear(self):
        from rules.waiting_period import check_waiting_period

        request = _make_request()
        wp = _make_wp(initial=False, days=15)
        result = check_waiting_period(request, wp, _make_clauses())

        assert result["is_clear"] is False
        assert len(result["deductions"]) == 1
        assert result["deductions"][0].category == DeductionCategory.WAITING_PERIOD

    def test_specific_disease_wp_cataract(self):
        from rules.waiting_period import check_waiting_period

        # Cataract (H26) is on the specific disease list
        request = _make_request(
            icd10_code="H26.9",
            diagnosis_desc="Cataract - bilateral",
        )
        wp = _make_wp(specific=False, days=400)
        result = check_waiting_period(request, wp, _make_clauses())

        assert result["is_clear"] is False
        assert len(result["deductions"]) == 1

    def test_ped_wp_not_clear(self):
        from rules.waiting_period import check_waiting_period

        request = _make_request(is_pre_existing=True)
        wp = _make_wp(ped=False, days=800)
        result = check_waiting_period(request, wp, _make_clauses())

        assert result["is_clear"] is False
        assert any(d.category == DeductionCategory.PED_EXCLUSION
                    for d in result["deductions"])


# ============================================================================
# Tests: Exclusions
# ============================================================================


class TestExclusions:
    """Tests for rules/exclusions.py."""

    def test_no_exclusions_on_clean_items(self):
        from rules.exclusions import check_exclusions

        request = _make_request()
        result = check_exclusions(request, _make_clauses())

        assert len(result["deductions"]) == 0

    def test_non_payable_item_detected(self):
        from rules.exclusions import check_exclusions

        items = [
            CostLineItem(item="Room Rent", amount=Decimal("40000.00"),
                         category=CostCategory.ROOM_RENT),
            CostLineItem(item="Registration and admission charges",
                         amount=Decimal("500.00"),
                         category=CostCategory.OTHER),
        ]
        request = _make_request(line_items=items,
                                total_amount=Decimal("40500.00"))
        result = check_exclusions(request, _make_clauses())

        assert len(result["deductions"]) >= 1
        assert any(d.category == DeductionCategory.NON_PAYABLE
                    for d in result["deductions"])


# ============================================================================
# Tests: Sub-limits
# ============================================================================


class TestSubLimits:
    """Tests for rules/sub_limits.py."""

    def test_no_capping_when_within_limit(self):
        from rules.sub_limits import apply_sub_limits

        # Room rent is ₹5,000/day × 5 days = ₹25,000
        # But the line item is total, and the sub-limit is per-day
        # Our test fixture has "Room Rent (5 days)" as ₹40,000 total
        # which is ₹8,000/day — exceeds ₹5,000/day cap
        items = [
            CostLineItem(item="Room Rent", amount=Decimal("4000.00"),
                         category=CostCategory.ROOM_RENT),
            CostLineItem(item="Surgeon Fee", amount=Decimal("50000.00"),
                         category=CostCategory.SURGEON_FEE),
        ]
        request = _make_request(line_items=items, total_amount=Decimal("54000.00"))
        result = apply_sub_limits(request, _make_clauses())

        assert len(result["deductions"]) == 0

    def test_room_rent_capping_with_proportionate(self):
        from rules.sub_limits import apply_sub_limits

        items = [
            CostLineItem(item="Room Rent", amount=Decimal("8000.00"),
                         category=CostCategory.ROOM_RENT),
            CostLineItem(item="Surgeon Fee", amount=Decimal("50000.00"),
                         category=CostCategory.SURGEON_FEE),
            CostLineItem(item="Diagnostics", amount=Decimal("20000.00"),
                         category=CostCategory.DIAGNOSTIC),
        ]
        request = _make_request(
            line_items=items,
            total_amount=Decimal("78000.00"),
            sub_limits={"room_rent_per_day": "5000.00"},
        )
        result = apply_sub_limits(request, _make_clauses())

        # Should have room rent capping + proportionate deductions
        assert len(result["deductions"]) >= 2

        room_rent_ded = [d for d in result["deductions"]
                         if d.category == DeductionCategory.ROOM_RENT_CAPPING]
        assert len(room_rent_ded) == 1
        assert room_rent_ded[0].deducted_amount == Decimal("3000.00")

        prop_deds = [d for d in result["deductions"]
                     if d.category == DeductionCategory.PROPORTIONATE_DEDUCTION]
        assert len(prop_deds) >= 1


# ============================================================================
# Tests: Co-pay
# ============================================================================


class TestCopay:
    """Tests for rules/copay_deductible.py."""

    def test_no_copay_when_zero(self):
        from rules.copay_deductible import apply_copay_deductible

        request = _make_request(co_pay_pct=Decimal("0.00"))
        result = apply_copay_deductible(request, _make_clauses())

        assert len(result["deductions"]) == 0

    def test_copay_20_percent(self):
        from rules.copay_deductible import apply_copay_deductible

        request = _make_request(co_pay_pct=Decimal("20.00"))
        result = apply_copay_deductible(request, _make_clauses())

        assert len(result["deductions"]) == 1
        d = result["deductions"][0]
        assert d.category == DeductionCategory.CO_PAY
        total = request.cost_estimate.total_amount
        expected_copay = (total * Decimal("20") / Decimal("100")).quantize(Decimal("0.01"))
        assert d.deducted_amount == expected_copay


# ============================================================================
# Tests: Fairness
# ============================================================================


class TestFairness:
    """Tests for rules/fairness.py."""

    def test_clean_deductions_pass(self):
        from rules.fairness import verify_fairness

        request = _make_request()
        deductions = [
            Deduction(
                category=DeductionCategory.CO_PAY,
                original_amount=Decimal("100000"),
                allowed_amount=Decimal("80000"),
                deducted_amount=Decimal("20000"),
                clause_citation="Co-pay of 20% applies per policy schedule.",
                source_document="copay_schedule.txt",
                explanation="Co-pay of 20% applied on admissible amount.",
            ),
        ]
        assert verify_fairness(request, deductions) is True

    def test_patient_name_leakage_fails(self):
        from rules.fairness import verify_fairness

        request = _make_request(patient_name="Suresh Patel")
        deductions = [
            Deduction(
                category=DeductionCategory.CO_PAY,
                original_amount=Decimal("100000"),
                allowed_amount=Decimal("80000"),
                deducted_amount=Decimal("20000"),
                clause_citation="Policy terms apply.",
                source_document="policy.txt",
                explanation="Deduction for Suresh Patel based on regional factors.",
            ),
        ]
        assert verify_fairness(request, deductions) is False


# ============================================================================
# Tests: Full Engine Integration
# ============================================================================


class TestRulesEngine:
    """Integration tests for rules/engine.py apply_rules()."""

    def test_happy_path_authorise(self):
        from rules.engine import apply_rules

        request = _make_request()
        result = apply_rules(
            request,
            _make_clauses(),
            _make_policy_status(),
            _make_wp(),
        )

        assert isinstance(result, AdjudicationResult)
        assert result.recommendation == Recommendation.RECOMMEND_AUTHORISE
        assert result.total_claimed > Decimal("0")
        assert result.policy_status == "ACTIVE"
        assert result.waiting_period_clear is True

    def test_lapsed_policy_deny(self):
        from rules.engine import apply_rules

        request = _make_request()
        result = apply_rules(
            request,
            _make_clauses(),
            _make_policy_status(is_active=False, status="LAPSED"),
            _make_wp(),
        )

        assert result.recommendation == Recommendation.RECOMMEND_DENY
        assert result.total_approved == Decimal("0")
        assert result.policy_status == "LAPSED"

    def test_ped_escalation_trigger(self):
        from rules.engine import apply_rules

        request = _make_request(is_pre_existing=True)
        result = apply_rules(
            request,
            _make_clauses(),
            _make_policy_status(),
            _make_wp(),
        )

        assert "PED-flagged diagnosis" in result.escalation_triggers

    def test_high_value_escalation_trigger(self):
        from rules.engine import apply_rules

        items = [
            CostLineItem(item="Surgery Package", amount=Decimal("600000.00"),
                         category=CostCategory.SURGEON_FEE),
        ]
        request = _make_request(
            line_items=items,
            total_amount=Decimal("600000.00"),
            sum_insured=Decimal("1000000.00"),
        )
        result = apply_rules(
            request,
            _make_clauses(),
            _make_policy_status(remaining_si=Decimal("1000000.00")),
            _make_wp(),
        )

        assert any("claim value" in t.lower() for t in result.escalation_triggers)

    def test_non_network_escalation_trigger(self):
        from rules.engine import apply_rules

        request = _make_request(network_tier=NetworkTier.NON_NETWORK)
        result = apply_rules(
            request,
            _make_clauses(),
            _make_policy_status(),
            _make_wp(),
        )

        assert "Non-network hospital" in result.escalation_triggers

    def test_copay_applied_correctly(self):
        from rules.engine import apply_rules

        request = _make_request(co_pay_pct=Decimal("10.00"))
        result = apply_rules(
            request,
            _make_clauses(),
            _make_policy_status(),
            _make_wp(),
        )

        copay_deds = [d for d in result.deductions
                      if d.category == DeductionCategory.CO_PAY]
        assert len(copay_deds) == 1
        assert copay_deds[0].deducted_amount > Decimal("0")

    def test_every_deduction_has_citation(self):
        """Guardrail #2: Every deduction must have a non-empty clause citation."""
        from rules.engine import apply_rules

        # Use a case with co-pay to ensure at least one deduction
        request = _make_request(co_pay_pct=Decimal("20.00"))
        result = apply_rules(
            request,
            _make_clauses(),
            _make_policy_status(),
            _make_wp(),
        )

        for deduction in result.deductions:
            assert deduction.clause_citation, (
                f"Deduction {deduction.category} is missing a clause citation "
                "(Guardrail #2 violation)"
            )
            assert deduction.source_document, (
                f"Deduction {deduction.category} is missing a source document"
            )
