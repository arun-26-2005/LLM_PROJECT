"""
intake/structured_extractor.py
------------------------------
Shared structured extraction engine for all non-JSON intake formats
(Digital PDF, Scanned PDF / Image OCR, DOCX, Plain Text).

Converts raw extracted text into a validated PreAuthRequest object,
tracking explicit vs inferred fields, missing required fields, and
producing comprehensive failure reports when extraction falls short.
"""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

# pyrefly: ignore [missing-import]
from schemas import (
    AdmissionType,
    CostCategory,
    CostEstimate,
    CostLineItem,
    Diagnosis,
    Gender,
    Hospital,
    HospitalCategory,
    NetworkTier,
    Patient,
    PlanType,
    Policy,
    PreAuthRequest,
    Procedure,
    RequestStatus,
    SourceFormat,
    SubLimitMap,
)

from intake.models import IntakeResult
from intake.narrative_generator import generate_narrative_summary
from intake.query_generator import (
    generate_clarification_questions,
    generate_query_notice,
)


# ============================================================================
# HELPER FUNCTIONS: FIELD-LEVEL REGEX EXTRACTION & PARSING
# ============================================================================

def extract_key_value(pattern: str, text: str, default: Optional[str] = None) -> tuple[Optional[str], bool]:
    """Search for a regex pattern in text and extract capturing group 1.

    This helper provides deterministic pattern matching for key-value pairs
    found in semi-structured clinical documents and forms. Crucially, it tracks
    the provenance of the extracted data: whether the value was explicitly present
    in the document or inferred via a fallback default.

    Tracking the `was_inferred` flag is essential for insurance claims compliance,
    confidence scoring, and automated query generation, ensuring auditability
    when downstream decisions rely on inferred or substituted data.

    Args:
        pattern: Regular expression containing at least one capturing group
            for the target value. Case-insensitivity is applied automatically.
        text: Raw document text to search within.
        default: Fallback string value to return if the pattern is not found.
            Defaults to None.

    Returns:
        tuple[Optional[str], bool]: A two-element tuple consisting of:
            - Extracted string value (or default if not found).
            - Boolean flag indicating whether the value was inferred (True if
              default was used, False if explicitly extracted from the text).

    Example:
        >>> text = "Patient Name: Jane Doe\\nAge: 32"
        >>> extract_key_value(r"Patient Name:\\s*([A-Za-z\\s]+)", text)
        ('Jane Doe', False)
        >>> extract_key_value(r"Gender:\\s*([A-Za-z]+)", text, default="female")
        ('female', True)
    """
    # IGNORECASE accounts for erratic capitalization across OCR, forms, and clinical notes
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        # Isolate capturing group 1 and strip whitespace/stray OCR tokens
        val = match.group(1).strip()
        # Return explicit extraction flag (was_inferred = False)
        return val, False
    # Value absent in source document: substitute default and flag as inferred (was_inferred = True)
    return default, True


def parse_cost_line_items(text: str) -> list[CostLineItem]:
    """Parses line item charges from free text or OCR billing tables.

    Extracts individual billing line items by scanning line-by-line for
    item-amount pairs. It applies regex pattern matching, skips non-itemized
    summary headers or aggregate totals to prevent double-counting, quantizes
    amounts to standard currency cents (Decimal 0.01), and maps line descriptions
    to standardized insurance cost categories via keyword heuristics.

    Pattern Matching Rationale:
        Matches lines formatted as "<Item Description> <Delimiter> <Currency> <Amount>".
        - Description pattern `([A-Za-z\\s\\-/]+)`: Captures multi-word item labels,
          allowing hyphens and slashes common in medical billing (e.g. "Pre-Op / Post-Op").
        - Delimiter `[:\\s\\.\\-]+`: Tolerates colons, dashes, spaces, and dot leaders
          frequently emitted by OCR tabular reconstruction.
        - Currency `\\$?₹?\\s*`: Matches optional rupee or dollar signs with variable whitespace.
        - Amount `([\\d,]+\\.?\\d*)`: Captures numbers with comma thousand-separators and
          optional decimal fractional parts.

    Categorization Heuristic:
        Maps service descriptions to standardized `CostCategory` enum members
        (e.g., room rent, ICU, surgeon fees, pharmacy, diagnostic lab). Unmatched items
        default to `CostCategory.OTHER` to preserve all financial claims while maintaining
        strict category sub-limit adjudication.

    Args:
        text: Free-text document string containing billing or estimate sections.

    Returns:
        list[CostLineItem]: List of parsed and categorized CostLineItem objects.
            Empty list if no valid line items are detected.

    Example:
        >>> text = "Room Rent: ₹ 15,000.00\\nSurgeon Fee: 25000.00\\nTotal: 40000.00"
        >>> items = parse_cost_line_items(text)
        >>> len(items)
        2
        >>> items[0].category
        <CostCategory.ROOM_RENT: 'room_rent'>
    """
    line_items: list[CostLineItem] = []
    
    # Process text line by line to isolate discrete billing table entries
    lines = text.splitlines()
    for line in lines:
        line_clean = line.strip()
        # Discard empty lines or whitespace padding
        if not line_clean:
            continue
            
        # Match lines like "Room Rent: 25000.00" or "Estimated Surgeon Fee ... ₹ 45,000.00"
        # Captures: Group 1 = Service label, Group 2 = Amount digits (with optional commas/decimals)
        m = re.search(r"([A-Za-z\s\-/]+)[:\s\.\-]+\$?₹?\s*([\d,]+\.?\d*)", line_clean)
        if m:
            item_name = m.group(1).strip()
            # Strip comma thousands-separators to allow direct Decimal conversion
            raw_amt = m.group(2).replace(",", "")
            
            # Skip totals or headers:
            # Aggregates like 'Grand Total', 'Sum Insured', or policy headers represent
            # policy limits or calculated rollups, NOT discrete chargeable services.
            # Including them would cause severe financial double-counting during adjudication.
            if any(k in item_name.lower() for k in ["total", "grand total", "sum insured", "policy"]):
                continue
                
            try:
                # Quantize to 2 decimal places to avoid floating-point rounding inaccuracies
                amt = Decimal(raw_amt).quantize(Decimal("0.01"))
                # Only retain non-zero positive expenditures
                if amt > 0:
                    # Categorize item using keyword heuristic to align with policy sub-limits
                    category = CostCategory.OTHER
                    item_lower = item_name.lower()
                    # Check most specific categories first, falling back to general buckets
                    if "room" in item_lower:
                        category = CostCategory.ROOM_RENT
                    elif "icu" in item_lower:
                        category = CostCategory.ICU_CHARGES
                    elif "surgeon" in item_lower:
                        category = CostCategory.SURGEON_FEE
                    elif "anaesthesia" in item_lower:
                        category = CostCategory.ANAESTHESIA_FEE
                    elif "consult" in item_lower:
                        category = CostCategory.CONSULTATION_FEE
                    elif "diag" in item_lower or "lab" in item_lower or "x-ray" in item_lower:
                        category = CostCategory.DIAGNOSTIC
                    elif "pharm" in item_lower or "drug" in item_lower or "med" in item_lower:
                        category = CostCategory.PHARMACY
                    elif "consum" in item_lower:
                        category = CostCategory.CONSUMABLES
                    elif "nurs" in item_lower:
                        category = CostCategory.NURSING
                    elif "ambul" in item_lower:
                        category = CostCategory.AMBULANCE

                    # Append validated line item
                    line_items.append(
                        CostLineItem(
                            item=item_name,
                            amount=amt,
                            category=category,
                        )
                    )
            except Exception:
                # Silently ignore unparseable or corrupted numeric strings to preserve remaining items
                continue
                
    return line_items


# ============================================================================
# MAIN EXTRACTION PIPELINE
# ============================================================================

def extract_structured_pre_auth(
    raw_text: str,
    source_format: SourceFormat,
    ocr_confidence: Optional[float] = None,
) -> IntakeResult:
    """Main structured extraction pipeline for non-JSON text inputs.

    Executes a multi-stage regex extraction, inference, reconciliation, and
    validation pipeline to transform unstructured or semi-structured document text
    (from digital PDFs, OCR scans, Word documents, or plain text) into a fully
    typed PreAuthRequest schema object.

    Pipeline Overview:
        1. Patient Details: Regex extraction with honorific-based fallbacks.
        2. Policy Details: Policy number, sum insured, and plan type inference.
        3. Hospital Details: Hospital name matching with entity type fallbacks.
        4. Diagnosis & Procedure: Clinical text, ICD-10, and PED flag detection.
        5. Financials & Cost Estimate: Cost line item extraction with mathematical
           reconciliation balancing.
        6. Date Parsing: Normalization of submission and admission dates.
        7. Domain Object Construction: Sub-model instantiations (Patient, Policy, etc.).
        8. Clarification Generation: Identification of critical missing fields
           and issuance of formal query notices.
        9. Pydantic Validation & Confidence Scoring: Schema validation and
           dynamic multi-factor confidence assessment.

    Args:
        raw_text: Extracted plain text representation of the source document.
        source_format: The input document format (PDF, DOCX, TXT, OCR).
        ocr_confidence: Optional mean optical character recognition confidence
            score (0.0 to 1.0) passed from upstream OCR processors.

    Returns:
        IntakeResult: Standardized container holding the validated PreAuthRequest,
            success flag, clinical narrative, missing/inferred field manifests,
            clarification questions, and failure diagnostic messages.
    """
    # Track fields that were inferred via fallbacks or defaults (reduces confidence score)
    inferred_fields: list[str] = []
    # Track mandatory fields that could not be detected in the document text
    missing_fields: list[str] = []
    # Collect schema validation failure descriptions
    validation_errors: list[str] = []

    # ------------------------------------------------------------------------
    # 1. Patient Details Extraction
    # ------------------------------------------------------------------------
    # Primary match: Searches for explicit label prefixes such as "Patient Name:", "Name:", or "Patient:"
    name_val, name_inf = extract_key_value(r"(?:Patient Name|Name|Patient)\s*[:\-]\s*([A-Za-z\s]+)", raw_text)
    if name_inf or not name_val:
        # Fallback regex: Look for salutations (Mr./Mrs./Ms.) or inline 'Patient:' preceding Title Case names.
        # This catches unstructured narratives or referral letters where structured form labels are omitted.
        m_name = re.search(r"(?:Mr\.|Mrs\.|Ms\.|Patient:?)\s+([A-Z][a-z]+\s+[A-Z][a-z]+)", raw_text)
        name_val = m_name.group(1) if m_name else None

    # Patient full name is a non-negotiable insurance identity requirement
    if not name_val:
        missing_fields.append("patient.full_name")
        # Assign placeholder to allow downstream parsing to continue without raising immediate type errors
        name_val = "Unknown Patient"
        inferred_fields.append("patient.full_name")

    # Patient Age: Matches digits after "Age:" label; defaults to standard actuarial median 45 if absent
    age_val_str, age_inf = extract_key_value(r"(?:Age)\s*[:\-]\s*(\d+)", raw_text, "45")
    if age_inf:
        inferred_fields.append("patient.age")
    try:
        age_val = int(age_val_str)
    except ValueError:
        # Guard against malformed OCR digits (e.g. "4S" instead of "45")
        age_val = 45

    # Patient Gender: Extracts gender text; defaults to "male" for schema compliance if omitted
    gender_str, gender_inf = extract_key_value(r"(?:Gender|Sex)\s*[:\-]\s*([A-Za-z]+)", raw_text, "male")
    if gender_inf:
        inferred_fields.append("patient.gender")
    g_lower = gender_str.lower() if gender_str else "male"
    # Normalize varied inputs ("Female", "F", "female") into Gender enum
    gender_enum = Gender.FEMALE if "female" in g_lower or "f" == g_lower else Gender.MALE

    # Policy Number: Primary search for labeled policy identifiers (alphanumeric with hyphens)
    policy_num, pol_inf = extract_key_value(r"(?:Policy\s*Number|Policy\s*#|Policy)\s*[:\-]\s*([A-Z0-9\-]+)", raw_text)
    if pol_inf or not policy_num:
        # Fallback regex: Scans for standard corporate policy pattern (e.g., "POL-123456")
        m_pol = re.search(r"(POL-\d+)", raw_text)
        policy_num = m_pol.group(1) if m_pol else None

    # Policy number is mandatory for insurer eligibility verification
    if not policy_num:
        missing_fields.append("policy.policy_number")
        policy_num = "POL-MISSING"
        inferred_fields.append("policy.policy_number")

    # ------------------------------------------------------------------------
    # 2. Policy Details Extraction
    # ------------------------------------------------------------------------
    # Sum Insured: Captures total policy coverage limit; defaults to benchmark ₹500,000.00
    # (standard median health insurance coverage in India) when not declared
    sum_ins_str, sum_inf = extract_key_value(r"(?:Sum\s*Insured|Coverage)\s*[:\-]\s*₹?\s*([\d,]+)", raw_text, "500000")
    if sum_inf:
        inferred_fields.append("policy.sum_insured")
    try:
        sum_insured_amt = Decimal(sum_ins_str.replace(",", ""))
    except Exception:
        # Safeguard Decimal conversion against OCR noise
        sum_insured_amt = Decimal("500000.00")

    # Plan Type: Differentiates Individual vs Family Floater plans; defaults to Individual
    plan_str, plan_inf = extract_key_value(r"(?:Plan\s*Type|Plan)\s*[:\-]\s*([A-Za-z_]+)", raw_text, "individual")
    if plan_inf:
        inferred_fields.append("policy.plan_type")
    # Substring detection captures "Family Floater", "floater", or "FLOATER"
    plan_enum = PlanType.FAMILY_FLOATER if "floater" in plan_str.lower() else PlanType.INDIVIDUAL

    # Policy Start Date: Inception date is required for calculating waiting periods (e.g. 24/48-month PED clauses)
    # Defaults to standard calendar epoch "2025-01-01" if missing from intake document
    start_date_str, start_inf = extract_key_value(r"(?:Policy\s*Start|Inception)\s*[:\-]\s*([\d\-\/]+)", raw_text, "2025-01-01")
    if start_inf:
        inferred_fields.append("policy.policy_start_date")
    try:
        # Normalize slash separators (YYYY/MM/DD) to ISO dash format (YYYY-MM-DD)
        policy_start_dt = date.fromisoformat(start_date_str.replace("/", "-"))
    except Exception:
        policy_start_dt = date(2025, 1, 1)

    # Co-pay Percentage: Captures patient cost-sharing obligation; defaults to 0% (standard full coverage)
    copay_str, copay_inf = extract_key_value(r"(?:Co-?pay)\s*[:\-]\s*([\d\.]+)", raw_text, "0.00")
    if copay_inf:
        inferred_fields.append("policy.co_pay_pct")
    try:
        copay_pct = Decimal(copay_str)
    except Exception:
        copay_pct = Decimal("0.00")

    # ------------------------------------------------------------------------
    # 3. Hospital Details Extraction
    # ------------------------------------------------------------------------
    # Primary match: Searches for labeled hospital name key-value pairs
    hosp_name, hosp_inf = extract_key_value(r"(?:Hospital\s*Name|Hospital)\s*[:\-]\s*([A-Za-z0-9\s,\.\-]+)", raw_text)
    if hosp_inf or not hosp_name:
        # Fallback regex: Documents like admission notes or letterheads often omit the "Hospital:" label
        # but contain recognized healthcare facility noun phrases ("Hospital", "Medical Center", "Clinic").
        m_hosp = re.search(r"([A-Z][a-z]+\s+(?:Hospital|Medical Center|Clinic))", raw_text)
        hosp_name = m_hosp.group(1) if m_hosp else "City Care Hospital"
        # If neither label nor healthcare facility pattern matched, record as missing and inferred
        if not m_hosp:
            inferred_fields.append("hospital.name")
            missing_fields.append("hospital.name")

    # Hospital City: Needed for tariff zone categorization (Tier 1 vs Tier 2 cities); defaults to "Mumbai"
    city_val, city_inf = extract_key_value(r"(?:City|Location)\s*[:\-]\s*([A-Za-z\s]+)", raw_text, "Mumbai")
    if city_inf:
        inferred_fields.append("hospital.city")

    # Network Tier: Checks for cashless network agreement; defaults to CASHLESS_NETWORK because
    # pre-authorisation requests are predominantly submitted by empanelled network hospitals
    tier_str, tier_inf = extract_key_value(r"(?:Network\s*Tier|Network)\s*[:\-]\s*([A-Za-z_]+)", raw_text, "cashless_network")
    if tier_inf:
        inferred_fields.append("hospital.network_tier")
    # Substring detection captures "non-network", "non network", or "non_network"
    tier_enum = NetworkTier.NON_NETWORK if "non" in tier_str.lower() else NetworkTier.CASHLESS_NETWORK

    # ------------------------------------------------------------------------
    # 4. Diagnosis & Procedure Extraction
    # ------------------------------------------------------------------------
    # ICD-10 Code: Standard international disease code (e.g., "K35.80", "I25.10")
    icd10_code, icd_inf = extract_key_value(r"(?:ICD-?10\s*Code|ICD-?10|ICD)\s*[:\-]\s*([A-Z0-9\.]+)", raw_text)
    # Diagnosis Description: Clinical condition narrative
    diag_desc, diag_inf = extract_key_value(r"(?:Diagnosis|Condition)\s*[:\-]\s*([A-Za-z0-9\s,\(\)\-]+)", raw_text)
    if diag_inf or not diag_desc:
        diag_desc = "General Clinical Condition"
        missing_fields.append("diagnosis.description")
        inferred_fields.append("diagnosis.description")

    # Pre-Existing Disease (PED) Detection:
    # Uses case-insensitive regex to scan for explicit declarations of prior chronic illness
    # (e.g. "pre-existing", "preexisting condition", "PED: Yes"). This flag directly impacts
    # underwriting exclusion checks and statutory waiting period verification.
    is_ped = bool(re.search(r"(pre-?existing|PED\s*[:\-]?\s*yes)", raw_text, re.IGNORECASE))

    # Procedure Code (CPT/Internal) & Description
    proc_code, proc_code_inf = extract_key_value(r"(?:Procedure\s*Code|CPT)\s*[:\-]\s*([A-Z0-9\-]+)", raw_text)
    proc_desc, proc_inf = extract_key_value(r"(?:Procedure|Treatment)\s*[:\-]\s*([A-Za-z0-9\s,\(\)\-]+)", raw_text)
    if proc_inf or not proc_desc:
        proc_desc = "Surgical / Medical Procedure"
        missing_fields.append("procedure.description")
        inferred_fields.append("procedure.description")

    # Admission Type: Classifies treatment urgency; directly impacts turnaround SLA and room rent eligibility
    # Defaults to PLANNED (elective surgery/treatment)
    adm_type_str, adm_inf = extract_key_value(r"(?:Admission\s*Type)\s*[:\-]\s*([A-Za-z_]+)", raw_text, "planned")
    if adm_inf:
        inferred_fields.append("procedure.admission_type")
    adm_type_lower = adm_type_str.lower() if adm_type_str else "planned"
    if "emergency" in adm_type_lower:
        adm_enum = AdmissionType.EMERGENCY
    elif "day" in adm_type_lower:
        adm_enum = AdmissionType.DAY_CARE
    elif "maternity" in adm_type_lower:
        adm_enum = AdmissionType.MATERNITY
    else:
        adm_enum = AdmissionType.PLANNED

    # ------------------------------------------------------------------------
    # 5. Financials / Cost Estimate & Mathematical Reconciliation
    # ------------------------------------------------------------------------
    # Extract explicitly stated grand total cost from document
    total_cost_str, total_cost_inf = extract_key_value(
        r"(?:Total\s*Estimated\s*Cost|Total\s*Amount|Grand\s*Total|Total)\s*[:\-]\s*₹?\s*([\d,]+\.?\d*)", raw_text
    )
    # Parse individual line items from billing tables or itemized free text
    line_items = parse_cost_line_items(raw_text)

    # Establish declared total amount
    if total_cost_str:
        try:
            declared_total = Decimal(total_cost_str.replace(",", "")).quantize(Decimal("0.01"))
        except Exception:
            declared_total = Decimal("0.00")
    else:
        # When no explicit grand total label exists, compute total as sum of parsed line items
        declared_total = sum(i.amount for i in line_items) if line_items else Decimal("0.00")
        total_cost_inf = True
        inferred_fields.append("cost_estimate.total_amount")

    # Fallback when line items are missing but a grand total was declared:
    # Insurers require itemized billing; create a single synthetic lump-sum line item
    # to fulfill the non-empty list schema requirement while flagging missing detail.
    if not line_items:
        missing_fields.append("cost_estimate.line_items")
        if declared_total > 0:
            line_items.append(
                CostLineItem(
                    item="Estimated Medical Charges",
                    amount=declared_total,
                    category=CostCategory.OTHER,
                )
            )
            inferred_fields.append("cost_estimate.line_items")

    # Financial Reconciliation Logic:
    # In raw OCR documents and medical estimates, the sum of line items frequently fails
    # to reconcile with the declared grand total due to unlisted administrative taxes,
    # rounding, or OCR line omissions. Schema invariants require sum(items) == total.
    computed_sum = sum(i.amount for i in line_items)
    if declared_total == Decimal("0.00") and computed_sum > Decimal("0.00"):
        # Case A: Declared total was missing or zero, but line items exist -> use line item sum
        declared_total = computed_sum
    elif abs(computed_sum - declared_total) > Decimal("1.00") and computed_sum > 0:
        # Case B: Discrepancy > ₹1.00 between declared total and line items sum.
        # Inject an adjustment line item for the exact difference to guarantee mathematical
        # reconciliation and prevent schema validation failures, while flagging inference for audit.
        diff = declared_total - computed_sum
        line_items.append(
            CostLineItem(
                item="Miscellaneous Adjustment Charges",
                amount=diff,
                category=CostCategory.OTHER,
            )
        )
        inferred_fields.append("cost_estimate.line_items_reconciled")

    # ------------------------------------------------------------------------
    # 6. Date Parsing & Normalization
    # ------------------------------------------------------------------------
    # Submission Date: Captures the date the pre-auth request was drafted/sent.
    # Defaults to today's date if omitted from document.
    sub_date_str, sub_inf = extract_key_value(r"(?:Submission\s*Date|Submitted)\s*[:\-]\s*([\d\-\/]+)", raw_text, date.today().isoformat())
    try:
        # Normalizes slash notation (e.g. 2025/03/15) to ISO-8601 (2025-03-15)
        sub_date = date.fromisoformat(sub_date_str.replace("/", "-"))
    except Exception:
        sub_date = date.today()

    # Admission Date: Captures planned or actual hospital admission date.
    # Remains None if not specified, as admission date is optional prior to actual hospital entry.
    adm_date_str, adm_inf_d = extract_key_value(r"(?:Admission\s*Date|Admitted)\s*[:\-]\s*([\d\-\/]+)", raw_text)
    try:
        adm_date = date.fromisoformat(adm_date_str.replace("/", "-")) if adm_date_str else None
    except Exception:
        adm_date = None

    # ------------------------------------------------------------------------
    # 7. Sub-Object Construction
    # ------------------------------------------------------------------------
    # Instantiate domain sub-models using extracted, normalized, and inferred fields.
    patient_obj = Patient(
        full_name=name_val,
        age=age_val,
        gender=gender_enum,
        policy_number=policy_num,
    )

    policy_obj = Policy(
        policy_number=policy_num,
        plan_type=plan_enum,
        sum_insured=sum_insured_amt,
        policy_start_date=policy_start_dt,
        co_pay_pct=copay_pct,
    )

    hospital_obj = Hospital(
        name=hosp_name,
        city=city_val,
        network_tier=tier_enum,
        category=HospitalCategory.MULTI_SPECIALTY,
    )

    diag_obj = Diagnosis(
        icd10_code=icd10_code,
        description=diag_desc,
        is_pre_existing=is_ped,
    )

    proc_obj = Procedure(
        procedure_code=proc_code,
        description=proc_desc,
        admission_type=adm_enum,
    )

    cost_obj = CostEstimate(
        line_items=line_items if line_items else [
            CostLineItem(item="Estimated Cost", amount=Decimal("10000.00"), category=CostCategory.OTHER)
        ],
        total_amount=declared_total if declared_total > 0 else Decimal("10000.00"),
    )

    # ------------------------------------------------------------------------
    # 8. Clarification Generation & Critical Field Check
    # ------------------------------------------------------------------------
    # Generate proactive clarification questions for missing or inferred fields
    questions = generate_clarification_questions(missing_fields, inferred_fields)
    # Draft formal query notice if any fields required fallback inference or were absent
    query_notice = (
        generate_query_notice(
            request_id=str(uuid.uuid4()),
            hospital_name=hosp_name,
            patient_name=name_val,
            missing_fields=missing_fields,
            inferred_fields=inferred_fields,
        )
        if (missing_fields or inferred_fields)
        else None
    )

    if missing_fields:
        # Critical Field Gate:
        # Under insurance claims processing guidelines, an adjudication workflow cannot proceed
        # if any of the three foundational identity/clinical pillars are missing:
        #   1. Patient Full Name (who is being treated)
        #   2. Policy Number (who is providing coverage)
        #   3. Diagnosis Description (what medical condition necessitates care)
        # If any of these are missing, halt processing immediately and return a failure result
        # with low confidence (0.2) and pending query notices for the hospital/TPA.
        if any(f in missing_fields for f in ["patient.full_name", "policy.policy_number", "diagnosis.description"]):
            return IntakeResult(
                request=None,
                is_success=False,
                source_format=source_format,
                summary=f"Intake extraction failed due to missing required fields: {', '.join(missing_fields)}",
                confidence_score=0.2,
                ocr_confidence=ocr_confidence,
                inferred_fields=inferred_fields,
                missing_fields=missing_fields,
                validation_errors=["Extraction incomplete: required fields could not be extracted from document."],
                clarification_questions=questions,
                pending_query_notice=query_notice,
                raw_text_snippet=raw_text[:300],
            )

    # ------------------------------------------------------------------------
    # 9. Pydantic Validation Attempt & Dynamic Confidence Scoring
    # ------------------------------------------------------------------------
    try:
        # Validate composite PreAuthRequest against all Pydantic field and model validators
        pre_auth_req = PreAuthRequest(
            submitted_at=sub_date,
            source_format=source_format,
            status=RequestStatus.PENDING,
            admission_date=adm_date,
            patient=patient_obj,
            policy=policy_obj,
            hospital=hospital_obj,
            diagnosis=diag_obj,
            procedure=proc_obj,
            cost_estimate=cost_obj,
        )

        # Dynamic Confidence Scoring Rationale:
        # Starts with a base confidence of 0.95 for direct regex extraction.
        # Deducts 0.08 per inferred field (capped at 0.45 penalty) because inferred
        # fields represent synthetic defaults rather than confirmed source data.
        base_confidence = 0.95
        if inferred_fields:
            base_confidence -= min(len(inferred_fields) * 0.08, 0.45)
        # Bound confidence by OCR quality: structured data cannot be more accurate
        # than the underlying optical character recognition engine that parsed the image.
        if ocr_confidence is not None:
            base_confidence = min(base_confidence, ocr_confidence)

        # Generate human-readable narrative clinical-administrative summary
        narrative = generate_narrative_summary(pre_auth_req)

        return IntakeResult(
            request=pre_auth_req,
            is_success=True,
            source_format=source_format,
            summary=narrative,
            confidence_score=round(max(base_confidence, 0.1), 2),
            ocr_confidence=ocr_confidence,
            inferred_fields=inferred_fields,
            missing_fields=missing_fields,
            validation_errors=[],
            clarification_questions=questions,
            pending_query_notice=query_notice,
            raw_text_snippet=raw_text[:300],
        )

    except Exception as exc:
        # Handle Pydantic schema validation failures (e.g. invalid dates, negative amounts)
        err_msg = str(exc)
        validation_errors.append(err_msg)
        return IntakeResult(
            request=None,
            is_success=False,
            source_format=source_format,
            summary=f"Extraction failed schema validation: {err_msg}",
            confidence_score=0.0,
            ocr_confidence=ocr_confidence,
            inferred_fields=inferred_fields,
            missing_fields=missing_fields,
            validation_errors=validation_errors,
            clarification_questions=questions,
            pending_query_notice=query_notice,
            raw_text_snippet=raw_text[:300],
        )
