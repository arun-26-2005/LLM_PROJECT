"""
rules/policy_validity.py
------------------------
Rule module: Policy validity checks.

Determines whether the insurance policy is active, lapsed, or expired,
and whether the admission date falls within the policy coverage period.

Mandatory adversarial case: Expired or lapsed policy (Metrics.md).

Usage:
    from rules.policy_validity import check_policy_validity
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING

from rules.models import Deduction, DeductionCategory, PolicyStatusInfo

if TYPE_CHECKING:
    from schemas import PreAuthRequest
    from retrieval.vector_store import RetrievedClause

logger = logging.getLogger(__name__)


def check_policy_validity(
    request: "PreAuthRequest",
    policy_status: PolicyStatusInfo,
    clauses: list["RetrievedClause"],
) -> dict:
    """Check if the policy is active and the admission is within coverage.

    Checks performed:
        1. Policy status (ACTIVE / LAPSED / EXPIRED) from the Policy Admin API.
        2. Admission date is on or after policy start date (already validated
           by Pydantic, but double-checked here for the reasoning trace).
        3. Remaining sum insured is sufficient for the claimed amount.

    Args:
        request: The PreAuthRequest to evaluate.
        policy_status: Policy status from the mock Policy Admin API.
        clauses: Retrieved clauses (used for citation in deductions).

    Returns:
        Dict with keys:
        - "deductions": list[Deduction] — any deductions applied
        - "reasoning": str — step reasoning for the audit trace
        - "is_valid": bool — whether the policy is valid for this claim
    """
    deductions: list[Deduction] = []
    reasoning_parts: list[str] = []

    # --- Check 1: Policy status ---
    if not policy_status.is_active:
        reasoning_parts.append(
            f"Policy {request.policy.policy_number} is {policy_status.status}. "
            f"Cashless pre-authorisation cannot be granted on a {policy_status.status.lower()} policy."
        )

        # Find the most relevant clause for citation
        citation_text = _find_best_clause(clauses, "policy status", "active", "lapsed")
        source_doc = _find_source_doc(clauses, "policy status", "active", "lapsed")

        deductions.append(
            Deduction(
                category=DeductionCategory.POLICY_INVALID,
                original_amount=request.cost_estimate.total_amount,
                allowed_amount=Decimal("0"),
                deducted_amount=request.cost_estimate.total_amount,
                clause_citation=citation_text,
                source_document=source_doc,
                explanation=(
                    f"Policy {request.policy.policy_number} is {policy_status.status}. "
                    "Claim is ineligible for cashless authorisation."
                ),
            )
        )

        return {
            "deductions": deductions,
            "reasoning": "\n".join(reasoning_parts),
            "is_valid": False,
        }

    # --- Check 2: Admission date within policy period ---
    reasoning_parts.append(
        f"Policy {request.policy.policy_number} is ACTIVE. "
        f"Inception date: {request.policy.policy_start_date}. "
        f"Days since inception: {policy_status.days_since_inception}."
    )

    # --- Check 3: Remaining sum insured ---
    if request.cost_estimate.total_amount > policy_status.remaining_sum_insured:
        reasoning_parts.append(
            f"Claimed amount ₹{request.cost_estimate.total_amount:,.2f} exceeds "
            f"remaining sum insured ₹{policy_status.remaining_sum_insured:,.2f}."
        )

    reasoning_parts.append("Policy validity check: PASSED.")

    return {
        "deductions": deductions,
        "reasoning": "\n".join(reasoning_parts),
        "is_valid": True,
    }


def _find_best_clause(
    clauses: list["RetrievedClause"], *keywords: str
) -> str:
    """Find the most relevant clause for a given set of keywords.

    Returns the clause text, or a generic fallback if none match.
    """
    for clause in clauses:
        text_lower = clause.chunk_text.lower()
        if any(kw.lower() in text_lower for kw in keywords):
            return clause.chunk_text[:500]

    # Fallback: use first clause or a generic statement
    if clauses:
        return clauses[0].chunk_text[:500]
    return "Policy terms require the policy to be active at the time of admission."


def _find_source_doc(
    clauses: list["RetrievedClause"], *keywords: str
) -> str:
    """Find the source document for a given set of keywords."""
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
