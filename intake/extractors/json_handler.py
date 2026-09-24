"""
intake/extractors/json_handler.py
---------------------------------
Handler for structured JSON pre-auth requests.
Validates JSON directly against the PreAuthRequest schema.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Union

# pyrefly: ignore [missing-import]
from schemas import PreAuthRequest, SourceFormat
from intake.models import IntakeResult
from intake.narrative_generator import generate_narrative_summary


def process_json_intake(source: Union[str, Path, dict]) -> IntakeResult:
    """
    Process a JSON input (raw string, file path, or dictionary).

    Supports polymorphic input sources: directly validates dictionary payloads,
    reads JSON files from disk, or parses raw JSON strings. Because structured JSON
    directly mirrors the target domain schema, this handler bypasses natural language
    extraction and runs direct Pydantic schema validation.

    Args:
        source (Union[str, Path, dict]): Input payload provided as an in-memory dictionary,
            a filesystem path (str or Path), or a serialized JSON string.

    Returns:
        IntakeResult: Complete result containing the validated PreAuthRequest,
            generated narrative summary, confidence score (1.0 on success), and
            any validation diagnostics.

    Example:
        >>> payload = {"patient": {"id": "P123", "name": "Jane Doe", "dob": "1980-01-01"}}
        >>> result = process_json_intake(payload)
        >>> print(result.is_success, result.summary)
    """
    # =========================================================================
    # 1. Multi-Input Polymorphism & Payload Deserialization
    # =========================================================================
    # Capture a 300-character snippet for diagnostic audit logging and UI display
    # without inflating memory consumption on large payloads.
    raw_snippet: str = ""

    if isinstance(source, dict):
        # Case A: Direct in-memory dictionary (e.g. from FastAPI endpoints or webhook payloads).
        # Bypasses disk I/O and deserialization overhead entirely.
        payload = source
        raw_snippet = json.dumps(payload)[:300]

    elif isinstance(source, (str, Path)):
        src_path = Path(source)
        if src_path.is_file():
            # Case B: Filesystem path to a JSON file (e.g. batch queue or test fixture).
            with open(src_path, "r", encoding="utf-8") as f:
                content = f.read()
                raw_snippet = content[:300]
                payload = json.loads(content)
        else:
            # Case C: Serialized JSON string payload (e.g. message broker event body).
            raw_snippet = str(source)[:300]
            payload = json.loads(str(source))

    else:
        # Case D: Unsupported input type. Return structured failure result instead of
        # raising an unhandled TypeError, preserving pipeline resilience.
        return IntakeResult(
            request=None,
            is_success=False,
            source_format=SourceFormat.JSON,
            summary="Invalid input type provided for JSON handler.",
            confidence_score=0.0,
            missing_fields=["payload"],
            validation_errors=["Expected dict, filepath, or JSON string."],
        )

    # =========================================================================
    # 2. Direct Pydantic Validation & Narrative Synthesis
    # =========================================================================
    try:
        # Direct Pydantic validation: structured submissions bypass LLM extraction
        # passes, eliminating latency and non-deterministic hallucination risk.
        req = PreAuthRequest.model_validate(payload)

        # Produce a standardized clinical narrative summary so human reviewers
        # have an identical presentation format regardless of whether the intake
        # originated from free text, PDF, or structured JSON.
        summary = generate_narrative_summary(req)

        # Assign confidence_score=1.0 because structured schema ingestion involves
        # zero OCR noise or statistical NLP inference ambiguity.
        return IntakeResult(
            request=req,
            is_success=True,
            source_format=SourceFormat.JSON,
            summary=summary,
            confidence_score=1.0,
            inferred_fields=[],
            missing_fields=[],
            validation_errors=[],
            raw_text_snippet=raw_snippet,
        )

    except Exception as exc:
        # =====================================================================
        # 3. Schema Violation & Parse Error Handling
        # =====================================================================
        # Capture Pydantic ValidationError or JSONDecodeError details and package
        # them into validation_errors for clear API consumer troubleshooting.
        err_msg = str(exc)
        return IntakeResult(
            request=None,
            is_success=False,
            source_format=SourceFormat.JSON,
            summary=f"JSON validation failed against PreAuthRequest schema: {err_msg}",
            confidence_score=0.0,
            missing_fields=[],
            validation_errors=[err_msg],
            raw_text_snippet=raw_snippet,
        )
