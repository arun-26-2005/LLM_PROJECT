"""
intake/extractors/text_handler.py
---------------------------------
Handler for plain text pre-auth submissions (.txt file or raw string).
"""

from __future__ import annotations

from pathlib import Path
from typing import Union

# pyrefly: ignore [missing-import]
from schemas import SourceFormat
from intake.models import IntakeResult
from intake.structured_extractor import extract_structured_pre_auth


def process_text_intake(source: Union[str, Path]) -> IntakeResult:
    """
    Process plain text input (either file path or raw string).

    Supports polymorphic ingestion: automatically inspects whether the input argument
    references an existing file on the filesystem or represents raw clinical narrative
    text (e.g. pasted clinical notes, EHR consultation text, or portal submissions).
    Passes sanitized text to the structured pre-authorization extractor.

    Args:
        source (Union[str, Path]): A filesystem path pointing to a text file,
            or the raw clinical text content as a string.

    Returns:
        IntakeResult: Standardized intake result containing the extracted PreAuthRequest,
            clinical summary, confidence score, and validation diagnostics.

    Example:
        >>> raw_note = "Patient: John Doe, DOB: 1985-04-12. Requesting MRI brain."
        >>> result = process_text_intake(raw_note)
        >>> print(f"Extraction status: {result.is_success}")
    """
    text_content: str = ""

    # =========================================================================
    # 1. File vs. Raw String Auto-Detection
    # =========================================================================
    # Polymorphic handling allows the caller to pass either an on-disk .txt path
    # or an unpersisted string buffer without maintaining separate intake entrypoints.
    if isinstance(source, (str, Path)):
        path = Path(source)
        # Check whether the string or Path represents an actual file on disk.
        # If true, open and read with UTF-8 encoding to preserve clinical symbols
        # (e.g., degree signs, micro-units 'µg', comparison operators '≥').
        if path.is_file():
            with open(path, "r", encoding="utf-8") as f:
                text_content = f.read()
        else:
            # If not a file on disk, treat the input directly as the clinical narrative text
            text_content = str(source)

    # =========================================================================
    # 2. Content Normalization & Empty Input Guard
    # =========================================================================
    # Strip leading/trailing whitespace and control characters to measure true content length
    text_content = text_content.strip()

    # Guard against blank or whitespace-only inputs early.
    # Invoking LLM extraction on empty text wastes API tokens, introduces unnecessary
    # network latency, and produces inevitable schema validation errors.
    if not text_content:
        return IntakeResult(
            request=None,
            is_success=False,
            source_format=SourceFormat.FORM,
            summary="Plain text input is empty.",
            confidence_score=0.0,
            missing_fields=["all"],
            validation_errors=["Provided text content is 0 characters."],
        )

    # =========================================================================
    # 3. Structured Information Extraction
    # =========================================================================
    # Plain text inputs represent digital character data with exact fidelity;
    # pass ocr_confidence=None because no optical recognition took place.
    return extract_structured_pre_auth(
        raw_text=text_content,
        source_format=SourceFormat.FORM,
        ocr_confidence=None,
    )
