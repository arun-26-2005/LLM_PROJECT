"""
rules/exclusions.py
-------------------
Rule module: IRDAI exclusion and non-payable item checks.

Evaluates each cost line item against:
    1. IRDAI Non-Payable Items List (List I–IV): administrative charges,
       personal comfort items, disposable supplies.
    2. Permanent Exclusions: cosmetic surgery, self-inflicted injury,
       substance abuse, war/terrorism, hazardous activities.

Guardrail #2: Every exclusion deduction cites the specific IRDAI list or
policy exclusion clause.
Guardrail #6: IRDAI non-payable references include the circular date.

Usage:
    from rules.exclusions import check_exclusions
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING

from rules.models import Deduction, DeductionCategory

if TYPE_CHECKING:
    from schemas import PreAuthRequest
    from retrieval.vector_store import RetrievedClause

logger = logging.getLogger(__name__)

# IRDAI Non-Payable Items — simplified keyword list for matching against
# line item descriptions. In production, this would be a structured lookup
# against the official IRDAI Non-Payable Schedule.
NON_PAYABLE_KEYWORDS = {
    # List I: Items that are not part of treatment
    "registration", "admission charges", "service charge",
    "documentation", "filing charges",
    # List II: Items related to comfort/convenience
    "telephone", "tv", "guest bed", "extra diet",
    "laundry", "mineral water", "toiletry",
    # List III: Disposable medical consumables (often debated)
    "gloves", "mask", "gown", "cap", "shoe cover",
    "ppe", "hand sanitizer",
    # List IV: External durable equipment / non-medical
    "wheelchair", "walker", "crutch",
}

# Permanent exclusion diagnosis keywords
PERMANENT_EXCLUSION_KEYWORDS = {
    "cosmetic", "aesthetic", "self-inflicted", "self inflicted",
    "substance abuse", "alcohol", "drug abuse",
    "hazardous sport", "adventure sport",
    "war", "terrorism", "nuclear",
}


def check_exclusions(
    request: "PreAuthRequest",
    clauses: list["RetrievedClause"],
) -> dict:
    """Check cost line items against IRDAI non-payables and permanent exclusions.

    Args:
        request: The PreAuthRequest to evaluate.
        clauses: Retrieved clauses for citation.

    Returns:
        Dict with "deductions" and "reasoning".
    """
    deductions: list[Deduction] = []
    reasoning_parts: list[str] = []

    # --- Check 1: Non-payable line items ---
    for item in request.cost_estimate.line_items:
        item_desc_lower = item.item.lower()

        # Check against non-payable keywords
        matched_keyword = None
        for keyword in NON_PAYABLE_KEYWORDS:
            if keyword in item_desc_lower:
                matched_keyword = keyword
                break

        # Also check if category is explicitly NON_PAYABLE
        if item.category.value == "non_payable" or matched_keyword:
            citation = _find_clause(clauses, "non-payable", "non payable", "exclusion")

            deductions.append(
                Deduction(
                    category=DeductionCategory.NON_PAYABLE,
                    line_item=item.item,
                    original_amount=item.amount,
                    allowed_amount=Decimal("0"),
                    deducted_amount=item.amount,
                    clause_citation=citation,
                    source_document=_find_source(clauses, "non-payable", "IRDAI"),
                    explanation=(
                        f"'{item.item}' identified as non-payable item "
                        f"(matched: '{matched_keyword or item.category.value}'). "
                        "Deducted per IRDAI Non-Payable Items Schedule."
                    ),
                )
            )

            reasoning_parts.append(
                f"Non-payable: '{item.item}' (₹{item.amount:,.2f}) — excluded."
            )

    # --- Check 2: Permanent exclusions based on diagnosis ---
    diag_lower = request.diagnosis.description.lower()
    for keyword in PERMANENT_EXCLUSION_KEYWORDS:
        if keyword in diag_lower:
            citation = _find_clause(clauses, "permanent exclusion", keyword)

            deductions.append(
                Deduction(
                    category=DeductionCategory.PERMANENT_EXCLUSION,
                    original_amount=request.cost_estimate.total_amount,
                    allowed_amount=Decimal("0"),
                    deducted_amount=request.cost_estimate.total_amount,
                    clause_citation=citation,
                    source_document=_find_source(clauses, "exclusion"),
                    explanation=(
                        f"Diagnosis '{request.diagnosis.description}' matches "
                        f"permanent exclusion keyword '{keyword}'. "
                        "Entire claim is excluded under policy terms."
                    ),
                )
            )

            reasoning_parts.append(
                f"PERMANENT EXCLUSION: '{request.diagnosis.description}' "
                f"matches exclusion '{keyword}'."
            )
            break  # One permanent exclusion is enough to deny

    if not deductions:
        reasoning_parts.append("Exclusion checks: No non-payable or excluded items found.")

    return {
        "deductions": deductions,
        "reasoning": "\n".join(reasoning_parts),
    }


def _find_clause(clauses: list["RetrievedClause"], *keywords: str) -> str:
    """Find the most relevant clause."""
    for clause in clauses:
        text_lower = clause.chunk_text.lower()
        if any(kw.lower() in text_lower for kw in keywords):
            return clause.chunk_text[:500]
    if clauses:
        return clauses[0].chunk_text[:500]
    return "IRDAI Non-Payable Items Schedule and policy exclusion clauses apply."


def _find_source(clauses: list["RetrievedClause"], *keywords: str) -> str:
    """Find source document."""
    for clause in clauses:
        text_lower = clause.chunk_text.lower()
        if any(kw.lower() in text_lower for kw in keywords):
            doc = clause.source_file
            if clause.circular_date:
                doc += f" (dated {clause.circular_date})"
            return doc
    if clauses:
        return clauses[0].source_file
    return "irdai_non_payables_schedule.txt"
