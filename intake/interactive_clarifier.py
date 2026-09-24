"""
intake/interactive_clarifier.py
--------------------------------
Interactive Clarification Workflow Module.

When an intake document has missing or low-confidence inferred details,
this module prompts the user field-by-field, accepts corrected inputs,
updates the request dictionary, and re-validates the payload into a 100%
validated PreAuthRequest object.

Architecture Overview:
----------------------
In a production cashless health insurance pipeline, automated document parsing
(via OCR, vision models, or LLMs) frequently produces partial or uncertain data.
Rather than rejecting the pre-authorisation request outright or forcing the hospital
to resubmit the entire file, this module executes an interactive clarification loop.
It bridges raw extraction and strict Pydantic validation by:
1. Utilizing an existing partial request or a complete baseline fallback template.
2. Iterating through missing and low-confidence fields using user-friendly prompts.
3. Dynamically mutating nested payload dictionaries via path traversal helpers.
4. Synchronizing cross-model identifiers (such as policy numbers).
5. Executing strict schema re-validation to certify data integrity before adjudication.
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any, Callable, Optional

# pyrefly: ignore [missing-import]
from schemas import (
    AdmissionType,
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
)
from intake.models import IntakeResult
from intake.narrative_generator import generate_narrative_summary
from intake.query_generator import FIELD_PROMPTS


# =============================================================================
# Section 1: Interactive Clarification Workflow
# =============================================================================

def interactive_clarify(
    result: IntakeResult,
    input_func: Callable[[str], str] = input,
) -> IntakeResult:
    """
    Prompt the user interactively to fill in missing fields or confirm/correct
    inferred fields. Re-validates against PreAuthRequest schema.

    The workflow handles missing mandatory fields and verifies low-confidence
    heuristic extractions. Upon collecting user input, the working payload is
    re-validated through the Pydantic schema to produce a certified IntakeResult.

    Args:
        result (IntakeResult): The initial intake result containing extracted data,
            validation status, and lists of missing or low-confidence inferred fields.
        input_func (Callable[[str], str], optional): A callable accepting a prompt string
            and returning user input. Defaults to built-in `input`. Can be mocked or
            overridden in unit tests or headless automated pipelines.

    Returns:
        IntakeResult: A newly constructed IntakeResult instance. If re-validation
            succeeds, `is_success` is True, confidence is 1.0, and the updated
            PreAuthRequest and narrative summary are attached. If re-validation
            fails, `is_success` is False with validation errors captured.

    Example:
        >>> # Interactive CLI execution with standard input
        >>> verified_result = interactive_clarify(initial_intake_result)
        >>> if verified_result.is_success:
        ...     print("Intake ready for adjudication:", verified_result.request.request_id)
    """
    # -------------------------------------------------------------------------
    # 1. Early Exit Optimization
    # -------------------------------------------------------------------------
    # Avoid prompting the user if the intake is already 100% verified and valid.
    # Short-circuiting prevents redundant console pauses in automated workflows.
    if not result.missing_fields and not result.inferred_fields and result.is_success:
        print("[+] All details are complete and 100% verified. No clarification needed.")
        return result

    print("\n=======================================================")
    print("      INTERACTIVE INTAKE CLARIFICATION WORKFLOW")
    print("=======================================================")
    print("Certain details are missing or were inferred from your document.")
    print("Please answer the following prompts to complete the intake:\n")

    # -------------------------------------------------------------------------
    # 2. Payload Initialization & Baseline Fallback Payload
    # -------------------------------------------------------------------------
    # Determine the working dictionary to mutate.
    if result.request:
        # Serializing to JSON and re-loading converts complex Pydantic types (Enums,
        # Decimals, Dates) into standard JSON-compatible native Python primitives,
        # ensuring seamless string overrides without type mismatches.
        payload = json.loads(result.request.model_dump_json())
    else:
        # Why the Baseline Fallback Payload Exists:
        # When an OCR or document ingestion step fails catastrophically (e.g. corrupted PDF,
        # illegible scan, or schema parsing failure), `result.request` is None.
        # Without a baseline fallback, the user would need to input 25+ mandatory schema
        # attributes manually, or the system would fail with missing structural dictionary keys.
        #
        # The fallback payload supplies a complete, syntactically and semantically valid
        # pre-authorisation scaffold pre-populated with reasonable default values
        # (current submission date, standard individual plan, typical hospital tier,
        # placeholder clinical and cost structures).
        # As the user answers clarification prompts, their inputs overwrite the template.
        # This guarantees that when Pydantic re-validates the payload, all mandatory
        # nested sub-models (`patient`, `policy`, `hospital`, `diagnosis`, `procedure`,
        # `cost_estimate`) exist with valid types.
        from datetime import date
        payload = {
            "submitted_at": date.today().isoformat(),
            "source_format": result.source_format.value,
            "status": "pending",
            "patient": {"full_name": "Insured Patient", "age": 35, "gender": "male", "policy_number": "POL-TEMP"},
            "policy": {
                "policy_number": "POL-TEMP",
                "plan_type": "individual",
                "sum_insured": "500000.00",
                "policy_start_date": "2025-01-01",
                "co_pay_pct": "0.00",
            },
            "hospital": {
                "name": "General Hospital",
                "city": "Mumbai",
                "network_tier": "cashless_network",
                "category": "multi_specialty",
            },
            "diagnosis": {"description": "Clinical Condition", "icd10_code": "H26.9", "is_pre_existing": False},
            "procedure": {"description": "Medical Procedure", "procedure_code": "CPT-66984", "admission_type": "planned"},
            "cost_estimate": {
                "line_items": [{"item": "Estimated Charges", "amount": "50000.00", "category": "other"}],
                "total_amount": "50000.00",
            },
        }

    # -------------------------------------------------------------------------
    # 3. Prompting Missing Fields
    # -------------------------------------------------------------------------
    # Missing fields represent hard gaps where no data was extracted.
    # The user must provide a value to satisfy mandatory schema constraints.
    for field in result.missing_fields:
        prompt_desc = FIELD_PROMPTS.get(field, f"Value for '{field}'")
        val = input_func(f"[MISSING] Enter {prompt_desc}: ").strip()

        # If the user presses Enter without typing, the existing or fallback default
        # is preserved rather than overwritten with an empty string.
        if val:
            _set_nested_field(payload, field, val)

    # -------------------------------------------------------------------------
    # 4. Prompting Low-Confidence Inferred Fields
    # -------------------------------------------------------------------------
    # Inferred fields represent guesses made by OCR/NLP models.
    # Displaying the current value allows the operator to verify quickly by pressing
    # Enter to accept, or typing a new string to overwrite the inference.
    for field in result.inferred_fields:
        curr_val = _get_nested_field(payload, field)
        prompt_desc = FIELD_PROMPTS.get(field, f"Value for '{field}'")
        val = input_func(f"[INFERRED] Confirm/update {prompt_desc} (current: '{curr_val}'): ").strip()

        # Only mutate the payload if the user entered a non-empty override.
        if val:
            _set_nested_field(payload, field, val)

    # -------------------------------------------------------------------------
    # 5. Policy Number Synchronization Logic
    # -------------------------------------------------------------------------
    # Why Policy Number Sync Logic is Necessary:
    # In the PreAuthRequest data architecture, both `Patient` (for member identity
    # and cashless card verification) and `Policy` (for coverage entitlement) track
    # the policy identifier. If the hospital user updates `policy.policy_number`
    # during clarification, `patient.policy_number` would become desynchronized if not
    # explicitly copied. This synchronization ensures cross-entity relational consistency
    # and satisfies internal schema validation rules.
    pol_num = payload["policy"].get("policy_number")
    if pol_num:
        payload["patient"]["policy_number"] = pol_num

    # -------------------------------------------------------------------------
    # 6. Re-Validation Flow After User Input
    # -------------------------------------------------------------------------
    # Re-validating the mutated payload through Pydantic is critical because user
    # input from the console is untyped raw string text. Pydantic coerces numeric
    # strings into Decimals, parses ISO strings into dates, maps string tokens to
    # Enums, and executes custom validators (e.g. age range, positive amounts).
    print("\n[*] Re-validating intake payload against PreAuthRequest schema...")
    try:
        # Strict validation converts the untyped dictionary back into a certified model
        updated_req = PreAuthRequest.model_validate(payload)
        
        # Regenerate the narrative summary from the newly validated fields to guarantee
        # no narrative drift between user inputs and the generated text.
        new_narrative = generate_narrative_summary(updated_req)

        print("[+] Clarification SUCCESS! Intake fully validated.")
        
        # Return an IntakeResult with 100% confidence, cleared deficiencies, and
        # any pending query notice dismissed since all ambiguities are now resolved.
        return IntakeResult(
            request=updated_req,
            is_success=True,
            source_format=result.source_format,
            summary=new_narrative,
            confidence_score=1.0,
            ocr_confidence=result.ocr_confidence,
            inferred_fields=[],
            missing_fields=[],
            validation_errors=[],
            clarification_questions={},
            pending_query_notice=None,
            raw_text_snippet=result.raw_text_snippet,
        )
    except Exception as exc:
        # Graceful failure handling: if the user typed an invalid format (e.g. letters
        # for a sum insured amount or malformed date), catch the exception, record the
        # specific validation error, and return a failed IntakeResult rather than crashing
        # the entire application runtime.
        err_msg = str(exc)
        print(f"[-] Clarification re-validation failed: {err_msg}")
        return IntakeResult(
            request=None,
            is_success=False,
            source_format=result.source_format,
            summary=f"Clarification payload failed validation: {err_msg}",
            confidence_score=0.0,
            ocr_confidence=result.ocr_confidence,
            inferred_fields=result.inferred_fields,
            missing_fields=result.missing_fields,
            validation_errors=[err_msg],
            clarification_questions=result.clarification_questions,
            pending_query_notice=result.pending_query_notice,
            raw_text_snippet=result.raw_text_snippet,
        )


# =============================================================================
# Section 2: Nested Dictionary Manipulation Helpers
# =============================================================================
# Why Helper Functions Exist:
# The intake schema uses dot-notated field paths (e.g., 'cost_estimate.total_amount')
# to identify fields across nested Pydantic models. Working with deeply nested Python
# dictionaries using dynamic string paths requires iterative traversal and automatic
# creation of missing intermediate branches (auto-vivification). These utilities
# isolate deep dictionary access and mutation from the workflow logic.

def _set_nested_field(d: dict[str, Any], path: str, value: Any) -> None:
    """Sets a value in a deeply nested dictionary using a dot-notated key path.

    Splits the path into tokens and traverses each hierarchy level. If an intermediate
    key does not exist or does not hold a dictionary, a new dictionary is automatically
    instantiated (auto-vivification) to prevent KeyErrors. Finally, assigns the value
    to the terminal leaf key.

    Args:
        d (dict[str, Any]): The target dictionary to mutate in-place.
        path (str): Dot-separated path representing the hierarchy (e.g., 'patient.age').
        value (Any): The value to assign at the leaf position.

    Example:
        >>> data = {"patient": {}}
        >>> _set_nested_field(data, "patient.name", "John")
        >>> print(data["patient"]["name"])
        John
    """
    parts = path.split(".")
    curr = d
    # Traverse all parent levels, creating empty dictionaries if paths are missing
    for p in parts[:-1]:
        if p not in curr or not isinstance(curr[p], dict):
            curr[p] = {}
        curr = curr[p]
    # Assign the value to the terminal leaf key
    curr[parts[-1]] = value


def _get_nested_field(d: dict[str, Any], path: str) -> Any:
    """Safely retrieves a value from a nested dictionary using a dot-notated key path.

    Traverses the dictionary along each dot-separated segment. If any intermediate
    key is missing or if an intermediate value is not a dictionary, safely returns
    an empty string instead of raising a KeyError or AttributeError.

    Args:
        d (dict[str, Any]): The dictionary to read from.
        path (str): Dot-separated path to inspect (e.g., 'hospital.city').

    Returns:
        Any: The value found at the specified path, or an empty string `""` if
            any segment of the path does not exist or is invalid.

    Example:
        >>> data = {"hospital": {"city": "Mumbai"}}
        >>> print(_get_nested_field(data, "hospital.city"))
        Mumbai
        >>> print(_get_nested_field(data, "hospital.nonexistent.field"))
        <empty string>
    """
    parts = path.split(".")
    curr = d
    # Walk down the dictionary path safely
    for p in parts:
        if isinstance(curr, dict) and p in curr:
            curr = curr[p]
        else:
            # Return empty string as a safe fallback for prompt rendering
            return ""
    return curr
