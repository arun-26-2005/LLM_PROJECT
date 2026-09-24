"""
intake/query_generator.py
--------------------------
Generates formal Pre-Authorisation Information Query Notices for missing or
ambiguous details when a document lacks required information.

IRDAI & TPA Compliance Context:
-------------------------------
Under IRDAI (Insurance Regulatory and Development Authority of India) guidelines
governing cashless health insurance claims, insurers and Third-Party Administrators
(TPAs) are bound by strict Turn-Around Time (TAT) mandates (typically 1 to 3 hours).
When an incoming pre-authorisation request lacks mandatory information or contains
low-confidence extractions, the insurer cannot arbitrarily reject the request. Instead,
a formal Information Query Notice must be generated and dispatched to the network
hospital desk. This notice legally records the deficiency, freezes the statutory
adjudication clock, and establishes a transparent audit trail of requested data items.
"""

from __future__ import annotations

from typing import Sequence


# =============================================================================
# Section 1: Canonical Field Prompt Mapping Dictionary
# =============================================================================
# Purpose of FIELD_PROMPTS:
# Internal Pydantic schemas use dot-notated technical paths (e.g., 'cost_estimate.total_amount',
# 'diagnosis.icd10_code') which are intuitive to software engineers but confusing to hospital
# admission desks, billing clerks, or patients. FIELD_PROMPTS acts as a domain-specific
# translation dictionary that maps technical schema keys to clear, legally unambiguous,
# and human-understandable healthcare terminology.
FIELD_PROMPTS: dict[str, str] = {
    "patient.full_name": "Full legal name of the insured patient as per policy records",
    "patient.age": "Age of the patient in completed years",
    "patient.gender": "Gender of the patient (male / female / other)",
    "patient.policy_number": "Active policy number / Health Card ID",
    "policy.policy_number": "Policy number linked to patient entitlement",
    "policy.sum_insured": "Total annual sum insured amount in INR",
    "hospital.name": "Official empanelled name of treating hospital / nursing home",
    "hospital.city": "City/location of the hospital",
    "diagnosis.description": "Clinical description of primary diagnosis / reason for admission",
    "diagnosis.icd10_code": "ICD-10 code for the diagnosed medical condition",
    "procedure.description": "Planned surgical or medical procedure name",
    "admission_date": "Actual or planned admission date (YYYY-MM-DD)",
    "cost_estimate.line_items": "Itemised break-up of estimated hospital charges",
    "cost_estimate.total_amount": "Grand total of estimated hospitalisation cost in INR",
}


# =============================================================================
# Section 2: Interactive Clarification Questions Generator
# =============================================================================

def generate_clarification_questions(missing_fields: Sequence[str], inferred_fields: Sequence[str]) -> dict[str, str]:
    """Generates user-friendly prompt questions for missing or inferred fields.

    Constructs specific interactive prompts distinguishing between totally absent
    data and low-confidence machine inferences.

    Distinction Between Missing vs. Inferred Field Prompts:
    - Missing Fields: Represent absolute data voids where extraction failed completely
      or the original document omitted mandatory data. Prompts demand direct user input
      to satisfy schema validation rules.
    - Inferred Fields: Represent values predicted by OCR heuristics, regex patterns, or
      NLP models with marginal confidence. Instead of forcing redundant data re-entry,
      the prompt presents the hypothesized value and requests confirmation or correction,
      minimizing cognitive load for hospital operators.

    Args:
        missing_fields (Sequence[str]): Dot-notated field names identified as completely
            missing from the intake document.
        inferred_fields (Sequence[str]): Dot-notated field names extracted with low
            confidence that require human corroboration.

    Returns:
        dict[str, str]: Mapping from dot-notated field keys to actionable prompt strings
            suitable for CLI or interactive UI presentation.

    Example:
        >>> missing = ["patient.full_name"]
        >>> inferred = ["diagnosis.icd10_code"]
        >>> qs = generate_clarification_questions(missing, inferred)
        >>> print(qs["patient.full_name"])
        Please enter Full legal name of the insured patient as per policy records:
    """
    questions: dict[str, str] = {}
    
    # -------------------------------------------------------------------------
    # Process Missing Fields: Requires direct data capture
    # -------------------------------------------------------------------------
    for f in missing_fields:
        # Fall back to the technical key if an unmapped field occurs, preventing KeyErrors
        # during schema evolution or unexpected custom field additions.
        desc = FIELD_PROMPTS.get(f, f"Value for '{f}'")
        questions[f] = f"Please enter {desc}:"
        
    # -------------------------------------------------------------------------
    # Process Inferred Fields: Requires confirmation or override
    # -------------------------------------------------------------------------
    for f in inferred_fields:
        # Avoid duplicate questions if an edge case flags a field in both sequences;
        # missing mandatory requirements take precedence over inference confirmations.
        if f not in questions:
            desc = FIELD_PROMPTS.get(f, f"Value for '{f}'")
            questions[f] = f"System inferred field '{f}'. Please confirm or update {desc}:"
            
    return questions


# =============================================================================
# Section 3: Formal TPA Query Notice Generator
# =============================================================================

def generate_query_notice(
    request_id: str,
    hospital_name: str,
    patient_name: str,
    missing_fields: Sequence[str],
    inferred_fields: Sequence[str],
) -> str:
    """Generates a formal TPA / Insurer Information Request Query Notice.

    Formal Query Notice Format (IRDAI / TPA Compliance):
    ----------------------------------------------------
    In the Indian cashless healthcare ecosystem, a query notice is an official legal
    communication between the TPA and the empanelled network provider. This notice
    must adhere to a standardized format:
    1. Header & Identifiers: Clearly states Request Reference ID, Hospital Name, and
       Patient Name to ensure indisputable association with the primary claim file.
    2. Status Indication: Explicitly designates status as 'PENDING INFORMATION (QUERIED)',
       pausing the regulatory cashless TAT timer under IRDAI compliance norms.
    3. Categorized Deficiencies: Clearly segregates [MISSING MANDATORY FIELD] from
       [LOW-CONFIDENCE INFERRED FIELD] so hospital desk staff understand exactly which
       elements are hard blockers vs. verification checkpoints.
    4. Actionable Next Steps: Provides explicit resolution mechanisms (document
       re-submission or interactive digital correction) to expedite claim adjudication.

    Args:
        request_id (str): Unique pre-authorisation tracking reference identifier.
        hospital_name (str): Name of the treating empanelled hospital or nursing home.
        patient_name (str): Full legal name of the insured patient undergoing treatment.
        missing_fields (Sequence[str]): List of dot-notated fields with missing values.
        inferred_fields (Sequence[str]): List of dot-notated fields requiring validation.

    Returns:
        str: Formatted multi-line text notice formatted for direct transmission
            via email, portal notification, or EDI messaging to the hospital.

    Example:
        >>> notice = generate_query_notice(
        ...     "REQ-2026-99", "Apollo Hospital", "John Doe", ["patient.age"], []
        ... )
        >>> print(notice.splitlines()[1])
                HEALTH INSURANCE TPA PRE-AUTHORISATION QUERY NOTICE
    """
    # -------------------------------------------------------------------------
    # Formal Notice Header & Regulatory Metadata
    # -------------------------------------------------------------------------
    # Fixed delimiter width and clean header layout conform to standardized
    # TPA electronic clearinghouse formatting conventions.
    lines = [
        "=======================================================================",
        "        HEALTH INSURANCE TPA PRE-AUTHORISATION QUERY NOTICE",
        "=======================================================================",
        f"Request Reference ID : {request_id}",
        f"Treating Hospital    : {hospital_name}",
        f"Insured Patient      : {patient_name}",
        f"Query Notice Status  : PENDING INFORMATION (QUERIED)",
        "-----------------------------------------------------------------------",
        "Dear Hospital SPOC / Insured Member,",
        "",
        "During intake processing of your pre-authorisation request, the system",
        "identified that certain mandatory details are missing or ambiguous in",
        "the submitted document.",
        "",
        "REQUIRED INFORMATION / DOCUMENTS:",
    ]

    # -------------------------------------------------------------------------
    # Itemized Deficiency List
    # -------------------------------------------------------------------------
    # Use 1-indexed numbering for formal legal clarity and ease of phone/email reference.
    item_idx = 1
    
    # Missing fields are hard blockers: the claim cannot proceed without them.
    for f in missing_fields:
        desc = FIELD_PROMPTS.get(f, f"Valid value for {f}")
        lines.append(f"  {item_idx}. [MISSING MANDATORY FIELD] {f}: {desc}")
        item_idx += 1

    # Inferred fields represent ambiguous data: confirmation is required to avoid
    # inaccurate denial or post-authorization billing disputes.
    for f in inferred_fields:
        desc = FIELD_PROMPTS.get(f, f"Confirmation of {f}")
        lines.append(f"  {item_idx}. [LOW-CONFIDENCE INFERRED FIELD] {f}: {desc}")
        item_idx += 1

    # -------------------------------------------------------------------------
    # Actionable Resolution Protocols
    # -------------------------------------------------------------------------
    # Direct the hospital to authorized correction channels to resolve the query
    # and resume cashless pre-authorisation processing.
    lines.extend([
        "",
        "NEXT STEPS:",
        "  - Option A: Re-submit document with highlighted missing fields.",
        "  - Option B: Use interactive CLI clarification mode to supply missing data.",
        "-----------------------------------------------------------------------",
    ])

    return "\n".join(lines)
