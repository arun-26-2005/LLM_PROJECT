"""
tests/test_adversarial_extensions.py
------------------------------------
Tests the 3 advanced adversarial scenarios mandated by Metrics.md:
  1. Document in an unexpected language (Hindi / Devanagari)
  2. Illegible scan (heavy blur / degraded document)
  3. Endorsement that reverses the base wording
"""

import os
from datetime import date, timedelta
from decimal import Decimal

import pytest

from schemas import (
    PreAuthRequest,
    Patient,
    Policy,
    Hospital,
    Diagnosis,
    Procedure,
    CostEstimate,
    CostLineItem,
    CostCategory,
    PlanType,
    NetworkTier,
    AdmissionType,
    Gender,
    HospitalCategory,
    SourceFormat,
)
from intake import process_intake
from orchestration.graph import run_pipeline


class TestUnexpectedLanguage:
    """Tests handling of medical notes in unexpected languages (Hindi/Devanagari)."""

    def test_hindi_document_detection_and_query_notice(self):
        hindi_text_path = "data/synthetic_docs/txt/adversarial_unexpected_language_hindi.txt"
        assert os.path.exists(hindi_text_path), f"File {hindi_text_path} does not exist"

        result = process_intake(hindi_text_path)
        assert result.is_success is False
        assert result.confidence_score <= 0.2
        assert "Devanagari" in result.validation_errors[0] or "language" in result.validation_errors[0].lower()
        assert result.pending_query_notice is not None
        assert "DEFICIENCY" in result.pending_query_notice or "translation" in result.pending_query_notice.lower()


class TestIllegibleScan:
    """Tests handling of unreadable / heavily degraded scan documents."""

    def test_illegible_scan_rejection(self):
        scan_path = "data/synthetic_docs/images/adversarial_illegible_scan.png"
        assert os.path.exists(scan_path), f"File {scan_path} does not exist"

        result = process_intake(scan_path)
        assert result.is_success is False
        assert result.request is None
        assert len(result.validation_errors) > 0


class TestEndorsementReversal:
    """Tests that an active endorsement document reverses base policy waiting periods."""

    def test_cataract_approved_under_endorsement_waiver(self):
        # A claim for Cataract (H26.9) submitted only 90 days after policy inception.
        # Under base policy: denied (2-year waiting period not elapsed).
        # Under endorsement: approved (endorsement explicitly waives 2-year waiting period).
        endorsed_req = PreAuthRequest(
            submitted_at=date.today(),
            source_format=SourceFormat.FORM,
            patient=Patient(
                full_name="Anil Kapoor",
                age=55,
                gender=Gender.MALE,
                policy_number="POL-ENDORSED-778899",
            ),
            policy=Policy(
                policy_number="POL-ENDORSED-778899",
                plan_type=PlanType.GROUP,
                sum_insured=Decimal("500000.00"),
                policy_start_date=date.today() - timedelta(days=90),
            ),
            hospital=Hospital(
                name="Apollo Hospital, Delhi",
                city="Delhi",
                network_tier=NetworkTier.CASHLESS_NETWORK,
                category=HospitalCategory.MULTI_SPECIALTY,
            ),
            diagnosis=Diagnosis(
                icd10_code="H26.9",
                description="Cataract, unspecified with Endorsement waiver",
                is_pre_existing=False,
            ),
            procedure=Procedure(
                procedure_code="CPT-66984",
                description="Phacoemulsification with IOL",
                admission_type=AdmissionType.DAY_CARE,
            ),
            cost_estimate=CostEstimate(
                line_items=[
                    CostLineItem(
                        item="Cataract Procedure",
                        amount=Decimal("35000.00"),
                        category=CostCategory.OTHER,
                    )
                ],
                total_amount=Decimal("35000.00"),
            ),
        )

        pipeline_res = run_pipeline({"is_success": True, "request": endorsed_req.model_dump()})

        # Under the endorsement reversal, the claim must be recommended for authorization
        raw_rec = pipeline_res.get("recommendation")
        rec_str = raw_rec.value if hasattr(raw_rec, "value") else str(raw_rec)
        assert rec_str in ["RECOMMEND_AUTHORISE", "APPROVE", "AUTHORISE"]

        adj = pipeline_res.get("adjudication_result")
        total_approved = Decimal(str(adj.get("total_approved", "0")))
        assert total_approved == Decimal("35000.00")

        # Verify no waiting period deductions were taken
        wp_deductions = [d for d in adj.get("deductions", []) if d.get("category") == "waiting_period"]
        assert len(wp_deductions) == 0
