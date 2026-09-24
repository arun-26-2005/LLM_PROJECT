"""
schemas/pre_auth_request.py
---------------------------
Pydantic v2 data models for the A1 Cashless Health Insurance
Pre-Authorisation (Pre-Auth) pipeline.

This module is the single source of truth for all intake schema types.
Import via the package entry-point wherever possible:

    from schemas import PreAuthRequest, RequestStatus, AdmissionType
    from schemas.pre_auth_request import CostLineItem   # also valid

Domain constraints follow Indian health-insurance conventions (IRDAI, NHA
cashless guidelines).

Pipeline Architecture & Role
----------------------------
This module defines the canonical domain entities that bind together the three
stages of the automated cashless health insurance pre-authorisation platform:

1. Intake & Extraction (Track 1):
   Normalizes heterogeneous inbound hospital data (PDF forms, scanned physical
   documents, electronic data interchange via NHCX / FHIR JSON) into strongly
   typed, validated Pydantic structures.
2. Adjudication & Rules Engine (Track 2):
   Executes deterministic rules against these models to verify policy validity,
   enforce waiting periods, check disease sub-limits, cross-reference hospital
   network tariff schedules, and compute approved cashless amounts.
3. Escalation & Audit (Track 3):
   Facilitates exception routing, medical underwriter reviews, query handling,
   and regulatory compliance reporting with immutable audit trails.

Financial & Regulatory Standards:
- Currency Precision: All financial amounts use Python `Decimal` with fixed
  two-decimal-place precision (Paise) to eliminate binary floating-point drift.
- Regulatory Alignment: Follows Insurance Regulatory and Development Authority
  of India (IRDAI) Master Guidelines on Health Insurance and National Health
  Authority (NHA) National Health Claims Exchange (NHCX) standards.
- Referential Integrity: Enforces strict cross-field validation between patient
  records, policy contracts, admission dates, and itemized billing reconciliations.
"""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Annotated, Optional

# pyrefly: ignore [missing-import]
from pydantic import (
    UUID4,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

# ===========================================================================
# Helpers & Type Aliases
# ===========================================================================

# Why Decimal instead of float?
# Standard IEEE 754 floating-point types introduce rounding inaccuracies (e.g.
# 0.1 + 0.2 != 0.3), which are unacceptable in financial accounting, statutory
# claims auditing, and reconciliation against hospital billing systems.
#
# Constraints rationale:
# 1. `ge=Decimal("0")`: Pre-authorization requests quantify prospective liabilities
#    and itemized estimates. Negative amounts (adjustments/refunds) are processed
#    only during post-discharge final claims settlement, never at pre-auth intake.
# 2. `decimal_places=2`: Enforces the standard denomination of Indian currency
#    (1 INR = 100 paise), preventing fractional paise accumulation across line items.
# 3. Leading underscore `_INR`: Scoped privately within the module to ensure external
#    callers interact with validated model fields rather than instantiating raw aliases.
_INR = Annotated[Decimal, Field(ge=Decimal("0"), decimal_places=2)]
"""Non-negative Indian Rupee amount, two decimal places."""


# ===========================================================================
# Enumerations
# ===========================================================================


class Gender(str, Enum):
    """Insured member gender as declared on the health insurance policy schedule.

    Domain Role:
        In health insurance underwriting and claims adjudication, member gender
        serves three vital functions:
        1. Demographic identity verification against national identity databases
           (Aadhaar/PAN) and hospital admission registers.
        2. Actuarial risk assessment and policy underwriting classification.
        3. Clinical appropriateness validation (e.g. verifying maternity or
           gynecology coverage eligibility, or sex-specific surgical interventions).
    """

    MALE = "male"  # Standard male biological / legal sex classification
    FEMALE = "female"  # Standard female classification; prerequisite for maternity benefits
    OTHER = "other"  # Transgender / non-binary gender as mandated by IRDAI inclusion norms
    PREFER_NOT_TO_SAY = "prefer_not_to_say"  # Intake fallback when gender is unstated on initial emergency triage


class PlanType(str, Enum):
    """Underwriting architecture and risk-pooling model of the health insurance contract.

    Domain Role:
        Dictates how the policy's sum insured is consumed and what eligibility rules apply:
        - Individual policies allocate dedicated financial limits to a single life.
        - Floater policies pool coverage across all family members, where one member's
          claim diminishes the remaining pool for the entire family during the policy year.
        - Group policies (corporate) frequently waive standard waiting periods and
          incorporate customized disease sub-limits.
        - Top-Up and Super Top-Up plans apply threshold deductibles before activating.
    """

    INDIVIDUAL = "individual"  # Dedicated sum insured reserved exclusively for a single insured life
    FAMILY_FLOATER = "family_floater"  # Shared sum insured pool across primary policyholder and dependents
    GROUP = "group"  # Employer-sponsored / corporate plan, typically with relaxed waiting periods
    SENIOR_CITIZEN = "senior_citizen"  # Specialized plan for ages 60+, typically with mandatory co-pays
    CRITICAL_ILLNESS = "critical_illness"  # Fixed-benefit policy paying lump-sum on diagnosis of specified illnesses
    TOP_UP = "top_up"  # Indemnity coverage activating after a single claim exceeds the threshold deductible
    SUPER_TOP_UP = "super_top_up"  # Aggregate coverage activating when cumulative annual claims exceed the deductible


class NetworkTier(str, Enum):
    """Empanelment tier of the treating hospital."""

    # Domain Role:
    # Captures the contractual empanelment agreement between the insurer / TPA
    # network and the treating hospital. Governs:
    # 1. Cashless eligibility: Non-network facilities typically require out-of-pocket
    #    payment followed by reimbursement, unless emergency pre-auth exception is granted.
    # 2. Tariff structures: Network tiers map directly to agreed schedule of rates
    #    (GIPSA/PPM tariffs), dictating maximum allowable room rent and procedural package rates.

    CASHLESS_NETWORK = "cashless_network"  # Fully empanelled provider with active bilateral cashless SLA
    TIER_1 = "tier_1"  # Metro / large city, highest tariff schedule (quaternary care facilities)
    TIER_2 = "tier_2"  # Mid-sized cities with intermediate agreed tariff schedules
    TIER_3 = "tier_3"  # Small towns / rural facilities with base tariff schedules
    NON_NETWORK = "non_network"  # Unempanelled provider; cashless requires exceptional approval


class HospitalCategory(str, Enum):
    """Institutional classification and clinical capability of the healthcare facility.

    Domain Role:
        Under IRDAI Section 2(k) guidelines, an institution must satisfy minimum
        infrastructure thresholds (e.g., minimum inpatient beds, round-the-clock
        medical officers, fully equipped operation theater) to qualify as a covered
        hospital. Facility category determines:
        1. Eligibility for specialized surgical procedures (e.g., tertiary cardiac
           surgery requires a multi-specialty hospital with an ICU).
        2. Day-care procedure validity versus full 24-hour hospitalization mandates.
        3. Tariff ceilings and institutional quality discounts.
    """

    MULTI_SPECIALTY = "multi_specialty"  # Comprehensive facility with diverse clinical specialties and intensive care
    SINGLE_SPECIALTY = "single_specialty"  # Dedicated specialty center (e.g. eye care, oncology, orthopedics)
    DAY_CARE_CENTER = "day_care_center"  # Specialized clinic licensed for modern same-day surgical procedures (<24 hrs)
    GOVERNMENT = "government"  # Public sector civil hospital, municipal facility, or medical college
    PRIVATE = "private"  # Commercial private hospital, nursing home, or corporate healthcare chain
    TRUST = "trust"  # Charitable trust, missionary, or non-profit healthcare institution


class AdmissionType(str, Enum):
    """Clinical urgency and operational pathway of hospital admission.

    Domain Role:
        Determines the regulatory turnaround time (SLA) required under IRDAI guidelines
        and dictates evidentiary documentation requirements:
        - Emergency admissions require expedited pre-authorization decisions (typically
          under 1 to 2 hours) to avoid delaying critical patient care.
        - Planned admissions require advance notification (usually 48 to 72 hours prior)
          with comprehensive pre-operative investigation reports.
        - Day-care admissions enforce same-day discharge criteria for specified technological
          procedures without requiring the standard 24-hour bed-stay minimum.
        - Maternity admissions trigger specialized policy maternity sub-limits and waiting periods.
    """

    PLANNED = "planned"  # Scheduled elective admission; pre-auth requested 48-72 hours prior
    EMERGENCY = "emergency"  # Acute unplanned hospitalization; pre-auth requested within 24-48 hours
    DAY_CARE = "day_care"  # Advanced procedure requiring < 24 hours stay (e.g., cataract, dialysis)
    MATERNITY = "maternity"  # Obstetric delivery or pregnancy complications subject to maternity waiting periods


class SourceFormat(str, Enum):
    """How the pre-auth request arrived at the system."""

    # Domain Role:
    # Tracks document provenance and data ingestion channel. Crucial for:
    # 1. Pipeline routing: Directs the payload to appropriate extraction engines
    #    (e.g., OCR with vision LLM for scanned images vs schema deserializers for JSON).
    # 2. Confidence scoring: Direct API and structured forms carry higher confidence
    #    than handwritten scanned images, influencing automated straight-through processing (STP).
    # 3. Regulatory auditability: Maintains clear chain-of-custody documentation for IRDAI audits.

    PDF = "pdf"  # Digital or scanned PDF document (e.g., standard IRDAI Annexure C pre-auth form)
    SCANNED_IMAGE = "scanned_image"  # Raster scan / photo (JPEG, PNG) requiring OCR document parsing
    JSON = "json"  # Structured JSON payload from hospital information management systems (HIMS)
    FORM = "form"  # Web portal or mobile app data-entry submission by hospital insurance desk
    EMAIL = "email"  # Inbound email attachment or unstructured clinical request
    API = "api"  # Direct machine-to-machine exchange via NHCX / HL7 FHIR integration gateways


class RequestStatus(str, Enum):
    """Lifecycle adjudication state of the cashless pre-authorization request.

    Domain Role:
        Manages the formal state machine across the intake and claims adjudication workflow:
        - PENDING: Request received and awaiting automated rules engine evaluation or underwriter pickup.
        - AUTHORISED: Initial pre-authorisation granted with a specific sanctioned amount (Guarantee of Payment).
        - QUERIED: Additional medical records, discharge summaries, or tariff clarifications requested from provider.
        - DENIED: Pre-authorisation refused under policy exclusions or non-disclosure (reimbursement may still be sought).
        - APPROVED: Final cashless claim confirmed post-discharge or following query resolution.
        - REJECTED: Upfront administrative rejection due to invalid policy, non-payment of premium, or expired member.
    """

    PENDING = "pending"  # Awaiting rules engine adjudication or medical underwriter review
    AUTHORISED = "authorised"  # Pre-auth granted with Initial Sanctioned Amount (GOP issued)
    QUERIED = "queried"  # Clarification, bills, or medical records requested from the hospital
    DENIED = "denied"  # Pre-auth denied due to policy exclusions, waiting periods, or medical necessity
    APPROVED = "approved"  # Final cashless approval confirmed post-query resolution or audit
    REJECTED = "rejected"  # Administratively invalid request (e.g. lapsed policy or unverified member)


class CostCategory(str, Enum):
    """IRDAI-standard billing heads for health insurance claims adjudication.

    Domain Role:
        Standardizes hospital charges into uniform categories defined in IRDAI
        Master Circular on Health Insurance. Enables the rules engine to apply:
        1. Room rent sub-limits: Room charges exceeding policy caps (e.g. 1% of Sum Insured)
           trigger proportionate deductions across doctor, surgeon, and operation theater fees.
        2. Non-payable deductions: Identifies non-medical supplies (gloves, PPE, admin fees)
           excluded under IRDAI Non-Payable Schedule (List I-IV).
        3. Medical capping: Checks high-cost consumables and implants against government
           price caps (NPPA ceiling rates) and policy-specific package tariffs.
    """

    ROOM_RENT = "room_rent"  # Daily bed/room accommodation charges; triggers proportionate deduction if breached
    ICU_CHARGES = "icu_charges"  # Intensive Care Unit accommodation, continuous monitoring, and life support
    SURGEON_FEE = "surgeon_fee"  # Operating surgeon professional charges
    ANAESTHESIA_FEE = "anaesthesia_fee"  # Anesthesiologist evaluation and administration fees
    CONSULTATION_FEE = "consultation_fee"  # Inpatient visits and specialist consultation charges
    DIAGNOSTIC = "diagnostic"  # Laboratory tests, pathology, radiology, CT/MRI, ultrasound scans
    PHARMACY = "pharmacy"  # Inpatient medications and IV infusions administered during hospitalization
    CONSUMABLES = "consumables"  # Surgical supplies and disposable items (scrutinized against IRDAI exclusions)
    IMPLANTS = "implants"  # Surgical prosthetics (e.g. cardiac stents, orthopedic implants, pacemakers)
    NURSING = "nursing"  # Routine inpatient nursing care and attending charges
    AMBULANCE = "ambulance"  # Emergency transit charges; capped by policy emergency transit sub-limits
    NON_PAYABLE = "non_payable"  # Items explicitly excluded by IRDAI regulations (registration, luxury items)
    OTHER = "other"  # Unclassified ancillary hospital charges requiring manual adjudicator review


# ===========================================================================
# Sub-models
# ===========================================================================


class Patient(BaseModel):
    """Demographic and identification details of the insured patient.

    Pipeline Role:
        Represents the insured member receiving treatment. Serves as the identity
        anchor connecting the hospital admission request with the core Policy
        Administration System (PAS). Downstream pipeline stages use this data to:
        - Verify active membership and dependent eligibility.
        - Evaluate age-dependent underwriting guidelines and pediatric/geriatric protocols.
        - Cross-check gender-specific clinical procedures and maternity clauses.
    """

    # Why populate_by_name and str_strip_whitespace?
    # - populate_by_name: Allows intake parsers to accept alternate field aliases from legacy systems.
    # - str_strip_whitespace: Cleans unintentional whitespace introduced during manual data entry or OCR extraction.
    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    patient_id: UUID4 = Field(
        default_factory=uuid.uuid4,
        description="Insurer-assigned patient / member identifier (UUID v4).",
    )
    full_name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Full name as it appears on the insurance policy.",
    )
    age: Annotated[int, Field(ge=0, le=120)] = Field(
        ...,
        description="Age in completed years at the time of admission.",
    )
    gender: Gender = Field(
        ...,
        description="Gender as recorded on the policy.",
    )
    policy_number: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Policy number linking this patient to the active policy.",
    )


class SubLimitMap(BaseModel):
    """Flexible per-category sub-limit caps drawn from the policy schedule.

    Pipeline Role:
        Encapsulates contract-defined sub-limits (monetary caps) for specific
        disease conditions, procedures, or treatment heads (e.g., Cataract: 40,000 INR;
        Knee Replacement: 1,50,000 INR; Maternity: 50,000 INR).
        The rules engine (Track 2) consults this map during financial adjudication
        to cap approved amounts independently of the total Sum Insured.

    Design Rationale:
        Using a dynamic dictionary rather than hardcoded fields accommodates diverse
        insurance products without requiring continuous database schema migrations.
    """

    limits: dict[str, _INR] = Field(
        default_factory=dict,
        description="Mapping of sub-limit category label to maximum payable amount (INR).",
    )


class Policy(BaseModel):
    """Policy-level entitlement data required at intake time.

    Pipeline Role:
        Represents the active insurance contract and financial coverage terms.
        Supplies essential parameters to the rules engine for:
        - Checking policy status and cumulative annual Sum Insured exhaustion.
        - Evaluating waiting period compliance (e.g., 30-day initial waiting period
          or 24-48 month pre-existing condition exclusions) against admission date.
        - Applying mandatory or voluntary co-payment percentages.
        - Applying disease-specific and treatment-specific sub-limit caps.
    """

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    policy_number: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Unique policy identifier.",
    )
    plan_type: PlanType = Field(
        ...,
        description="Structure of the policy (individual / family_floater / group).",
    )
    sum_insured: _INR = Field(
        ...,
        description="Total sum insured in INR for the current policy year.",
    )
    policy_start_date: date = Field(
        ...,
        description="Policy inception date.",
    )
    waiting_period_months: Annotated[int, Field(ge=0)] = Field(
        default=0,
        description="General waiting period in months from policy_start_date.",
    )
    sub_limits: SubLimitMap = Field(
        default_factory=SubLimitMap,
        description="Per-category coverage caps as specified in the policy schedule.",
    )
    co_pay_pct: Annotated[
        Decimal, Field(ge=Decimal("0"), le=Decimal("100"), decimal_places=2)
    ] = Field(
        default=Decimal("0.00"),
        description="Co-pay percentage borne by the insured.",
    )


class Hospital(BaseModel):
    """The hospital submitting the pre-auth request.

    Pipeline Role:
        Identifies the treating healthcare provider. The rules engine utilizes
        this model to:
        - Validate active empanelment and network tier for cashless privileges.
        - Look up negotiated tariff packages and room rent rate agreements based on city tier.
        - Ensure the facility category (e.g., multi-specialty vs day care) meets
          minimum clinical infrastructure requirements for the planned procedure.
    """

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    hospital_id: UUID4 = Field(
        default_factory=uuid.uuid4,
        description="Insurer's internal hospital empanelment ID (UUID v4).",
    )
    name: str = Field(
        ...,
        min_length=1,
        max_length=300,
        description="Legal name of the hospital / clinic.",
    )
    city: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="City where the hospital is located.",
    )
    network_tier: NetworkTier = Field(
        ...,
        description="Cashless empanelment status.",
    )
    category: HospitalCategory = Field(
        ...,
        description="Facility type.",
    )


class Diagnosis(BaseModel):
    """Primary diagnosis for the admission.

    Pipeline Role:
        Establishes the clinical pathology and medical necessity for hospitalization.
        The rules engine evaluates the diagnosis to:
        - Identify statutory IRDAI exclusions (e.g., cosmetic surgery, self-inflicted injury).
        - Match against disease-specific waiting period lists (e.g., 2-year waiting periods
          for hernia, cataract, benign prostatic hypertrophy).
        - Correlate with pre-existing condition flags to enforce PED exclusion clauses.
    """

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    icd10_code: Optional[str] = Field(
        default=None,
        description="ICD-10 code (e.g. 'H26.9' for cataract).",
    )
    description: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Free-text clinical description of the primary diagnosis.",
    )
    is_pre_existing: bool = Field(
        default=False,
        description="True if flagged as pre-existing condition.",
    )

    @field_validator("icd10_code")
    @classmethod
    def validate_icd10_format(cls, v: Optional[str]) -> Optional[str]:
        """Validates syntax and normalizes WHO ICD-10 diagnostic codes.

        Business Logic:
            - Conforms to World Health Organization (WHO) ICD-10 coding architecture:
              1 capital letter followed by 2 digits, optionally followed by a period
              and 1 to 4 alphanumeric characters (e.g., 'H26', 'H26.9', 'S72.001A').
            - Normalization: Automatically trims whitespace and capitalizes letters to
              guarantee deterministic indexing against clinical knowledge bases and
              exclusion rules.
            - Nullability: Allows None because acute emergency admissions may be
              submitted by hospital intake desks before formal medical record coding
              is completed by the attending physician.

        Args:
            v: The input ICD-10 code string or None.

        Returns:
            The uppercase, stripped ICD-10 code, or None if omitted.

        Raises:
            ValueError: If the non-null string violates the standard ICD-10 regex pattern.
        """
        if v is None:
            return v
        pattern = r"^[A-Z][0-9]{2}(\.[A-Z0-9]{1,4})?$"
        normalised = v.strip().upper()
        if not re.fullmatch(pattern, normalised):
            raise ValueError(
                f"'{v}' does not match the expected ICD-10 format "
                "(e.g. 'H26', 'H26.9', 'S72.001A')."
            )
        return normalised


class Procedure(BaseModel):
    """The primary procedure / treatment planned for the admission.

    Pipeline Role:
        Specifies the planned medical or surgical intervention. Downstream
        adjudication processes use this model to:
        - Verify clinical consistency between the planned procedure and the diagnosis.
        - Check whether the intervention qualifies for day-care treatment or requires
          standard 24-hour hospitalization.
        - Map against agreed package tariffs (e.g., GIPSA schedule of rates) for
          network hospital billing validation.
    """

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    procedure_code: Optional[str] = Field(
        default=None,
        max_length=50,
        description="Procedure code (NHCX / ICD-10-PCS / hospital-specific).",
    )
    description: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Free-text description of the planned procedure.",
    )
    admission_type: AdmissionType = Field(
        ...,
        description="Clinical context of the admission.",
    )


class CostLineItem(BaseModel):
    """A single line item from the hospital's cost estimate.

    Pipeline Role:
        Represents an atomic billable entry from the hospital's pro-forma estimate.
        Enables granular adjudication rules to execute:
        - Applying room rent sub-limits and triggering proportionate tariff deductions.
        - Disallowing non-payable items (administrative charges, disposable toiletries)
          under IRDAI Non-Payable Expense guidelines.
        - Auditing medical implant charges against NPPA statutory price ceilings.
    """

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    item: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Description of the line item as provided by the hospital.",
    )
    amount: _INR = Field(
        ...,
        description="Line-item cost in INR (non-negative, 2 decimal places).",
    )
    category: CostCategory = Field(
        ...,
        description="IRDAI-aligned cost category.",
    )


class CostEstimate(BaseModel):
    """Hospital's itemised cost estimate submitted with the pre-auth request.

    Pipeline Role:
        Aggregates and verifies the provider's financial breakdown. Ensures mathematical
        reconciliation between individual line-item charges and declared totals
        before the claim enters the financial rules adjudication pipeline.
    """

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    line_items: list[CostLineItem] = Field(
        ...,
        min_length=1,
        description="Itemised list of charges from the hospital's cost estimate.",
    )
    total_amount: _INR = Field(
        ...,
        description="Total estimated cost in INR as declared by the hospital.",
    )

    @model_validator(mode="after")
    def total_must_reconcile_with_line_items(self) -> "CostEstimate":
        """Cross-validates that the sum of line items matches the declared total.

        Cross-Field Validation Rules & Business Logic:
            - Computes the arithmetic sum of all line item amounts.
            - Compares `computed` sum against the hospital-declared `total_amount`.
            - Enforces a reconciliation tolerance threshold of +/- 1.00 INR (diff <= 1.00).

        Why allow +/- 1.00 INR tolerance?
            Hospital billing systems frequently calculate line-item taxes (GST),
            prorated bed charges, and fractional percentage discounts, which introduce
            sub-rupee rounding differences when summed. A strict zero-difference rule
            would reject valid claims due to rounding noise, whereas an error exceeding
            1 INR indicates data extraction omission, omitted charges, or calculation errors.

        Returns:
            The validated CostEstimate instance if reconciled.

        Raises:
            ValueError: If the discrepancy between computed sum and total_amount exceeds 1 INR.
        """
        # Sum all atomic line items using Decimal arithmetic to preserve exact currency precision.
        computed = sum(item.amount for item in self.line_items)
        diff = abs(computed - self.total_amount)
        # Check against statutory +/- 1 INR rounding tolerance.
        if diff > Decimal("1.00"):
            raise ValueError(
                f"total_amount ({self.total_amount} INR) differs from the "
                f"sum of line_items ({computed} INR) by {diff} INR, which "
                "exceeds the +/- 1 INR reconciliation tolerance."
            )
        return self


# ===========================================================================
# Root model — PreAuthRequest
# ===========================================================================


class PreAuthRequest(BaseModel):
    """Root intake model for a single cashless pre-authorisation request.

    Pipeline Role:
        The core unified payload representing an entire cashless pre-authorisation
        transaction. Serves as the authoritative system-to-system contract connecting:
        1. Track 1 (Extraction & Ingestion): Populates this root model from incoming
           clinical and administrative documents.
        2. Track 2 (Rules Adjudication): Validates cross-entity rules, evaluates
           policy terms, and computes approved sanction amounts.
        3. Track 3 (Escalation & Audit): Manages request state transitions (PENDING,
           QUERIED, AUTHORISED, DENIED) and logs decision traces for regulatory compliance.

    Design Rationale:
        Aggregates Patient, Policy, Hospital, Diagnosis, Procedure, and CostEstimate
        into an atomic data structure, enforcing relational consistency and temporal
        validity across all sub-entities before any business decision is made.
    """

    model_config = ConfigDict(
        populate_by_name=True,
        # Decimal serialization: Convert Decimal to string in JSON output to prevent
        # downstream consumer JSON parsers (e.g. JavaScript) from degrading precision to floats.
        json_encoders={Decimal: str},
        json_schema_extra={
            "title": "A1 Cashless Pre-Authorisation Request",
            "version": "1.0.0",
        },
    )

    request_id: UUID4 = Field(
        default_factory=uuid.uuid4,
        description="Globally unique identifier for this pre-auth request.",
    )
    submitted_at: date = Field(
        ...,
        description="Calendar date on which the hospital submitted the request.",
    )
    source_format: SourceFormat = Field(
        ...,
        description="Format in which the request arrived.",
    )
    status: RequestStatus = Field(
        default=RequestStatus.PENDING,
        description="Current lifecycle status.",
    )
    admission_date: Optional[date] = Field(
        default=None,
        description="Planned or actual date of hospital admission.",
    )

    # Composite Sub-models
    patient: Patient = Field(..., description="The insured member receiving treatment.")
    policy: Policy = Field(..., description="Policy entitlement data at submission.")
    hospital: Hospital = Field(..., description="The network (or non-network) hospital.")
    diagnosis: Diagnosis = Field(..., description="Primary diagnosis for the admission.")
    procedure: Procedure = Field(..., description="Primary procedure / treatment planned.")
    cost_estimate: CostEstimate = Field(..., description="Hospital's itemised cost estimate.")

    @model_validator(mode="after")
    def policy_number_must_be_consistent(self) -> "PreAuthRequest":
        """Cross-validates that patient's policy number matches the policy entity.

        Cross-Field Validation Rules & Business Logic:
            - Verifies referential integrity between `patient.policy_number` and
              `policy.policy_number`.

        Why this check is necessary:
            In document-intake pipelines, patient demographic data (from hospital
            admission forms) and policy contract details (from the insurer's policy
            database or uploaded policy certificate) may be extracted from separate
            pages or distinct systems. A mismatch signals that a patient record has
            been mistakenly linked to another policyholder's contract, which could cause
            unauthorized data disclosure or improper claims payout.

        Returns:
            The validated PreAuthRequest instance.

        Raises:
            ValueError: If patient.policy_number does not match policy.policy_number.
        """
        # Ensure referential integrity between demographic record and contractual entitlement.
        if self.patient.policy_number != self.policy.policy_number:
            raise ValueError(
                f"patient.policy_number ('{self.patient.policy_number}') "
                f"does not match policy.policy_number ('{self.policy.policy_number}')."
            )
        return self

    @model_validator(mode="after")
    def admission_date_not_before_policy_start(self) -> "PreAuthRequest":
        """Cross-validates that admission date is on or after the policy inception date.

        Cross-Field Validation Rules & Business Logic:
            - Evaluates temporal eligibility by comparing `admission_date` against
              `policy.policy_start_date`.

        Why this check is necessary:
            Under foundational insurance law and IRDAI regulations, an insurer assumes
            zero liability for hospitalizations that occur prior to policy inception.
            If admission occurred before the policy began, the claim is strictly
            ineligible. Catching this at intake avoids wasted clinical adjudication
            effort and immediately triggers an administrative denial or query workflow.

        Returns:
            The validated PreAuthRequest instance.

        Raises:
            ValueError: If admission_date is earlier than policy.policy_start_date.
        """
        # Verify temporal coverage eligibility: treatment cannot pre-date the policy contract.
        if (
            self.admission_date is not None
            and self.admission_date < self.policy.policy_start_date
        ):
            raise ValueError(
                f"admission_date ({self.admission_date}) is before "
                f"policy.policy_start_date ({self.policy.policy_start_date})."
            )
        return self
