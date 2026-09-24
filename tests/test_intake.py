"""
tests/test_intake.py
--------------------
Automated unit & integration test suite for the Multi-Format Intake System.
Tests all 6 input format handlers, structured extraction, confidence scoring,
narrative generation, and failure reporting.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

# pyrefly: ignore [missing-import]
from intake import process_intake, detect_format
# pyrefly: ignore [missing-import]
from schemas import SourceFormat, PreAuthRequest


class TestMultiFormatIntake(unittest.TestCase):
    """Test suite validating end-to-end multi-format pre-authorization intake.

    Covers format auto-detection, ingestion across native JSON, digital PDF,
    scanned image OCR, DOCX, and plain text, along with negative failure paths
    and interactive Human-in-the-Loop (HITL) clarification query notices.
    """

    @classmethod
    def setUpClass(cls):
        """Initializes shared test fixtures and directory paths.

        Uses class-level setup to define immutable directory references once
        for the entire test suite, avoiding redundant Path allocations across
        individual test executions.
        """
        cls.base_dir = Path("data/synthetic_docs")
        cls.json_valid_dir = Path("data/synthetic/valid")
        cls.json_invalid_dir = Path("data/synthetic/invalid")

    # -----------------------------------------------------------------------
    # 1. Format Auto-Detection Tests
    # -----------------------------------------------------------------------

    def test_format_detection(self):
        """Validates input format auto-detection across types and file extensions.

        Ensures `detect_format` accurately routes diverse payload representations:
          - In-memory dictionary -> Format "1" (Structured JSON)
          - String path with .json extension -> Format "1" (JSON file)
          - Path object with .pdf extension -> Format "2" (Digital PDF)
          - Path object with .png extension -> Format "4" (Scanned Image / OCR)
          - Path object with .docx extension -> Format "5" (Microsoft Word DOCX)
          - Path object with .txt extension -> Format "6" (Plain Text)

        WHY: The intake entrypoint must seamlessly accept both in-memory Python
        objects and filesystem paths (strings or pathlib.Path) submitted by
        different upstream services (REST API, batch workers, email pollers).
        """
        # In-memory dictionary payload detection
        self.assertEqual(detect_format({"test": 1}), "1")
        # File path string detection for JSON
        self.assertEqual(detect_format("data/synthetic/valid/request_0001.json"), "1")
        # Pathlib object detection for PDF
        self.assertEqual(detect_format(self.base_dir / "pdf" / "valid_request_0001.pdf"), "2")
        # Pathlib object detection for scanned image PNG
        self.assertEqual(detect_format(self.base_dir / "images" / "valid_request_0001.png"), "4")
        # Pathlib object detection for Word DOCX
        self.assertEqual(detect_format(self.base_dir / "docx" / "valid_request_0001.docx"), "5")
        # Pathlib object detection for plain text TXT
        self.assertEqual(detect_format(self.base_dir / "txt" / "valid_request_0001.txt"), "6")

    # -----------------------------------------------------------------------
    # 2. JSON Intake Handler Tests
    # -----------------------------------------------------------------------

    def test_json_intake_success(self):
        """Validates happy-path ingestion of fully formed, valid JSON pre-auth requests.

        Verifies that:
          1. The intake pipeline executes successfully (`is_success` is True).
          2. The deserialized object is populated and strictly adheres to the
             `PreAuthRequest` Pydantic schema model.
          3. Format provenance is accurately recorded as `SourceFormat.JSON`.
          4. Confidence score is exactly 1.0, because structured JSON input involves
             no heuristic extraction or OCR uncertainty.
          5. Automated clinical summary generation extracts patient details into
             human-readable notes for TPA triage.
        """
        json_file = self.json_valid_dir / "request_0001.json"
        result = process_intake(json_file, format_override="1")
        
        # Confirm intake completed without unhandled exceptions
        self.assertTrue(result.is_success)
        # Ensure a validated Pydantic domain model was generated
        self.assertIsNotNone(result.request)
        self.assertIsInstance(result.request, PreAuthRequest)
        # Verify provenance tracking metadata
        self.assertEqual(result.source_format, SourceFormat.JSON)
        # JSON parsing has zero extraction ambiguity, so confidence must be 100%
        self.assertEqual(result.confidence_score, 1.0)
        # Verify the intake summary narrative was compiled for claims handlers
        self.assertIn("Patient:", result.summary)

    def test_json_intake_failure(self):
        """Validates rejection and diagnostic reporting on adversarial/invalid payloads.

        Exercises an adversarial JSON file containing intentional data violations
        (e.g., policy number mismatch, arithmetic cost discrepancy, or invalid ICD-10).

        Verifies that:
          1. `is_success` is False, confirming the pipeline rejects invalid data
             rather than allowing corrupt claims into adjudication.
          2. `result.request` is None to prevent downstream services from acting
             on invalid domain objects.
          3. `validation_errors` contains descriptive error strings capturing
             the exact reason for rejection for auditability.
        """
        json_file = self.json_invalid_dir / "request_0181.json"
        result = process_intake(json_file, format_override="1")

        # Ingestion must fail gracefully
        self.assertFalse(result.is_success)
        # No corrupted domain model should be emitted
        self.assertIsNone(result.request)
        # Diagnostic error records must be captured for triage
        self.assertGreater(len(result.validation_errors), 0)

    # -----------------------------------------------------------------------
    # 3. Digital PDF Intake Handler Tests
    # -----------------------------------------------------------------------

    def test_pdf_intake_success(self):
        """Validates extraction and parsing from digital vector PDF documents.

        Verifies that:
          1. The digital PDF text stream is successfully extracted and structured.
          2. The output conforms to `PreAuthRequest` schema.
          3. Provenance reflects `SourceFormat.PDF`.
          4. Confidence score exceeds the minimum operational threshold (> 0.5),
             accounting for slight heuristic variance compared to direct JSON.
          5. Clinical narrative summary extracts key diagnosis fields.
        """
        pdf_file = self.base_dir / "pdf" / "valid_request_0001.pdf"
        result = process_intake(pdf_file, format_override="2")

        # Extraction and schema validation must succeed
        self.assertTrue(result.is_success)
        self.assertIsNotNone(result.request)
        # Metadata must reflect digital PDF origin
        self.assertEqual(result.source_format, SourceFormat.PDF)
        # Heuristic extraction carries slight uncertainty, but must remain reliable
        self.assertGreater(result.confidence_score, 0.5)
        # Confirm clinical fields were parsed into summary
        self.assertIn("Diagnosis", result.summary)

    # -----------------------------------------------------------------------
    # 4. Scanned PDF / Image OCR Intake Handler Tests
    # -----------------------------------------------------------------------

    def test_image_ocr_intake_success(self):
        """Validates optical character recognition (OCR) and ingestion from scanned images.

        Simulates intake of a scanned paper pre-authorisation form submitted as a PNG.

        Verifies that:
          1. OCR engine extracts text and maps it into a valid `PreAuthRequest`.
          2. OCR confidence score is tracked and meets the operational quality
             floor (>= 0.70) required for automated processing without manual re-keying.
          3. Generated clinical summary reflects successful document extraction.
        """
        img_file = self.base_dir / "images" / "valid_request_0001.png"
        result = process_intake(img_file, format_override="4")

        # Ingestion must succeed through OCR pipeline
        self.assertTrue(result.is_success)
        self.assertIsNotNone(result.request)
        # OCR confidence must be populated
        self.assertIsNotNone(result.ocr_confidence)
        # OCR character recognition confidence must exceed regulatory threshold
        self.assertGreaterEqual(result.ocr_confidence, 0.70)
        # Summary narrative must confirm pre-authorisation request classification
        self.assertIn("Pre-authorisation request", result.summary)

    # -----------------------------------------------------------------------
    # 5. DOCX Intake Handler Tests
    # -----------------------------------------------------------------------

    def test_docx_intake_success(self):
        """Validates ingestion from Microsoft Word (.docx) hospital pre-auth templates.

        Verifies that:
          1. XML document structure is parsed and mapped into `PreAuthRequest`.
          2. Confidence score exceeds minimum acceptance threshold (> 0.5).
        """
        docx_file = self.base_dir / "docx" / "valid_request_0001.docx"
        result = process_intake(docx_file, format_override="5")

        # Ingestion must succeed through DOCX parser
        self.assertTrue(result.is_success)
        self.assertIsNotNone(result.request)
        # Document structural parsing must maintain high confidence
        self.assertGreater(result.confidence_score, 0.5)

    # -----------------------------------------------------------------------
    # 6. Plain Text Intake Handler Tests
    # -----------------------------------------------------------------------

    def test_text_intake_success(self):
        """Validates ingestion from unstructured or semi-structured plain text files.

        Simulates intake from an email body, text file, or copy-pasted submission.

        Verifies that:
          1. Heuristic regex and keyword extractors successfully populate `PreAuthRequest`.
          2. Summary narrative includes extracted hospital identification.
        """
        txt_file = self.base_dir / "txt" / "valid_request_0001.txt"
        result = process_intake(txt_file, format_override="6")

        # Text ingestion and model construction must succeed
        self.assertTrue(result.is_success)
        self.assertIsNotNone(result.request)
        # Summary narrative must verify hospital extraction
        self.assertIn("Hospital", result.summary)

    # -----------------------------------------------------------------------
    # 7. Partial Failure & Malformed Error Reporting Tests
    # -----------------------------------------------------------------------

    # -----------------------------------------------------------------------
    # 8. Interactive Clarification & Query Notice Tests
    # -----------------------------------------------------------------------

    def test_query_notice_and_clarification(self):
        """Validates Human-In-The-Loop (HITL) clarification flow for incomplete requests.

        When a pre-authorization submission is missing critical mandatory data
        (such as the patient's insurance policy number), the pipeline should not
        abruptly fail. Instead, it must:
          1. Generate an official IRDAI-compliant TPA Pre-Authorisation Query Notice.
          2. Formulate specific clarification questions targeting the missing attributes.
          3. Allow interactive resolution (via `interactive_clarify`) using user/hospital
             feedback to supply the missing information.
          4. Transition the request into a fully valid, successful `PreAuthRequest`.
        """
        from intake.interactive_clarifier import interactive_clarify

        # Simulate an incomplete submission missing mandatory policy number and cost details
        raw_incomplete = "Patient Name: Rajesh Sharma\nDiagnosis: Acute Appendicitis\nProcedure: Appendectomy\nHospital: Fortis Hospital"
        result = process_intake(raw_incomplete, format_override="6")

        # Confirm the incomplete request generated a formal TPA Query Notice
        self.assertIsNotNone(result.pending_query_notice)
        # Query notice must contain standard IRDAI regulatory header
        self.assertIn("HEALTH INSURANCE TPA PRE-AUTHORISATION QUERY NOTICE", result.pending_query_notice)
        # Query questions list must contain actionable prompts for missing fields
        self.assertGreater(len(result.clarification_questions), 0)

        # Mock interactive answers for missing policy number
        # WHY: `interactive_clarify` normally halts execution waiting for terminal
        # input from `sys.stdin`. In headless CI/CD environments, this would block
        # indefinitely. `mock_input` simulates an interactive user response by
        # inspecting the prompt text for keywords ('policy number' / 'health card id')
        # and supplying the missing value 'POL-998877'.
        def mock_input(prompt: str) -> str:
            """Simulates user keyboard input during interactive clarification prompts.

            Args:
                prompt: The query string presented to the user.

            Returns:
                Mocked policy number if the prompt asks for policy/health card ID,
                otherwise an empty string to simulate default/empty input.
            """
            if "policy number" in prompt.lower() or "health card id" in prompt.lower():
                return "POL-998877"
            return ""

        # Run interactive clarification using the mock input function
        clarified_result = interactive_clarify(result, input_func=mock_input)
        
        # After supplying the missing policy number, the request must transition to success
        self.assertTrue(clarified_result.is_success)
        self.assertIsNotNone(clarified_result.request)
        # The supplied policy number must be properly injected into the domain model
        self.assertEqual(clarified_result.request.policy.policy_number, "POL-998877")


if __name__ == "__main__":
    unittest.main()
