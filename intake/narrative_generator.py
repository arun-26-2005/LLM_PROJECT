"""
intake/narrative_generator.py
-----------------------------
Generates human-readable narrative summaries strictly derived from a
validated PreAuthRequest model instance.

This prevents narrative drift by ensuring the summary is computed directly
from structured fields (patient, hospital, diagnosis, procedure, costs, policy).

Why Narrative is Generated from Structured Fields (Preventing Drift):
---------------------------------------------------------------------
In health insurance pre-authorisation pipelines, clinical narratives generated
directly from raw OCR, unconstrained LLM outputs, or unstructured physician notes
frequently suffer from "narrative drift" — subtle hallucinations, mismatched sums,
or altered clinical terminology that diverge from the canonical claim record.
By synthesizing the summary strictly from the validated Pydantic model (`PreAuthRequest`),
this module guarantees:
1. Deterministic Consistency: The human-readable narrative matches the database
   and rules-engine payload byte-for-byte in amounts, codes, and names.
2. Regulatory Auditability: IRDAI and TPA compliance reviews require an immutable
   audit trail where human reviewers and automated adjudicators evaluate the exact
   same underlying structured entities.
3. Decoupled Presentation: Schema migrations and validation rules remain isolated
   from the textual presentation layer.
"""

from __future__ import annotations

# pyrefly: ignore [missing-import]
from schemas import PreAuthRequest


# =============================================================================
# Narrative Assembly Engine
# =============================================================================

def generate_narrative_summary(request: PreAuthRequest) -> str:
    """
    Constructs a clear, human-readable summary narrative from a validated
    PreAuthRequest schema instance.

    Assembles structured sub-models across patient demographics, clinical
    diagnoses, planned procedures, and financial estimates into a cohesive
    multi-paragraph text summary suitable for TPA adjudicators and audit logs.

    Args:
        request (PreAuthRequest): A fully validated pre-authorisation request
            containing patient, policy, hospital, diagnosis, procedure, and cost
            sub-models.

    Returns:
        str: A formatted, multi-line narrative string representing the complete
            case overview with all key clinical and financial parameters.

    Example:
        >>> summary = generate_narrative_summary(validated_preauth_req)
        >>> print(summary.splitlines()[0])
        Pre-authorisation request (REQ-1001) received on 2026-09-24 via PDF intake.
    """
    # -------------------------------------------------------------------------
    # 1. Sub-Model Extraction
    # -------------------------------------------------------------------------
    # Unpack sub-models upfront to decouple string interpolation from deep
    # object attribute traversal, enhancing readability and execution speed.
    patient = request.patient
    policy = request.policy
    hospital = request.hospital
    diag = request.diagnosis
    proc = request.procedure
    cost = request.cost_estimate

    # -------------------------------------------------------------------------
    # 2. Section: Patient Demographics & Policy Overview
    # -------------------------------------------------------------------------
    # Establishes provenance, identity, and coverage ceiling.
    # Turnaround time (TAT) tracking under IRDAI guidelines begins at submitted_at.
    lines = [
        # Intake metadata: provides immediate audit trail context on channel and timing
        f"Pre-authorisation request ({request.request_id}) received on {request.submitted_at} "
        f"via {request.source_format.value.upper()} intake.",
        # Patient & policy basics: title-cased plan type and formatted currency
        # ensure standard insurance terminology for adjudicators.
        f"Patient: {patient.full_name}, {patient.age} y/o {patient.gender.value.title()} "
        f"(Policy #{policy.policy_number}, Plan: {policy.plan_type.value.replace('_', ' ').title()}, "
        f"Sum Insured: INR {policy.sum_insured:,.2f}).",
        # Provider context: network tier indicates cashless entitlement eligibility
        f"Hospital: {hospital.name} ({hospital.city}, {hospital.network_tier.value.replace('_', ' ').title()} Network).",
    ]

    # -------------------------------------------------------------------------
    # 3. Section: Clinical Details (Diagnosis & Procedure)
    # -------------------------------------------------------------------------
    # Medical necessity verification requires explicit diagnosis codification
    # and pre-existing condition (PED) flags to evaluate waiting periods.
    
    # Pre-Existing Disease (PED) flag must be highlighted because policies typically
    # enforce 24- to 48-month waiting periods before PED claims become payable.
    ped_str = " (Flagged as Pre-Existing Condition)" if diag.is_pre_existing else ""
    
    # ICD-10 code is conditionally appended; tentative emergency admissions might
    # arrive before formal diagnostic coding is finalized by the hospital desk.
    icd_str = f" [{diag.icd10_code}]" if diag.icd10_code else ""
    lines.append(f"Diagnosis: {diag.description}{icd_str}{ped_str}.")

    # Procedure description and billing code specify the planned intervention;
    # admission type (daycare vs. planned vs. emergency) dictates coverage rules.
    proc_code_str = f" [{proc.procedure_code}]" if proc.procedure_code else ""
    lines.append(
        f"Planned Procedure: {proc.description}{proc_code_str} "
        f"({proc.admission_type.value.replace('_', ' ').title()} Admission)."
    )

    # -------------------------------------------------------------------------
    # 4. Section: Financials & Cost Breakdown
    # -------------------------------------------------------------------------
    # Financial summary gives adjudicators immediate visibility into total exposure
    # relative to sum insured, while line-item count signals whether an itemized
    # tariff audit is required. Co-pay percentage determines out-of-pocket split.
    lines.append(
        f"Financials: Estimated Total INR {cost.total_amount:,.2f} across {len(cost.line_items)} line items. "
        f"Applicable Co-Pay: {policy.co_pay_pct}%."
    )

    # -------------------------------------------------------------------------
    # 5. Assembly
    # -------------------------------------------------------------------------
    # Join into a clean, newline-delimited block for presentation in downstream
    # TPA portals, CLI summaries, or formal pre-authorisation letter headers.
    return "\n".join(lines)
