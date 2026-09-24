"""
schemas/__init__.py
-------------------
Public surface of the shared intake-schema package.

All three pipeline tracks (extraction/retrieval, rules-engine, escalation/audit)
import from this single entry-point so that renaming an internal module never
breaks downstream consumers.

Usage
-----
    from schemas import PreAuthRequest, RequestStatus, AdmissionType
    from schemas.pre_auth_request import CostLineItem   # fine too

Architecture & Pipeline Role
----------------------------
This module serves as the authoritative public interface and semantic contract
for all data exchange across the cashless health insurance pre-authorisation pipeline:

1. Extraction & Ingestion Track (Track 1):
   Converts semi-structured or unstructured inbound clinical artifacts (OCR scans,
   digital PDFs, hospital portal forms, FHIR/NHCX JSON payloads) into validated,
   strongly-typed Pydantic intake schemas.

2. Rules Engine & Adjudication Track (Track 2):
   Consumes the validated intake models to enforce deterministic business logic,
   IRDAI regulatory compliance, waiting period calculations, disease sub-limits,
   network hospital tariff ceilings, and co-payment obligations.

3. Escalation, Audit & Human Review Track (Track 3):
   Tracks workflow transitions (e.g., PENDING -> QUERIED -> AUTHORISED/DENIED),
   maintains non-repudiation audit trails, and formats human-in-the-loop review
   screens for medical adjudicators.

Why Re-exporting via __all__ is Crucial:
- Decouples downstream consumers from internal module file organization.
- Explicitly seals the public namespace, hiding internal helpers and type aliases
  (such as `_INR`) while exposing only the public domain entities.
- Provides seamless auto-completion and static verification for IDEs and type
  checkers (mypy, pyright, pyrefly).
"""

# =============================================================================
# Domain Model Imports & Re-exports
# =============================================================================

# Import core domain primitives, sub-models, and root models from the canonical
# pre_auth_request module to re-export them at the top-level package namespace.
from schemas.pre_auth_request import (
    # ── Enums ──────────────────────────────────────────────────────────────
    # Insurance domain enumerations representing patient demographics, policy types,
    # hospital tiers, clinical urgency, document provenance, workflow states,
    # and IRDAI-standard billing heads.
    Gender,
    PlanType,
    NetworkTier,
    HospitalCategory,
    AdmissionType,
    SourceFormat,
    RequestStatus,
    CostCategory,
    # ── Sub-models ─────────────────────────────────────────────────────────
    # Validated sub-components encapsulating patient identity, policy entitlements,
    # hospital empanelment, diagnosis, procedures, and itemized billing.
    Patient,
    SubLimitMap,
    Policy,
    Hospital,
    Diagnosis,
    Procedure,
    CostLineItem,
    CostEstimate,
    # ── Root model ─────────────────────────────────────────────────────────
    # The unified pre-authorisation intake payload aggregating all sub-models
    # with cross-field consistency validation.
    PreAuthRequest,
)

# =============================================================================
# Public Surface Definition (__all__)
# =============================================================================

# Restricting __all__ guarantees that `from schemas import *` only imports
# officially supported public types, preventing unintended internal symbol leakage.
__all__ = [
    # ── Enums ──────────────────────────────────────────────────────────────
    "Gender",
    "PlanType",
    "NetworkTier",
    "HospitalCategory",
    "AdmissionType",
    "SourceFormat",
    "RequestStatus",
    "CostCategory",
    # ── Sub-models ─────────────────────────────────────────────────────────
    "Patient",
    "SubLimitMap",
    "Policy",
    "Hospital",
    "Diagnosis",
    "Procedure",
    "CostLineItem",
    "CostEstimate",
    # ── Root model ─────────────────────────────────────────────────────────
    "PreAuthRequest",
]
