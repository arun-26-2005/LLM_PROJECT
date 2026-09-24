"""
intake/models.py
----------------
Data models and wrapper types for the Multi-Format Intake Pipeline.

Defines the unified `IntakeResult` envelope that standardizes outputs across
all ingestion channels (JSON, Digital PDF, Scanned PDF/OCR, DOCX, and Plain Text),
providing downstream adjudication and auditing services with a consistent contract.
"""

from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, Field

# pyrefly: ignore [missing-import]
from schemas import PreAuthRequest, SourceFormat


# ============================================================================
# UNIFIED INTAKE RESULT MODEL
# ============================================================================

class IntakeResult(BaseModel):
    """Unified result object returned by all intake paths.

    Every input format handler (JSON, Digital PDF, Scanned PDF/OCR, DOCX, Text)
    returns an instance of this model. Standardizing on this envelope ensures
    that downstream adjudication engines, validation services, audit loggers,
    and user interfaces interact with a consistent, type-safe interface.

    Attributes:
        request: Validated PreAuthRequest domain model when extraction succeeds.
        is_success: Boolean status flag indicating extraction and validation success.
        source_format: Origin format enum indicating the document modality.
        summary: Deterministic human-readable clinical/administrative summary.
        confidence_score: Overall extraction confidence score ranging from 0.0 to 1.0.
        ocr_confidence: Character recognition confidence score for OCR-based pipelines.
        inferred_fields: List of schema fields populated via clinical heuristics/defaults.
        missing_fields: List of mandatory schema fields that could not be extracted.
        validation_errors: List of Pydantic validation errors or cross-field rule violations.
        raw_text_snippet: Excerpt of raw extracted text retained for auditability and debugging.
        clarification_questions: Pre-computed map of field names to user-facing interview prompts.
        pending_query_notice: Ready-to-send formal IRDAI/TPA deficiency query letter.
    """

    # -------------------------------------------------------------------------
    # Core Adjudication & Validation Payload
    # -------------------------------------------------------------------------
    # The primary domain model consumed by downstream automated adjudication,
    # policy coverage verification, and medical necessity rule engines.
    # If extraction fails validation, this remains None so downstream processors
    # know not to execute adjudication rules on partial or malformed data.
    request: Optional[PreAuthRequest] = Field(
        default=None,
        description="Validated PreAuthRequest model if extraction & validation succeeded.",
    )

    # Acts as the primary circuit breaker and control-flow guard for downstream
    # workflow orchestrators. Orchestrators check this boolean first to decide
    # whether to proceed with automated processing or divert to manual review.
    is_success: bool = Field(
        ...,
        description="True if a valid PreAuthRequest was successfully constructed.",
    )

    # Records the evidentiary source format for audit trails and compliance logging.
    # Downstream analytics and risk-scoring modules use this to apply format-specific
    # scrutiny (e.g., flagging OCR-derived requests for spot-check reviews).
    source_format: SourceFormat = Field(
        ...,
        description="Input format processed.",
    )

    # -------------------------------------------------------------------------
    # Narrative & Human Summarization
    # -------------------------------------------------------------------------
    # Provides a deterministic, structured narrative synthesized strictly from validated fields.
    # Downstream TPA claims adjusters, hospital portal dashboards, and notification systems
    # consume this summary for rapid human review without having to parse complex nested JSON.
    summary: str = Field(
        default="",
        description="Human-readable narrative summary generated strictly from schema fields.",
    )

    # -------------------------------------------------------------------------
    # Quality Scoring & Telemetry Metrics
    # -------------------------------------------------------------------------
    # Normalized composite metric (0.0 to 1.0) reflecting overall extraction reliability.
    # Downstream Straight-Through Processing (STP) engines use this score against approval
    # thresholds (e.g., >= 0.85) to determine whether a claim qualifies for zero-touch processing.
    confidence_score: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Overall extraction confidence score (0.0 to 1.0).",
    )

    # Specific to raster image and scanned PDF pipelines using Tesseract/EasyOCR.
    # Downstream image quality monitors evaluate this score to detect unreadable hospital
    # printouts or blurry scans, prompting document re-upload before adjudication.
    ocr_confidence: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="OCR quality score if input went through image/OCR extraction.",
    )

    # -------------------------------------------------------------------------
    # Auditability & Field Lineage Diagnostics
    # -------------------------------------------------------------------------
    # Crucial for regulatory compliance, transparency, and fraud detection.
    # Informs downstream auditors which field values were deduced via clinical heuristics
    # (e.g., room category or admission type) rather than explicitly stated by the hospital.
    inferred_fields: list[str] = Field(
        default_factory=list,
        description="List of field names that were guessed or filled with default heuristics.",
    )

    # Identifies mandatory IRDAI/TPA fields absent from the input document.
    # Directly feeds the interactive clarification wizard and query notice generators,
    # pinpointing exactly which data elements must be gathered from the submitter.
    missing_fields: list[str] = Field(
        default_factory=list,
        description="List of mandatory schema fields that could not be extracted.",
    )

    # Contains granular schema validation and business rule error messages.
    # Downstream API endpoints and CLI interfaces display these errors to provide
    # clear, actionable diagnostics so users understand why a submission was rejected.
    validation_errors: list[str] = Field(
        default_factory=list,
        description="List of Pydantic validation errors or logical rule failures.",
    )

    # Preserves an excerpt of raw extracted text for traceability and debugging.
    # Downstream telemetry and support teams use this snippet to verify extractor
    # fidelity against the source document without retaining entire large files in memory.
    raw_text_snippet: Optional[str] = Field(
        default=None,
        description="Truncated snippet of raw extracted source text (for debugging/audit).",
    )

    # -------------------------------------------------------------------------
    # Interactive Resolution & TPA Communications
    # -------------------------------------------------------------------------
    # Maps field names to pre-constructed, user-friendly conversational questions.
    # Downstream interactive CLI wizards, chatbots, and web forms use these prompts
    # directly to conduct guided interviews without re-analyzing the request schema.
    clarification_questions: dict[str, str] = Field(
        default_factory=dict,
        description="Map of field name to user question prompt for missing/ambiguous fields.",
    )

    # Formal, pre-formatted IRDAI-compliant deficiency query notice.
    # Downstream notification dispatchers (email/fax/portal webhook) can transmit this
    # letter directly to the submitting hospital to pause pre-auth SLA clocks while awaiting info.
    pending_query_notice: Optional[str] = Field(
        default=None,
        description="Formal IRDAI/TPA Pre-Auth Query Notice for requesting missing details from submitter.",
    )

    # -------------------------------------------------------------------------
    # Serialization Methods
    # -------------------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        """Dump result as a JSON-serializable dictionary.

        Downstream REST APIs, logging frameworks, and caching layers call this
        method to serialize the unified result into standard JSON primitives.

        Returns:
            dict[str, Any]: Fully serialized dictionary representation of the IntakeResult.

        Example:
            >>> result_dict = result.to_dict()
            >>> print(result_dict["is_success"])
            True
        """
        return self.model_dump(mode="json")
