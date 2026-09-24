"""
intake/extractors/docx_handler.py
---------------------------------
Handler for Microsoft Word (.docx) documents.
Extracts text from paragraphs and tables using python-docx.
"""

from __future__ import annotations

from pathlib import Path
from typing import Union

# pyrefly: ignore [missing-import]
import docx

# pyrefly: ignore [missing-import]
from schemas import SourceFormat
from intake.models import IntakeResult
from intake.structured_extractor import extract_structured_pre_auth


def process_docx_intake(source_path: Union[str, Path]) -> IntakeResult:
    """
    Extract text from a DOCX file and route to structured extractor.

    Parses Microsoft Word (.docx) containers by sequentially extracting narrative
    paragraphs and converting embedded tabular data into markdown-style pipe-delimited
    lines. Passes the synthesized text representation to the structured pre-auth extractor.

    Args:
        source_path (Union[str, Path]): Path to the target .docx document on disk.

    Returns:
        IntakeResult: Standardized result containing the validated PreAuthRequest
            model, clinical summary narrative, confidence metrics, and validation errors.

    Example:
        >>> result = process_docx_intake("forms/prior_authorization_request.docx")
        >>> if result.is_success:
        ...     print(f"Extracted procedure: {result.request.clinical_info.procedure_name}")
    """
    # =========================================================================
    # 1. Path Verification & File Presence Guard
    # =========================================================================
    path = Path(source_path)

    # Fail fast before initializing python-docx / zipfile decoding to provide
    # clear, immediate diagnostics if the file path is invalid or missing.
    if not path.is_file():
        return IntakeResult(
            request=None,
            is_success=False,
            source_format=SourceFormat.FORM,
            summary=f"File not found: {path}",
            confidence_score=0.0,
            validation_errors=[f"DOCX file does not exist at '{path}'."],
        )

    try:
        # =====================================================================
        # 2. Document Parsing & Text Stream Extraction
        # =====================================================================
        # Convert Path object to str for broad compatibility with python-docx's Document constructor
        doc = docx.Document(str(path))
        lines: list[str] = []

        # ---------------------------------------------------------------------
        # Paragraph Extraction
        # ---------------------------------------------------------------------
        # Extract running narrative text. Strip each paragraph and skip empty strings
        # to prevent unnecessary whitespace lines from consuming LLM prompt context tokens.
        for p in doc.paragraphs:
            if p.text.strip():
                lines.append(p.text.strip())

        # ---------------------------------------------------------------------
        # Table Extraction & Pipe-Delimited Formatting
        # ---------------------------------------------------------------------
        # python-docx maintains distinct object trees for paragraphs and tables;
        # tables are not included in doc.paragraphs. Because clinical intake forms
        # frequently place patient details, CPT codes, and medications inside tables,
        # we iterate over each table row and cell.
        for table in doc.tables:
            for row in table.rows:
                # Omit empty cells to avoid disjointed sequences of redundant separators
                row_cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                if row_cells:
                    # Format cells using pipe delimiters (" | "). This mirrors markdown
                    # table syntax, which modern LLMs are extensively trained to parse
                    # into key-value or column-row associations with high fidelity.
                    lines.append(" | ".join(row_cells))

        full_text = "\n".join(lines).strip()

        # =====================================================================
        # 3. Content Validation Guard
        # =====================================================================
        # Guard against empty documents (e.g. documents containing only shapes,
        # watermarks, or unanchored canvas drawings) before triggering LLM calls.
        if not full_text:
            return IntakeResult(
                request=None,
                is_success=False,
                source_format=SourceFormat.FORM,
                summary="DOCX document contains no text content.",
                confidence_score=0.0,
                missing_fields=["all"],
                validation_errors=["Document has 0 paragraphs and empty tables."],
            )

        # =====================================================================
        # 4. Structured Extraction Routing
        # =====================================================================
        # DOCX extraction pulls direct XML character streams, so character transcription
        # is 100% faithful; pass ocr_confidence=None to denote native digital source.
        return extract_structured_pre_auth(
            raw_text=full_text,
            source_format=SourceFormat.FORM,
            ocr_confidence=None,
        )

    except Exception as exc:
        # =====================================================================
        # 5. Exception Handling & Error Packaging
        # =====================================================================
        # Catch corrupt ZIP packages, malformed XML nodes, or schema mismatches,
        # returning an informative failure IntakeResult rather than crashing the worker.
        err_msg = str(exc)
        return IntakeResult(
            request=None,
            is_success=False,
            source_format=SourceFormat.FORM,
            summary=f"Failed to read DOCX document: {err_msg}",
            confidence_score=0.0,
            validation_errors=[err_msg],
        )
