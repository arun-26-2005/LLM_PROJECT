"""
rules/engine.py
---------------
Master rules orchestrator — sequentially applies all rule modules and
produces an AdjudicationResult with a RECOMMEND_* recommendation.

Guardrail Compliance:
    #1: Output is always RECOMMEND_* (never auto-approves).
    #2: Every Deduction carries a clause citation.
    #5: Only risk-relevant features are used (diagnosis, procedure, policy terms).
    #7: Explicit escalation triggers are identified.

Architecture Role:
    Called by the orchestration graph's `apply_rules_engine` node.
    Receives the PreAuthRequest + retrieved clauses + policy status from
    the mock API, and returns a fully cited AdjudicationResult.

Usage:
    from rules.engine import apply_rules
    result = apply_rules(request, clauses, policy_status)
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING

from rules.models import (
    AdjudicationResult,
    Deduction,
    DeductionCategory,
    PolicyStatusInfo,
    Recommendation,
    WaitingPeriodInfo,
)
from rules.policy_validity import check_policy_validity
from rules.waiting_period import check_waiting_period
from rules.sub_limits import apply_sub_limits
from rules.copay_deductible import apply_copay_deductible
from rules.exclusions import check_exclusions
from rules.fairness import verify_fairness

if TYPE_CHECKING:
    from schemas import PreAuthRequest
    from retrieval.vector_store import RetrievedClause

logger = logging.getLogger(__name__)


def apply_rules(
    request: "PreAuthRequest",
    clauses: list["RetrievedClause"],
    policy_status: PolicyStatusInfo,
    waiting_period: WaitingPeriodInfo,
) -> AdjudicationResult:
    """Sequentially apply all rule modules and produce a recommendation.

    Rule application order (each may short-circuit to DENY):
        1. Policy validity   — DENY if policy is lapsed/expired
        2. Waiting period     — DENY if within applicable waiting period
        3. Exclusions         — Filter non-payable line items
        4. Sub-limits         — Cap room rent + proportionate deduction
        5. Co-pay/deductible  — Apply co-pay percentage
        6. Fairness check     — Verify no protected-proxy attributes used
        7. Aggregate          — Compute totals, determine recommendation

    Args:
        request: The validated PreAuthRequest from Member 1's extraction.
        clauses: Retrieved policy/regulatory clauses from the vector store.
        policy_status: Policy status info from the mock Policy Admin API.
        waiting_period: Waiting period evaluation from the mock API.

    Returns:
        AdjudicationResult with recommendation, deductions, and reasoning trace.
    """
    deductions: list[Deduction] = []
    reasoning_steps: list[str] = []
    escalation_triggers: list[str] = []
    missing_info: list[str] = []

    total_claimed = request.cost_estimate.total_amount

    # ---------------------------------------------------------------
    # Step 1: Policy validity
    # ---------------------------------------------------------------
    validity_result = check_policy_validity(request, policy_status, clauses)
    deductions.extend(validity_result.get("deductions", []))
    reasoning_steps.append(validity_result.get("reasoning", ""))

    if not policy_status.is_active:
        logger.info("Policy %s is %s — recommending DENY.", request.policy.policy_number, policy_status.status)
        return AdjudicationResult(
            request_id=request.request_id,
            recommendation=Recommendation.RECOMMEND_DENY,
            confidence_score=0.95,
            total_claimed=total_claimed,
            total_approved=Decimal("0"),
            total_deducted=total_claimed,
            deductions=deductions,
            policy_status=policy_status.status,
            waiting_period_clear=True,
            reasoning_trace="\n".join(reasoning_steps),
        )

    # ---------------------------------------------------------------
    # Step 2: Waiting period
    # ---------------------------------------------------------------
    wp_result = check_waiting_period(request, waiting_period, clauses)
    deductions.extend(wp_result.get("deductions", []))
    reasoning_steps.append(wp_result.get("reasoning", ""))

    if not wp_result.get("is_clear", True):
        logger.info("Claim within waiting period — recommending DENY.")
        return AdjudicationResult(
            request_id=request.request_id,
            recommendation=Recommendation.RECOMMEND_DENY,
            confidence_score=0.90,
            total_claimed=total_claimed,
            total_approved=Decimal("0"),
            total_deducted=total_claimed,
            deductions=deductions,
            policy_status=policy_status.status,
            waiting_period_clear=False,
            reasoning_trace="\n".join(reasoning_steps),
        )

    # ---------------------------------------------------------------
    # Step 3: Exclusions (IRDAI non-payables, permanent exclusions)
    # ---------------------------------------------------------------
    exclusion_result = check_exclusions(request, clauses)
    deductions.extend(exclusion_result.get("deductions", []))
    reasoning_steps.append(exclusion_result.get("reasoning", ""))

    # ---------------------------------------------------------------
    # Step 4: Sub-limits and room-rent capping
    # ---------------------------------------------------------------
    sublimit_result = apply_sub_limits(request, clauses)
    deductions.extend(sublimit_result.get("deductions", []))
    reasoning_steps.append(sublimit_result.get("reasoning", ""))

    # ---------------------------------------------------------------
    # Step 5: Co-pay and deductible
    # ---------------------------------------------------------------
    copay_result = apply_copay_deductible(request, clauses)
    deductions.extend(copay_result.get("deductions", []))
    reasoning_steps.append(copay_result.get("reasoning", ""))

    # ---------------------------------------------------------------
    # Step 6: Fairness verification (Guardrail #5)
    # ---------------------------------------------------------------
    fairness_ok = verify_fairness(request, deductions)
    if not fairness_ok:
        escalation_triggers.append("Fairness check failed — potential proxy attribute usage detected.")

    # ---------------------------------------------------------------
    # Step 7: Aggregate and determine recommendation
    # ---------------------------------------------------------------
    total_deducted = sum(d.deducted_amount for d in deductions)
    total_approved = max(total_claimed - total_deducted, Decimal("0"))

    # Determine escalation triggers (Guardrail #7)
    if total_claimed > Decimal("500000"):
        escalation_triggers.append(f"High claim value (₹{total_claimed:,.2f})")

    if request.diagnosis.is_pre_existing:
        escalation_triggers.append("PED-flagged diagnosis")

    if request.hospital.network_tier.value == "non_network":
        escalation_triggers.append("Non-network hospital")

    # Determine recommendation
    if missing_info:
        recommendation = Recommendation.RECOMMEND_QUERY
        confidence = 0.50
    elif total_deducted >= total_claimed:
        recommendation = Recommendation.RECOMMEND_DENY
        confidence = 0.85
    else:
        recommendation = Recommendation.RECOMMEND_AUTHORISE
        confidence = 0.80

    # Lower confidence if escalation triggers exist
    if escalation_triggers:
        confidence = min(confidence, 0.65)

    return AdjudicationResult(
        request_id=request.request_id,
        recommendation=recommendation,
        confidence_score=confidence,
        total_claimed=total_claimed,
        total_approved=total_approved,
        total_deducted=total_deducted,
        deductions=deductions,
        missing_info=missing_info,
        policy_status=policy_status.status,
        waiting_period_clear=True,
        reasoning_trace="\n".join(reasoning_steps),
        escalation_triggers=escalation_triggers,
    )
