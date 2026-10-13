"""
rules/waiting_period.py
-----------------------
Rule module: Waiting period checks.

Evaluates whether the claim falls within any applicable waiting period:
    1. 30-day initial waiting period (from policy inception).
    2. 2-year specific disease waiting period (cataract, hernia, etc.).
    3. 4-year pre-existing disease (PED) waiting period.

Mandatory adversarial case: Claim inside a waiting period (Metrics.md).

Usage:
    from rules.waiting_period import check_waiting_period
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING

from rules.models import Deduction, DeductionCategory, WaitingPeriodInfo

if TYPE_CHECKING:
    from schemas import PreAuthRequest
    from retrieval.vector_store import RetrievedClause

logger = logging.getLogger(__name__)

# ICD-10 codes subject to the 2-year specific disease waiting period.
# These are diseases that insurers commonly place under specific waiting
# periods per IRDAI guidelines.
SPECIFIC_DISEASE_ICD10_PREFIXES = {
    "H25", "H26",  # Cataract
    "K40", "K41", "K42", "K43", "K44", "K45", "K46",  # Hernia
    "N40",  # Benign prostatic hypertrophy
    "K80",  # Gallstones / Cholelithiasis
    "H40",  # Glaucoma
    "M17",  # Gonarthrosis (knee)
    "I84",  # Haemorrhoids
    "J34",  # Nasal septum deviation / Sinusitis
    "N20", "N21",  # Urolithiasis (kidney/ureter stones)
}


def check_waiting_period(
    request: "PreAuthRequest",
    waiting_period: WaitingPeriodInfo,
    clauses: list["RetrievedClause"],
) -> dict:
    """Check if the claim falls within any applicable waiting period.

    Sequential checks:
        1. Initial 30-day waiting period — applies to all claims.
        2. Specific disease 2-year waiting period — applies to listed conditions.
        3. PED 4-year waiting period — applies if diagnosis is flagged pre-existing.

    Args:
        request: The PreAuthRequest to evaluate.
        waiting_period: Waiting period info from the mock API.
        clauses: Retrieved clauses for citation.

    Returns:
        Dict with:
        - "deductions": list[Deduction]
        - "reasoning": str
        - "is_clear": bool — True if all waiting periods have elapsed
    """
    deductions: list[Deduction] = []
    reasoning_parts: list[str] = []

    # --- Check 0: Endorsement Reversal (Adversarial / Priority Endorsement) ---
    # Per Metrics.md, an endorsement can explicitly reverse or waive the base policy wording.
    endorsement_clause = _find_endorsement_waiver(clauses)
    if endorsement_clause:
        endorsement_text = getattr(endorsement_clause, "chunk_text", "")
        endorsement_doc = getattr(endorsement_clause, "source_file", "")
        reasoning_parts.append(
            "ENDORSEMENT REVERSAL APPLIED: An active policy endorsement was retrieved that expressly "
            "waives specific disease and waiting periods, superseding and reversing the base policy exclusion."
        )
        return {
            "deductions": [],
            "reasoning": "\n".join(reasoning_parts),
            "is_clear": True,
            "endorsement_applied": True,
            "endorsement_citation": endorsement_text[:300],
        }

    # --- Check 1: Initial 30-day waiting period ---
    if not waiting_period.initial_wp_clear:
        reasoning_parts.append(
            f"Initial 30-day waiting period NOT elapsed. "
            f"Days since inception: {waiting_period.days_elapsed}. "
            "Claim is within the initial waiting period."
        )

        citation = _find_wp_clause(clauses, "initial waiting period", "30 day")

        deductions.append(
            Deduction(
                category=DeductionCategory.WAITING_PERIOD,
                original_amount=request.cost_estimate.total_amount,
                allowed_amount=Decimal("0"),
                deducted_amount=request.cost_estimate.total_amount,
                clause_citation=citation,
                source_document=_find_wp_source(clauses, "initial waiting period"),
                explanation=(
                    f"Claim is within the initial 30-day waiting period. "
                    f"Only {waiting_period.days_elapsed} days have elapsed "
                    "since policy inception."
                ),
            )
        )

        return {
            "deductions": deductions,
            "reasoning": "\n".join(reasoning_parts),
            "is_clear": False,
        }

    reasoning_parts.append(
        f"Initial 30-day waiting period: CLEAR ({waiting_period.days_elapsed} days elapsed)."
    )

    # --- Check 2: Specific disease 2-year waiting period ---
    icd_code = request.diagnosis.icd10_code or ""
    icd_prefix = icd_code.split(".")[0] if icd_code else ""

    is_specific_disease = icd_prefix in SPECIFIC_DISEASE_ICD10_PREFIXES

    if is_specific_disease and not waiting_period.specific_disease_wp_clear:
        reasoning_parts.append(
            f"Diagnosis {icd_code} ({request.diagnosis.description}) is on the "
            "specific disease list. 2-year waiting period NOT elapsed."
        )

        citation = _find_wp_clause(clauses, "specific disease", "2 year", "24 month")

        deductions.append(
            Deduction(
                category=DeductionCategory.WAITING_PERIOD,
                original_amount=request.cost_estimate.total_amount,
                allowed_amount=Decimal("0"),
                deducted_amount=request.cost_estimate.total_amount,
                clause_citation=citation,
                source_document=_find_wp_source(clauses, "specific disease"),
                explanation=(
                    f"Diagnosis '{request.diagnosis.description}' (ICD-10: {icd_code}) "
                    "is subject to a 2-year specific disease waiting period which "
                    "has not yet elapsed."
                ),
            )
        )

        return {
            "deductions": deductions,
            "reasoning": "\n".join(reasoning_parts),
            "is_clear": False,
        }

    if is_specific_disease:
        reasoning_parts.append(
            f"Specific disease ({icd_code}) 2-year waiting period: CLEAR."
        )

    # --- Check 3: Pre-existing disease 4-year waiting period ---
    if request.diagnosis.is_pre_existing and not waiting_period.ped_wp_clear:
        reasoning_parts.append(
            f"Diagnosis flagged as pre-existing. 4-year PED waiting period NOT elapsed."
        )

        citation = _find_wp_clause(clauses, "pre-existing", "4 year", "48 month", "PED")

        deductions.append(
            Deduction(
                category=DeductionCategory.PED_EXCLUSION,
                original_amount=request.cost_estimate.total_amount,
                allowed_amount=Decimal("0"),
                deducted_amount=request.cost_estimate.total_amount,
                clause_citation=citation,
                source_document=_find_wp_source(clauses, "pre-existing"),
                explanation=(
                    f"Diagnosis '{request.diagnosis.description}' is flagged as "
                    "pre-existing. The 4-year PED waiting period has not yet elapsed."
                ),
            )
        )

        return {
            "deductions": deductions,
            "reasoning": "\n".join(reasoning_parts),
            "is_clear": False,
        }

    if request.diagnosis.is_pre_existing:
        reasoning_parts.append("PED 4-year waiting period: CLEAR.")

    reasoning_parts.append("All applicable waiting periods: CLEAR.")

    return {
        "deductions": deductions,
        "reasoning": "\n".join(reasoning_parts),
        "is_clear": True,
    }


def _find_wp_clause(clauses: list["RetrievedClause"], *keywords: str) -> str:
    """Find the most relevant waiting-period clause."""
    for clause in clauses:
        text_lower = clause.chunk_text.lower()
        if any(kw.lower() in text_lower for kw in keywords):
            return clause.chunk_text[:500]
    if clauses:
        return clauses[0].chunk_text[:500]
    return "Policy terms specify applicable waiting periods from date of inception."


def _find_wp_source(clauses: list["RetrievedClause"], *keywords: str) -> str:
    """Find source document for waiting period clause."""
    for clause in clauses:
        text_lower = clause.chunk_text.lower()
        if any(kw.lower() in text_lower for kw in keywords):
            doc = clause.source_file
            if clause.circular_date:
                doc += f" (dated {clause.circular_date})"
            return doc
    if clauses:
        return clauses[0].source_file
    return "policy_wording_general.txt"


def _find_endorsement_waiver(clauses: list["RetrievedClause"]) -> Optional["RetrievedClause"]:
    """Check if retrieved clauses include an endorsement waiving waiting periods."""
    for clause in clauses:
        text = getattr(clause, "chunk_text", "") or ""
        doc = getattr(clause, "source_document", "") or getattr(clause, "source_file", "") or ""
        text_lower = text.lower()
        doc_lower = doc.lower()
        if ("endorsement" in text_lower or "endorsement" in doc_lower) and (
            "waiv" in text_lower or "waiver" in text_lower or "delete" in text_lower
        ) and ("waiting period" in text_lower or "specific disease" in text_lower or "ped" in text_lower):
            return clause
    return None
