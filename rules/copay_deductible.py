"""
rules/copay_deductible.py
-------------------------
Rule module: Co-pay and deductible calculations.

Applies:
    1. Co-pay percentage from policy.co_pay_pct.
    2. Deductible for top-up/super-top-up plans (threshold deductible
       below which the policyholder bears the cost).

Usage:
    from rules.copay_deductible import apply_copay_deductible
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


def apply_copay_deductible(
    request: "PreAuthRequest",
    clauses: list["RetrievedClause"],
) -> dict:
    """Apply co-pay percentage and deductible to the claim.

    Logic:
        1. If policy.co_pay_pct > 0, compute co-pay on total claimed amount.
        2. If plan_type is TOP_UP or SUPER_TOP_UP, apply threshold deductible.

    Args:
        request: The PreAuthRequest to evaluate.
        clauses: Retrieved clauses for citation.

    Returns:
        Dict with "deductions" and "reasoning".
    """
    deductions: list[Deduction] = []
    reasoning_parts: list[str] = []

    total_claimed = request.cost_estimate.total_amount
    co_pay_pct = request.policy.co_pay_pct

    # --- Co-pay ---
    if co_pay_pct > Decimal("0"):
        co_pay_amount = (total_claimed * co_pay_pct / Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        citation = _find_clause(clauses, "co-pay", "copay", "co pay")

        deductions.append(
            Deduction(
                category=DeductionCategory.CO_PAY,
                original_amount=total_claimed,
                allowed_amount=total_claimed - co_pay_amount,
                deducted_amount=co_pay_amount,
                clause_citation=citation,
                source_document=_find_source(clauses, "co-pay", "copay"),
                explanation=(
                    f"Co-pay of {co_pay_pct}% applied: "
                    f"₹{total_claimed:,.2f} × {co_pay_pct}% = ₹{co_pay_amount:,.2f} "
                    "borne by the insured."
                ),
            )
        )

        reasoning_parts.append(
            f"Co-pay applied: {co_pay_pct}% of ₹{total_claimed:,.2f} = "
            f"₹{co_pay_amount:,.2f}."
        )
    else:
        reasoning_parts.append("Co-pay: 0% — no co-pay applicable.")

    # --- Deductible (top-up / super-top-up) ---
    plan_type = request.policy.plan_type.value
    if plan_type in ("top_up", "super_top_up"):
        # TODO: Retrieve deductible threshold from policy data.
        # For now, this is a stub — the deductible amount will come from
        # the mock Policy Admin API or policy.sub_limits in a future iteration.
        reasoning_parts.append(
            f"Plan type is {plan_type} — deductible check will be applied "
            "once threshold data is available from the Policy Admin API."
        )

    if not deductions:
        reasoning_parts.append("Co-pay and deductible checks: No deductions applied.")

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
    return "Policy schedule specifies the applicable co-payment percentage."


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
