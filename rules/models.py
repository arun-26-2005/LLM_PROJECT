"""
rules/models.py
---------------
Pydantic v2 data models for the rules engine and adjudication pipeline.

Defines the output contract for all rule modules: every deduction, capping,
or exclusion applied to a claim is represented as a `Deduction` object with
a mandatory clause citation (Guardrail #2: grounded output or no output).

The final output — `AdjudicationResult` — uses a RECOMMEND-prefixed enum
(Guardrail #1: recommend, never decide) to ensure no agent auto-approves.

Architecture Role:
    These models bridge the rules engine (rules/) with the orchestration
    graph (orchestration/). The `AdjudicationResult` is consumed by:
    - The LLM reasoning node (to generate a human-readable narrative)
    - The escalation router (to decide if human review is needed)
    - The audit log (to create an immutable decision record)

Usage:
    from rules.models import Deduction, AdjudicationResult, Recommendation
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ============================================================================
# Enumerations
# ============================================================================


class Recommendation(str, Enum):
    """Agent recommendation output — always a RECOMMENDATION, never a decision.

    Guardrail #1 Compliance:
        IRDAI's outsourcing framework treats claims decision-making as a core
        insurer responsibility. The agent produces recommendations only; a human
        must sign off before any real authorisation or denial is issued.
    """

    RECOMMEND_AUTHORISE = "RECOMMEND_AUTHORISE"
    RECOMMEND_QUERY = "RECOMMEND_QUERY"
    RECOMMEND_DENY = "RECOMMEND_DENY"


class DeductionCategory(str, Enum):
    """Category of a deduction or capping applied to the claim.

    Each category maps to a specific rule module in the rules engine.
    """

    POLICY_INVALID = "policy_invalid"           # Policy lapsed/expired
    WAITING_PERIOD = "waiting_period"           # Claim within waiting period
    ROOM_RENT_CAPPING = "room_rent_capping"     # Room rent exceeds policy cap
    PROPORTIONATE_DEDUCTION = "proportionate_deduction"  # Consequent proportionate reduction
    SUB_LIMIT_CAPPING = "sub_limit_capping"     # Procedure-specific sub-limit breach
    CO_PAY = "co_pay"                           # Co-payment percentage applied
    DEDUCTIBLE = "deductible"                   # Deductible for top-up/super-top-up
    NON_PAYABLE = "non_payable"                 # IRDAI non-payable item exclusion
    PERMANENT_EXCLUSION = "permanent_exclusion" # Permanent exclusion (cosmetic, etc.)
    PED_EXCLUSION = "ped_exclusion"             # Pre-existing disease exclusion


# ============================================================================
# Sub-models
# ============================================================================


class Deduction(BaseModel):
    """A single capping, deduction, or exclusion applied to the claim.

    Guardrail #2 Compliance:
        Every deduction MUST carry a non-empty `clause_citation` referencing the
        exact clause text from the retrieved policy/regulatory document. A deduction
        without a citation is a critical failure — the rules engine will refuse to
        produce it.

    Guardrail #6 Compliance:
        For IRDAI-sourced deductions, `source_document` includes the circular
        number and gazette date.

    Attributes:
        category: The type of deduction being applied.
        line_item: Which cost line item this deduction applies to, if specific.
        original_amount: Amount before this deduction.
        allowed_amount: Amount after this deduction.
        deducted_amount: The delta (original - allowed).
        clause_citation: Exact text from the retrieved clause (MANDATORY).
        source_document: Source document path with circular date if IRDAI.
        explanation: Human-readable reasoning for this deduction.
    """

    category: DeductionCategory = Field(
        ..., description="Type of deduction or capping."
    )
    line_item: Optional[str] = Field(
        default=None,
        description="Cost line item this deduction applies to (if item-specific).",
    )
    original_amount: Decimal = Field(
        ..., ge=Decimal("0"), description="Amount before deduction (INR)."
    )
    allowed_amount: Decimal = Field(
        ..., ge=Decimal("0"), description="Amount after deduction (INR)."
    )
    deducted_amount: Decimal = Field(
        ..., ge=Decimal("0"), description="Delta: original - allowed (INR)."
    )
    clause_citation: str = Field(
        ...,
        min_length=1,
        description=(
            "Exact clause text from the retrieved policy/regulatory document. "
            "MANDATORY — a deduction without a citation is a critical failure."
        ),
    )
    source_document: str = Field(
        ...,
        min_length=1,
        description=(
            "Source document path. For IRDAI documents, includes circular number "
            "and gazette date (Guardrail #6)."
        ),
    )
    explanation: str = Field(
        ...,
        min_length=1,
        description="Human-readable explanation of why this deduction was applied.",
    )


class PolicyStatusInfo(BaseModel):
    """Policy status information from the mock Policy Admin System.

    Used by the policy_validity rule module to determine if the policy
    is active and eligible for cashless benefits.
    """

    is_active: bool = Field(..., description="Whether the policy is currently active.")
    status: str = Field(
        ..., description="Policy status: 'ACTIVE', 'LAPSED', or 'EXPIRED'."
    )
    remaining_sum_insured: Decimal = Field(
        default=Decimal("0"), ge=Decimal("0"),
        description="Remaining sum insured after prior claims in this policy year.",
    )
    days_since_inception: int = Field(
        default=0, ge=0,
        description="Number of days since policy inception date.",
    )


class WaitingPeriodInfo(BaseModel):
    """Waiting period evaluation results.

    Used by the waiting_period rule module to determine if the claim
    falls within any applicable waiting period.
    """

    initial_wp_clear: bool = Field(
        default=True,
        description="Whether the 30-day initial waiting period has elapsed.",
    )
    specific_disease_wp_clear: bool = Field(
        default=True,
        description="Whether the 2-year specific disease waiting period has elapsed.",
    )
    ped_wp_clear: bool = Field(
        default=True,
        description="Whether the 4-year pre-existing disease waiting period has elapsed.",
    )
    days_elapsed: int = Field(
        default=0, ge=0,
        description="Days elapsed since policy inception.",
    )
    applicable_wp_months: int = Field(
        default=0, ge=0,
        description="Applicable waiting period in months for this diagnosis.",
    )


# ============================================================================
# Root output model
# ============================================================================


class AdjudicationResult(BaseModel):
    """Complete output of the rules engine for a single pre-auth request.

    This is the primary output consumed by the LLM reasoning node, escalation
    router, and audit log. Contains the full arithmetic trace of all deductions
    applied, the recommendation, and supporting evidence.

    Guardrail #1: recommendation is always RECOMMEND_* (never a final decision).
    Guardrail #2: every deduction has a mandatory clause citation.
    Guardrail #5: only risk-relevant features are used (no patient name/address proxies).

    Attributes:
        request_id: Links back to the original PreAuthRequest.
        recommendation: RECOMMEND_AUTHORISE / RECOMMEND_QUERY / RECOMMEND_DENY.
        confidence_score: Agent's confidence in the recommendation (0.0–1.0).
        total_claimed: Total amount claimed by the hospital.
        total_approved: Recommended approved amount after all deductions.
        total_deducted: Sum of all deductions applied.
        deductions: Itemised list of deductions with citations.
        missing_info: Fields that triggered a QUERY recommendation.
        policy_status: Policy status summary (ACTIVE / LAPSED / EXPIRED).
        waiting_period_clear: Whether all applicable waiting periods are clear.
        reasoning_trace: Step-by-step reasoning narrative for audit trail.
        escalation_triggers: Reasons this case should be escalated to a human.
    """

    request_id: UUID = Field(..., description="Original PreAuthRequest ID.")
    recommendation: Recommendation = Field(
        ..., description="Agent recommendation (RECOMMEND_AUTHORISE / QUERY / DENY)."
    )
    confidence_score: float = Field(
        default=1.0, ge=0.0, le=1.0,
        description="Agent confidence in the recommendation."
    )
    total_claimed: Decimal = Field(
        ..., ge=Decimal("0"), description="Total hospital-claimed amount (INR)."
    )
    total_approved: Decimal = Field(
        ..., ge=Decimal("0"), description="Recommended approved amount (INR)."
    )
    total_deducted: Decimal = Field(
        default=Decimal("0"), ge=Decimal("0"),
        description="Sum of all deductions (INR)."
    )
    deductions: list[Deduction] = Field(
        default_factory=list,
        description="Itemised deductions with clause citations.",
    )
    missing_info: list[str] = Field(
        default_factory=list,
        description="Missing information that triggered a QUERY recommendation.",
    )
    policy_status: str = Field(
        default="ACTIVE",
        description="Policy status: ACTIVE / LAPSED / EXPIRED.",
    )
    waiting_period_clear: bool = Field(
        default=True,
        description="Whether all applicable waiting periods have elapsed.",
    )
    reasoning_trace: str = Field(
        default="",
        description="Step-by-step reasoning narrative for audit trail.",
    )
    escalation_triggers: list[str] = Field(
        default_factory=list,
        description=(
            "Reasons for escalation to human review (Guardrail #7). "
            "E.g., 'Low confidence (0.45)', 'High claim value (₹8,50,000)', "
            "'PED-flagged diagnosis'."
        ),
    )
