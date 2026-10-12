"""
rules/sub_limits.py
-------------------
Rule module: Sub-limit and room-rent capping with proportionate deduction.

Applies two types of sub-limit logic:
    1. Room rent capping — if daily room rent exceeds the policy cap, the excess
       is deducted AND proportionate deductions are applied to surgeon, anaesthesia,
       and other fees.
    2. Procedure-specific sub-limits — caps from policy.sub_limits.limits.

Mandatory adversarial case: Claim on threshold boundary (Metrics.md).

Usage:
    from rules.sub_limits import apply_sub_limits
"""

from __future__ import annotations

import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import TYPE_CHECKING

from rules.models import Deduction, DeductionCategory

if TYPE_CHECKING:
    from schemas import PreAuthRequest
    from retrieval.vector_store import RetrievedClause

logger = logging.getLogger(__name__)

# Cost categories subject to proportionate deduction when room rent is capped.
PROPORTIONATE_CATEGORIES = {
    "surgeon_fee",
    "anaesthesia_fee",
    "consultation_fee",
    "diagnostic",
    "pharmacy",
}


def apply_sub_limits(
    request: "PreAuthRequest",
    clauses: list["RetrievedClause"],
) -> dict:
    """Apply sub-limit capping and room-rent proportionate deduction.

    Logic:
        1. Check if room_rent line item exceeds policy sub-limit for room_rent_per_day.
        2. If yes, compute proportionate deduction ratio and apply to all
           PROPORTIONATE_CATEGORIES line items.
        3. Check procedure-specific sub-limits from policy.sub_limits.limits.

    Args:
        request: The PreAuthRequest to evaluate.
        clauses: Retrieved clauses for citation.

    Returns:
        Dict with "deductions" and "reasoning".
    """
    deductions: list[Deduction] = []
    reasoning_parts: list[str] = []

    sub_limits = request.policy.sub_limits.limits

    # --- Room rent capping ---
    room_rent_cap = sub_limits.get("room_rent_per_day")

    if room_rent_cap is not None:
        room_rent_cap = Decimal(str(room_rent_cap))

        # Find room_rent line item(s)
        for item in request.cost_estimate.line_items:
            if item.category.value == "room_rent" and item.amount > room_rent_cap:
                excess = item.amount - room_rent_cap
                ratio = room_rent_cap / item.amount  # proportion allowed

                citation = _find_clause(clauses, "room rent", "sub-limit", "capping")

                deductions.append(
                    Deduction(
                        category=DeductionCategory.ROOM_RENT_CAPPING,
                        line_item=item.item,
                        original_amount=item.amount,
                        allowed_amount=room_rent_cap,
                        deducted_amount=excess,
                        clause_citation=citation,
                        source_document=_find_source(clauses, "room rent", "sub-limit"),
                        explanation=(
                            f"Room rent ₹{item.amount:,.2f} exceeds policy cap "
                            f"₹{room_rent_cap:,.2f}/day. Excess ₹{excess:,.2f} deducted."
                        ),
                    )
                )

                reasoning_parts.append(
                    f"Room rent capped: ₹{item.amount:,.2f} → ₹{room_rent_cap:,.2f}. "
                    f"Proportionate ratio: {ratio:.4f}."
                )

                # Apply proportionate deduction to related categories
                for related_item in request.cost_estimate.line_items:
                    if related_item.category.value in PROPORTIONATE_CATEGORIES:
                        allowed = (related_item.amount * ratio).quantize(
                            Decimal("0.01"), rounding=ROUND_HALF_UP
                        )
                        deducted = related_item.amount - allowed

                        if deducted > Decimal("0"):
                            deductions.append(
                                Deduction(
                                    category=DeductionCategory.PROPORTIONATE_DEDUCTION,
                                    line_item=related_item.item,
                                    original_amount=related_item.amount,
                                    allowed_amount=allowed,
                                    deducted_amount=deducted,
                                    clause_citation=citation,
                                    source_document=_find_source(clauses, "proportionate"),
                                    explanation=(
                                        f"Proportionate deduction on {related_item.item}: "
                                        f"₹{related_item.amount:,.2f} × {ratio:.4f} = "
                                        f"₹{allowed:,.2f} (deducted ₹{deducted:,.2f})."
                                    ),
                                )
                            )

                break  # Only process first room_rent line item

    if not deductions:
        reasoning_parts.append("Room rent and sub-limit checks: No capping applied.")
    else:
        reasoning_parts.append(
            f"Sub-limit checks: {len(deductions)} deduction(s) applied."
        )

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
    return "Policy schedule specifies applicable sub-limits and room rent caps."


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
    return "policy_benefit_schedule.txt"
