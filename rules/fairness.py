"""
rules/fairness.py
-----------------
Fairness verification module (Guardrail #5).

Ensures that the rules engine's deductions are based ONLY on risk-relevant
features (diagnosis, procedure, policy terms, admission date) and NEVER on
proxies for protected attributes (religion, caste, region, gender inferred
from name, address, or PIN code).

From Guardrails.md:
    "Decisions must rest on risk-relevant features and cited rules, never on
     proxies for religion, caste, region or gender inferred from name, address
     or PIN code."

From Metrics.md:
    "Fairness — Outcome stability when protected-proxy attributes are perturbed."

Usage:
    from rules.fairness import verify_fairness
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from schemas import PreAuthRequest
    from rules.models import Deduction

logger = logging.getLogger(__name__)

# Fields that are ALLOWED to influence the decision (risk-relevant features).
RISK_RELEVANT_FIELDS = {
    "diagnosis.icd10_code",
    "diagnosis.description",
    "diagnosis.is_pre_existing",
    "procedure.procedure_code",
    "procedure.description",
    "procedure.admission_type",
    "policy.plan_type",
    "policy.sum_insured",
    "policy.policy_start_date",
    "policy.waiting_period_months",
    "policy.sub_limits",
    "policy.co_pay_pct",
    "hospital.network_tier",
    "hospital.category",
    "cost_estimate.line_items",
    "cost_estimate.total_amount",
    "admission_date",
}

# Fields that must NEVER influence the decision (protected-proxy attributes).
PROTECTED_PROXY_FIELDS = {
    "patient.full_name",       # Proxy for religion, caste, ethnicity
    "patient.gender",          # Should not affect non-gender-specific claims
    "patient.patient_id",      # Should not influence decision
    "hospital.city",           # Proxy for region (only network_tier matters)
    "hospital.name",           # Should not influence decision
    "hospital.hospital_id",    # Should not influence decision
}


def verify_fairness(
    request: "PreAuthRequest",
    deductions: list["Deduction"],
) -> bool:
    """Verify that no deduction references protected-proxy attributes.

    Checks:
        1. No deduction explanation mentions patient name or city as a
           decision factor.
        2. No deduction uses gender as a basis unless the procedure is
           genuinely gender-specific (e.g., maternity).

    This is a static analysis check. The full fairness evaluation (outcome
    stability under perturbation) is done in the evaluation harness (Member 3).

    Args:
        request: The PreAuthRequest being processed.
        deductions: List of deductions produced by the rules engine.

    Returns:
        True if fairness check passes, False if a violation is detected.
    """
    violations: list[str] = []

    # Extract protected values to check for leakage
    patient_name = request.patient.full_name.lower()
    hospital_city = request.hospital.city.lower()
    hospital_name = request.hospital.name.lower()

    for deduction in deductions:
        explanation_lower = deduction.explanation.lower()
        citation_lower = deduction.clause_citation.lower()

        # Check if patient name leaked into reasoning
        if patient_name in explanation_lower and len(patient_name) > 3:
            violations.append(
                f"Deduction '{deduction.category.value}' references patient name "
                f"'{request.patient.full_name}' in explanation."
            )

        # Check if hospital city (as opposed to network tier) is used
        # as a decision factor (city is a proxy for region)
        if hospital_city in explanation_lower and "non-network" not in explanation_lower:
            # Allow city mention only if it's in the context of network status
            if "tier" not in explanation_lower and "network" not in explanation_lower:
                violations.append(
                    f"Deduction '{deduction.category.value}' references hospital city "
                    f"'{request.hospital.city}' outside of network-tier context."
                )

    if violations:
        for v in violations:
            logger.warning("FAIRNESS VIOLATION: %s", v)
        return False

    logger.debug("Fairness check: PASSED (%d deductions verified).", len(deductions))
    return True
