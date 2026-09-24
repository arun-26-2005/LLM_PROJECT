"""
intake/cli.py
-------------
Menu-Driven Multi-Format Intake CLI Interface with Interactive Clarification Options.

Usage:
    python -m intake.cli                             # Interactive format menu mode
    python -m intake.cli path/to/file.pdf            # Auto-detect mode
    python -m intake.cli path/to/file.pdf --clarify  # Force interactive clarification workflow
    python -m intake.cli path/to/file.pdf --query    # Generate formal TPA query notice for missing details
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from intake import FORMAT_MENU, process_intake
from intake.interactive_clarifier import interactive_clarify


# ============================================================================
# INTERACTIVE FORMAT MENU PRESENTATION
# ============================================================================

def display_menu() -> None:
    """Displays the interactive format selection menu in the terminal.

    Dynamically iterates through FORMAT_MENU to ensure that available menu options
    remain perfectly synchronized with the underlying ingestion engine.
    Uses fixed-width column formatting to maintain clean tabular visual alignment
    across varying terminal dimensions and system fonts.
    """
    print("\n=======================================================")
    print("  A1 Cashless Health Insurance - Multi-Format Intake")
    print("=======================================================")
    print("Select input format option:")

    # Dynamically pull choices from FORMAT_MENU so new format extractors
    # added to the intake package are automatically reflected in the CLI.
    # Fixed-width padding (label:<18) creates aligned columns without third-party dependencies.
    for key, (label, desc) in FORMAT_MENU.items():
        print(f"  [{key}] {label:<18} — {desc}")
    print("=======================================================\n")


# ============================================================================
# HUMAN-READABLE RESULT FORMATTING
# ============================================================================

def print_result(result) -> None:
    """Prints a structured, human-readable summary of the intake result.

    Formats technical quality metrics (status, confidence scores), audit flags
    (inferred/missing fields, validation errors), and business narratives into
    clearly separated visual sections. Conditionally renders the validated JSON
    payload only upon success to prevent cluttering output during failures.

    Args:
        result (IntakeResult): Unified result envelope from `process_intake`.
    """
    print("\n-------------------------------------------------------")
    print("               INTAKE PROCESSING RESULT")
    print("-------------------------------------------------------")

    # Clear status indicator allows operators to immediately determine outcome
    print(f"Status           : {'SUCCESS [VALIDATED]' if result.is_success else 'FAILED [VALIDATION ERROR]'}")
    print(f"Source Format    : {result.source_format.value.upper()}")

    # Display confidence as an intuitive integer percentage (e.g. 95%) rather than a raw float
    print(f"Confidence Score : {result.confidence_score * 100:.0f}%")

    # Display OCR score only when optical character recognition was actually utilized,
    # preventing misleading or redundant metrics on native digital files.
    if result.ocr_confidence is not None:
        print(f"OCR Quality Score: {result.ocr_confidence * 100:.0f}%")

    # Highlight audit trail diagnostics to immediately alert the operator to gaps
    if result.inferred_fields:
        print(f"Inferred Fields  : {', '.join(result.inferred_fields)}")
    if result.missing_fields:
        print(f"Missing Fields   : {', '.join(result.missing_fields)}")
    if result.validation_errors:
        print(f"Validation Errors: {'; '.join(result.validation_errors)}")

    # Deterministic narrative summary for clinical and claims review
    print("\n--- HUMAN READABLE SUMMARY ---")
    print(result.summary)

    # Only output full schematic JSON if parsing and Pydantic validation succeeded.
    # Suppressing JSON on failures avoids confusing the operator with partial or null payloads.
    if result.is_success and result.request:
        print("\n--- VALIDATED SCHEMATIC JSON PAYLOAD ---")
        print(result.request.model_dump_json(indent=2))
    print("-------------------------------------------------------\n")


# ============================================================================
# MISSING DATA RESOLUTION WORKFLOW
# ============================================================================

def prompt_missing_data_options(result):
    """Prompt user options when missing or inferred details exist.

    Serves as an interactive triage fork when extraction identifies incomplete
    or heuristically deduced clinical details. Provides operators with three
    resolution pathways: immediate interactive Q&A, formal IRDAI query letter
    generation, or proceeding with default heuristics.

    Args:
        result (IntakeResult): Unified result envelope containing missing or inferred fields.

    Returns:
        IntakeResult: Updated result with user clarifications applied, or original result.
    """
    # Fast path: If all mandatory fields were extracted cleanly without heuristic inference,
    # immediately return without interrupting the user or blocking pipeline flow.
    if not result.missing_fields and not result.inferred_fields:
        return result

    print("\n-------------------------------------------------------")
    print("  NOTICE: Missing or Inferred Details Detected")
    print("-------------------------------------------------------")
    if result.missing_fields:
        print(f"  • Missing Fields : {', '.join(result.missing_fields)}")
    if result.inferred_fields:
        print(f"  • Inferred Fields: {', '.join(result.inferred_fields)}")
        
    print("\nChoose how to handle missing details:")
    print("  [1] Interactive Clarification — Prompt me now to fill/confirm missing details")
    print("  [2] Generate TPA Query Notice — Output formal request for missing information")
    print("  [3] Auto-Manage — Keep current heuristic defaults and proceed")

    # Default to Option 1 (Interactive Clarification) on empty Enter to favor
    # maximum data completeness and prompt resolution before submission.
    choice = input("\nEnter choice [1-3] (default: 1): ").strip() or "1"

    # Branch 1: Launch interactive CLI questionnaire to solicit missing values from user
    if choice == "1":
        return interactive_clarify(result)

    # Branch 2: Emit pre-formatted IRDAI-compliant inquiry notice for sending to hospital
    elif choice == "2":
        if result.pending_query_notice:
            print("\n" + result.pending_query_notice)
        else:
            print("\n[-] No query notice required.")
        return result

    # Branch 3: Proceed with current heuristic inferences without blocking execution
    else:
        return result


# ============================================================================
# ARGPARSE SETUP AND DISPATCH LOGIC
# ============================================================================

def main() -> None:
    """CLI entry point coordinating argument parsing, interactive menus, and execution.

    Supports both automated headless execution (with command-line flags and JSON output)
    and interactive terminal sessions (with menus and guided clarification workflows).
    """
    # -------------------------------------------------------------------------
    # Argparse Configuration
    # -------------------------------------------------------------------------
    parser = argparse.ArgumentParser(description="Multi-Format Intake CLI Tool")

    # Positional source is optional (nargs="?") so running `python -m intake.cli`
    # without arguments gracefully opens the interactive menu rather than exiting with an error.
    parser.add_argument("source", nargs="?", help="Path to input file or raw text submission")

    # Restrict format choice to valid keys from FORMAT_MENU, preventing invalid options at parse time.
    parser.add_argument("-f", "--format", choices=list(FORMAT_MENU.keys()), help="Explicit format menu selection (1-6)")

    # Workflow overrides allowing non-interactive scripts to force specific paths
    parser.add_argument("-c", "--clarify", action="store_true", help="Force interactive clarification workflow")
    parser.add_argument("-q", "--query", action="store_true", help="Print formal TPA information query notice")

    # Machine-readable output flag for Unix piping and backend service integration
    parser.add_argument("--json", action="store_true", help="Output result as raw JSON string")

    args = parser.parse_args()

    source = args.source
    fmt_choice = args.format

    # -------------------------------------------------------------------------
    # Interactive Fallback Prompts
    # -------------------------------------------------------------------------
    # When no input source is passed as a CLI argument, activate interactive terminal mode.
    # Prompts the user sequentially for format choice and file path to guide manual testing.
    if not source:
        display_menu()
        fmt_choice = input("Enter option [1-6] (or press Enter for auto-detect): ").strip() or None
        source = input("Enter path to file or text input: ").strip()

    # If the user pressed Enter without providing an input path, abort with a standard error code
    if not source:
        print("Error: No input source provided.", file=sys.stderr)
        sys.exit(1)

    # -------------------------------------------------------------------------
    # Processing Execution & Workflow Dispatch
    # -------------------------------------------------------------------------
    # Run the core intake pipeline with automatic sniffing or user-specified format override
    result = process_intake(source, format_override=fmt_choice)

    # Workflow dispatch precedence:
    # 1. Explicit --clarify flag: Force interactive clarification session unconditionally
    if args.clarify:
        result = interactive_clarify(result)

    # 2. Explicit --query flag: Output formal deficiency notice directly if one was generated
    elif args.query and result.pending_query_notice:
        print("\n" + result.pending_query_notice)

    # 3. Interactive prompt: Only prompt when running interactively (NOT in --json mode)
    #    and when incomplete or inferred data elements were detected.
    #    In --json mode, interactive prompts are skipped to prevent hanging automated scripts.
    elif not args.json and (result.missing_fields or result.inferred_fields):
        result = prompt_missing_data_options(result)

    # -------------------------------------------------------------------------
    # Output Rendering
    # -------------------------------------------------------------------------
    # Emit machine-readable JSON if requested (for pipeline integration),
    # otherwise render human-readable terminal banners and summaries.
    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print_result(result)


if __name__ == "__main__":
    main()
