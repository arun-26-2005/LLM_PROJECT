"""
intake/__init__.py
------------------
Main entry-point package for the Multi-Format Pre-Authorisation Intake System.

Exports:
  - process_intake(source, format_override=None): Auto-sniffs format or accepts override, routes to correct handler.
  - IntakeResult: Unified intake output object.
  - detect_format(source): Auto-sniffs source format.
  - FORMAT_MENU: Mapping of format keys to display labels and processing pipelines.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional, Union

from intake.models import IntakeResult
from intake.extractors.json_handler import process_json_intake
from intake.extractors.pdf_handler import process_digital_pdf_intake
from intake.extractors.ocr_handler import process_ocr_intake
from intake.extractors.docx_handler import process_docx_intake
from intake.extractors.text_handler import process_text_intake

# pyrefly: ignore [missing-import]
from schemas import SourceFormat

# ============================================================================
# FORMAT MENU SPECIFICATION
# ============================================================================

# Single source of truth for supported ingestion formats and their pipeline descriptions.
# This mapping decouples CLI/UI display logic from internal format codes, ensuring
# that interactive prompts, API documentation, and help text remain synchronized.
# Each entry maps a choice key ("1"-"6") to a tuple of (Human-Readable Label, Strategy Description).
FORMAT_MENU = {
    "1": ("JSON", "Direct schema validation"),
    "2": ("Digital PDF", "Text extraction -> structured extraction"),
    "3": ("Scanned PDF", "Image page extraction -> OCR -> structured extraction"),
    "4": ("Image (JPEG/PNG)", "Image OCR -> structured extraction"),
    "5": ("DOCX", "Word document extraction -> structured extraction"),
    "6": ("Plain text", "Free-text extraction -> structured extraction"),
}


# ============================================================================
# AUTOMATIC FORMAT DETECTION & SNIFFING
# ============================================================================

def detect_format(source: Union[str, Path, dict]) -> str:
    """Auto-detects the format of the input source based on type, file extension, or content sniffing.

    Applies a priority-based heuristic detection strategy:
      1. In-memory Python dictionaries are directly identified as JSON payloads.
      2. Verified filesystem paths are inspected by extension, with deep content sniffing
         for PDFs to distinguish between digital vector text and rasterized scans.
      3. Raw string inputs are probed for valid JSON syntax.
      4. Any unidentifiable content defaults to unstructured plain text for NLP parsing.

    Args:
        source: File path (str or Path), raw string content, or dictionary payload.

    Returns:
        Format code key matching FORMAT_MENU ("1", "2", "3", "4", "5", or "6").

    Example:
        >>> detect_format("/path/to/claim.pdf")
        '2'  # If digital PDF containing selectable text
        >>> detect_format({"patient_name": "John Doe"})
        '1'
    """
    # Fast path: in-memory dictionaries already represent structured JSON-compatible data,
    # bypassing any disk I/O or string parsing overhead.
    if isinstance(source, dict):
        return "1"

    source_str = str(source).strip()

    # -------------------------------------------------------------------------
    # Filesystem Path Inspection
    # -------------------------------------------------------------------------
    # Verify the path actually exists on disk before inspecting its extension.
    # This prevents raw string content containing dots or file-like names from being
    # misclassified as file paths.
    path = Path(source_str)
    if path.is_file():
        suffix = path.suffix.lower()

        # Direct JSON configuration or API dump
        if suffix == ".json":
            return "1"

        # PDF Content Sniffing: Distinguish digital vector text from scanned raster pages.
        # Digital PDFs contain selectable font streams that can be extracted cleanly,
        # whereas scanned PDFs consist of embedded raster images requiring expensive OCR.
        elif suffix == ".pdf":
            try:
                from pypdf import PdfReader
                reader = PdfReader(str(path))
                # Aggregate text across all pages to evaluate whether an embedded text layer exists
                text = "".join(page.extract_text() or "" for page in reader.pages)

                # Heuristic threshold: >30 characters indicates a genuine digital text stream.
                # Documents with <=30 characters are typically scanned images wrapped in PDF containers
                # or empty forms, requiring optical character recognition.
                if len(text.strip()) > 30:
                    return "2"  # Digital PDF with selectable text stream
                return "3"      # Scanned PDF requiring page rasterization + OCR
            except Exception:
                # If PDF reading fails (e.g., encryption or minor corruption), default to
                # digital PDF extractor so specialized recovery logic can handle it.
                return "2"

        # Raster graphics: standalone image formats requiring full OCR vision pipeline
        elif suffix in [".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".webp"]:
            return "4"

        # Word processing document: requires OpenXML structure parsing via python-docx
        elif suffix == ".docx":
            return "5"

        # Unstructured or tabular text files: routed to NLP/regex extraction pipeline
        elif suffix in [".txt", ".log", ".md", ".csv"]:
            return "6"

    # -------------------------------------------------------------------------
    # Raw String Content Sniffing
    # -------------------------------------------------------------------------
    # When source is not a file, check if raw string payload represents a serialized JSON object.
    # Checking outer braces first avoids the computational cost of attempting json.loads on
    # arbitrary free-form narrative text.
    if source_str.startswith("{") and source_str.endswith("}"):
        try:
            json.loads(source_str)
            return "1"
        except Exception:
            # Not valid JSON; fall through to plain text extraction
            pass

    # Safe fallback: treat all unclassified inputs as plain text. This ensures the pipeline
    # never drops arbitrary clinical notes, email bodies, or unstructured pre-auth narratives.
    return "6"  # Default to plain text


# ============================================================================
# INTAKE ROUTING & DISPATCH ENGINE
# ============================================================================

def process_intake(
    source: Union[str, Path, dict],
    format_override: Optional[str] = None,
) -> IntakeResult:
    """Main entry point for pre-auth request intake processing.

    Coordinates format determination, normalization of user overrides, and routing
    to the appropriate format-specific extractor. Maintains a uniform error envelope
    if an unsupported format is specified.

    Args:
        source: File path (str/Path), raw string, or dictionary payload.
        format_override: Optional format menu option ("1" to "6") or format alias name
            (e.g., "json", "digital_pdf", "scanned_pdf", "image", "docx", "text").

    Returns:
        IntakeResult: Unified result object containing validated pre-auth model,
            extraction confidence scores, missing field diagnostics, and audit logs.

    Example:
        >>> result = process_intake("hospital_preauth.docx")
        >>> if result.is_success:
        ...     print(f"Validated pre-auth ID: {result.request.request_id}")
    """
    # Prioritize explicit user/caller override; otherwise employ automated sniffing heuristics
    fmt_key = format_override.strip() if format_override else detect_format(source)

    # -------------------------------------------------------------------------
    # Format Alias Normalization
    # -------------------------------------------------------------------------
    # Map descriptive human-readable aliases and common file extensions to internal
    # menu keys ("1"-"6"). This allows programmatic callers and CLI users to specify
    # semantic names (e.g., --format json) rather than arbitrary numeric indices.
    fmt_map = {
        "json": "1",
        "digital_pdf": "2",
        "pdf": "2",
        "scanned_pdf": "3",
        "image": "4",
        "png": "4",
        "jpeg": "4",
        "jpg": "4",
        "docx": "5",
        "text": "6",
        "txt": "6",
    }
    if fmt_key.lower() in fmt_map:
        fmt_key = fmt_map[fmt_key.lower()]

    # -------------------------------------------------------------------------
    # Extractor Dispatch
    # -------------------------------------------------------------------------
    # Route to specialized extractor modules based on normalized format key.
    # Handlers encapsulate format-specific extraction, normalization, and validation.
    if fmt_key == "1":
        # Direct schema parsing and Pydantic validation
        return process_json_intake(source)
    elif fmt_key == "2":
        # Native PDF vector text extraction followed by structured LLM parsing
        return process_digital_pdf_intake(source)
    elif fmt_key == "3":
        # PDF page rasterization into images, followed by OCR and structured parsing
        return process_ocr_intake(source, source_format=SourceFormat.PDF)
    elif fmt_key == "4":
        # Direct image OCR with preprocessing (deskewing, contrast adjustment)
        return process_ocr_intake(source, source_format=SourceFormat.SCANNED_IMAGE)
    elif fmt_key == "5":
        # Paragraph and table extraction from Word documents (.docx)
        return process_docx_intake(source)
    elif fmt_key == "6":
        # Unstructured clinical text parsing via LLM/regex extraction pipeline
        return process_text_intake(source)
    else:
        # Graceful failure: return an explicit failed IntakeResult rather than raising an
        # unhandled exception, ensuring downstream consumers receive a consistent response model.
        return IntakeResult(
            request=None,
            is_success=False,
            source_format=SourceFormat.FORM,
            summary=f"Unsupported format choice '{fmt_key}'. Please select option 1 to 6.",
            confidence_score=0.0,
            validation_errors=[f"Unknown format option: {fmt_key}"],
        )


__all__ = [
    "process_intake",
    "IntakeResult",
    "detect_format",
    "FORMAT_MENU",
]
