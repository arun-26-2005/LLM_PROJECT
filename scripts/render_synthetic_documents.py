"""
scripts/render_synthetic_documents.py
--------------------------------------
Renders synthetic JSON pre-auth requests into all supported document formats:
  - Digital PDFs (data/synthetic_docs/pdf/)
  - Scanned PDF / Image forms (data/synthetic_docs/images/)
  - Microsoft Word DOCX (data/synthetic_docs/docx/)
  - Plain Text TXT files (data/synthetic_docs/txt/)

Used for end-to-end testing of OCR, text extraction, and multi-format intake.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# pyrefly: ignore [missing-import]
import docx
from PIL import Image, ImageDraw, ImageFont

# pyrefly: ignore [missing-import]
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.lib import colors


# ===========================================================================
# 1. Plain Text Layout & Formatting
# ===========================================================================

def format_request_as_text(data: dict[str, Any]) -> str:
    """Formats a pre-auth dictionary into structured plain text representation.

    Transforms structured JSON claim data into a standardized layout mirroring
    the Indian Third-Party Administrator (TPA) Cashless Authorization Request
    Form (standardized under IRDAI guidelines).

    The layout establishes clearly delineated structural sections:
      - Header & Request Metadata: Request ID, submission timestamp, format.
      - Patient Details: Name, age, gender, card/policy number.
      - Policy Details: Plan type, sum insured, inception date, co-pay ratio.
      - Hospital & Clinical Details: Facility name, network status, ICD-10,
        clinical diagnosis description, procedure code, admission type and date.
      - Estimated Cost Breakdown: Itemized tariff heads with explicit 'INR'
        currency labels and reconciled total amount.

    Delimiters ('---') and consistent label-value naming conventions provide a
    deterministic visual and textual structure across all downstream document
    renderers (PDF, DOCX, TXT, and PNG image OCR).

    Args:
        data: Pre-authorization request dictionary conforming to PreAuthRequest schema.

    Returns:
        Multi-line formatted plain text string of the pre-authorization form.

    Example:
        >>> text = format_request_as_text({"request_id": "REQ-01", ...})
        >>> "PATIENT DETAILS" in text
        True
    """
    # Extract sub-dictionaries with safe fallbacks for missing or partial payloads
    patient = data.get("patient", {})
    policy = data.get("policy", {})
    hosp = data.get("hospital", {})
    diag = data.get("diagnosis", {})
    proc = data.get("procedure", {})
    cost = data.get("cost_estimate", {})

    # Construct the document section by section using standard hospital pre-auth headers
    lines = [
        "A1 CASHLESS HEALTH INSURANCE PRE-AUTHORISATION FORM",
        "--------------------------------------------------",
        f"Request ID: {data.get('request_id')}",
        f"Submission Date: {data.get('submitted_at')}",
        f"Source Format: {data.get('source_format')}",
        "",
        "PATIENT DETAILS",
        "---------------",
        f"Patient Name: {patient.get('full_name')}",
        f"Age: {patient.get('age')}",
        f"Gender: {patient.get('gender')}",
        f"Policy Number: {patient.get('policy_number')}",
        "",
        "POLICY DETAILS",
        "--------------",
        f"Plan Type: {policy.get('plan_type')}",
        f"Sum Insured: {policy.get('sum_insured')}",
        f"Policy Start Date: {policy.get('policy_start_date')}",
        f"Co-Pay: {policy.get('co_pay_pct')}%",
        "",
        "HOSPITAL & CLINICAL DETAILS",
        "---------------------------",
        f"Hospital Name: {hosp.get('name')}",
        f"City: {hosp.get('city')}",
        f"Network Tier: {hosp.get('network_tier')}",
        f"ICD-10 Code: {diag.get('icd10_code')}",
        f"Diagnosis: {diag.get('description')}",
        f"Pre-Existing Condition: {'Yes' if diag.get('is_pre_existing') else 'No'}",
        f"Procedure Code: {proc.get('procedure_code')}",
        f"Procedure: {proc.get('description')}",
        f"Admission Type: {proc.get('admission_type')}",
        f"Admission Date: {data.get('admission_date')}",
        "",
        "ESTIMATED COST BREAKDOWN",
        "-----------------------",
    ]

    # Append itemized billing entries with category and currency tags
    for item in cost.get("line_items", []):
        lines.append(f"  {item.get('item')}: INR {item.get('amount')} ({item.get('category')})")

    lines.append(f"Total Amount: INR {cost.get('total_amount')}")
    return "\n".join(lines)


# ===========================================================================
# 2. Digital PDF Document Rendering
# ===========================================================================

def render_pdf(text_content: str, output_path: Path):
    """Renders digital PDF using ReportLab.

    Constructs a vector-based digital PDF document using ReportLab Platypus
    flowable elements (`SimpleDocTemplate`, `Paragraph`, `Spacer`).

    Document construction steps:
      - Uses `SimpleDocTemplate` configured to standard `letter` page size.
      - Uses `getSampleStyleSheet()` to apply typographic styles (Title, Heading2, Normal).
      - Parses the input text line-by-line into structured flowable elements:
        * Form title ("A1 CASHLESS...") is styled with bold Title styling.
        * Section titles (lines ending with "DETAILS" or "BREAKDOWN") are rendered
          using Heading2 style to enforce visual hierarchy.
        * Dashed underline lines ("---") are intentionally omitted because Platypus
          flowables and Spacers manage vertical whitespace naturally, eliminating
          unsightly ASCII artifacts in the PDF.
        * Body text lines are wrapped into Normal Paragraphs followed by a 4pt
          Spacer to preserve vertical readability without text overlap.
      - Assembles the flowable story and compiles the final PDF to disk.

    Args:
        text_content: Pre-formatted plain text representing the pre-auth request.
        output_path: Target filesystem path for the output `.pdf` file.
    """
    doc = SimpleDocTemplate(str(output_path), pagesize=letter)
    styles = getSampleStyleSheet()
    story = []

    # Map plain-text lines into ReportLab flowable elements
    for line in text_content.splitlines():
        if line.startswith("A1 CASHLESS"):
            story.append(Paragraph(f"<b>{line}</b>", styles["Title"]))
        elif line.endswith("DETAILS") or line.endswith("BREAKDOWN"):
            story.append(Paragraph(f"<b>{line}</b>", styles["Heading2"]))
        elif line.strip().startswith("-"):
            # Omit ASCII divider dashes; styling and spacing provide cleaner visual separation
            continue
        elif line.strip():
            story.append(Paragraph(line, styles["Normal"]))
            story.append(Spacer(1, 4))

    # Compile the flowable story into the final PDF binary
    doc.build(story)


# ===========================================================================
# 3. Microsoft Word (.docx) Document Rendering
# ===========================================================================

def render_docx(data: dict[str, Any], output_path: Path):
    """Renders Microsoft Word (.docx) document.

    Generates a native Microsoft Word (.docx) document using python-docx to model
    hospital liaison office submissions received as Word templates.

    Usage and structural mapping:
      - Instantiates a clean `docx.Document()`.
      - Adds a level-0 title heading for the pre-authorization header.
      - Obtains canonical text via `format_request_as_text(data)` and slices past
        the raw title lines (`[2:]`) to avoid duplicating the document header.
      - Detects section banners ("DETAILS" or "BREAKDOWN") and creates native Word
        Heading 2 elements (`doc.add_heading(line, level=2)`), creating an accessible
        document outline structure that downstream Word extractors can query.
      - Filters out decorative plain-text dashes and writes substantive content
        as standard Word body paragraphs (`doc.add_paragraph(line)`).
      - Serializes the document to the destination `.docx` file.

    Args:
        data: Pre-authorization request dictionary conforming to PreAuthRequest schema.
        output_path: Target filesystem path for the output `.docx` file.
    """
    doc = docx.Document()
    doc.add_heading("A1 Cashless Health Insurance Pre-Authorisation", 0)

    text_content = format_request_as_text(data)
    # Skip the first two header lines since add_heading already created the title
    for line in text_content.splitlines()[2:]:
        if "DETAILS" in line or "BREAKDOWN" in line:
            doc.add_heading(line, level=2)
        elif line.strip() and not line.startswith("-"):
            # Exclude raw separator dashes; native headings provide semantic separation
            doc.add_paragraph(line)

    doc.save(str(output_path))


# ===========================================================================
# 4. Scanned Form Image (PNG) & OCR Ground Truth Rendering
# ===========================================================================

def render_image(text_content: str, output_path: Path):
    """Renders scanned image form (PNG). Embeds layout info for OCR testing.

    Simulates a paper pre-authorisation form digitized via flatbed scanner or fax
    machine (850x1100 px canvas, approximating 8.5x11 inches at ~100 DPI):
      - Creates a crisp RGB image canvas with a standard white page background.
      - Uses `ImageDraw.Draw` to draw text line-by-line at fixed coordinates
        (left margin x=40, line increment y+=22), mimicking a printed mono-spaced form.
      - Stores the source text inside PIL image metadata (`img.info["text"]`) for
        deterministic in-memory verification in test environments without OCR binaries.
      - Companion Ground Truth TXT file:
        Saves an identical `.txt` file alongside the `.png` with matching base name.
        WHY: Optical Character Recognition (OCR) engines (e.g. Tesseract, EasyOCR,
        or vision-language models) can introduce character-level errors or drop
        lines. The companion `.txt` file acts as the 100% verified ground truth
        reference, enabling automated test suites to compute Character Error Rate (CER),
        Word Error Rate (WER), and evaluate extraction accuracy quantitatively.

    Args:
        text_content: Pre-formatted plain text representing the pre-auth request.
        output_path: Target filesystem path for the output `.png` image file.
    """
    img = Image.new("RGB", (850, 1100), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    # Render lines vertically with crisp 16pt font
    try:
        font = ImageFont.load_default(size=16)
    except Exception:
        font = ImageFont.load_default()

    y = 30
    for line in text_content.splitlines():
        draw.text((40, y), line, font=font, fill=(10, 10, 10))
        y += 24

    # Save image with embedded text comment in PIL PngInfo for deterministic fallback OCR testing
    from PIL import PngImagePlugin
    pnginfo = PngImagePlugin.PngInfo()
    pnginfo.add_text("text", text_content)
    pnginfo.add_text("comment", text_content)
    img.save(str(output_path), format="PNG", pnginfo=pnginfo)
    
    # Also save companion text file alongside image for OCR ground truth.
    # WHY: Provides an immutable baseline for automated OCR precision/recall scoring.
    txt_path = output_path.with_suffix(".txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(text_content)


# ===========================================================================
# 5. Multi-Format Batch Document Rendering Pipeline
# ===========================================================================

def main():
    """Generates synthetic test documents across all supported input formats.

    Sampling Strategy:
      Instead of converting all 220 synthetic JSON files (which would consume excessive
      CPU/disk I/O and produce redundant binary assets), a targeted sampling strategy
      is applied:
        - 5 Valid JSON records: Representative sample covering diverse clinical domains
          (daycare cataract, emergency STEMI, elective joint arthroplasty, etc.) to verify
          successful parsing, confidence scoring, and end-to-end schema extraction.
        - 3 Invalid / Adversarial JSON records: Representative flawed payloads (policy
          mismatches, cost reconciliation discrepancies, date errors) to verify that
          multi-format intake parsers faithfully extract corrupted input without silently
          masking or dropping fields, allowing downstream validation layers to trigger.
      
      Total artifacts rendered: 8 records x 4 format modalities = 32 test files across:
        1. Plain Text (.txt)
        2. Digital PDF (.pdf)
        3. Word Document (.docx)
        4. Scanned Form PNG (.png + companion .txt)
    """
    print("[*] Rendering synthetic test documents across all formats...")

    base_dir = Path("data/synthetic_docs")
    pdf_dir = base_dir / "pdf"
    image_dir = base_dir / "images"
    docx_dir = base_dir / "docx"
    txt_dir = base_dir / "txt"

    # Ensure all target modality directories exist before rendering
    for d in [pdf_dir, image_dir, docx_dir, txt_dir]:
        d.mkdir(parents=True, exist_ok=True)

    # Pick sample valid and invalid json files
    # Sort files so request_0001 and consistent fixtures are always rendered
    valid_jsons = sorted(list(Path("data/synthetic/valid").glob("*.json")))[:15]
    invalid_jsons = sorted(list(Path("data/synthetic/invalid").glob("*.json")))[:5]

    all_samples = [(f, True) for f in valid_jsons] + [(f, False) for f in invalid_jsons]

    for json_file, is_valid in all_samples:
        prefix = "valid" if is_valid else "invalid"
        stem = json_file.stem
        
        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        text_rep = format_request_as_text(data)

        # 1. Render TXT
        # Baseline plain text representation for simple string matching and regex parsers
        txt_path = txt_dir / f"{prefix}_{stem}.txt"
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(text_rep)

        # 2. Render Digital PDF
        # Exercises digital PDF text extraction engines (pypdf, pdfplumber)
        pdf_path = pdf_dir / f"{prefix}_{stem}.pdf"
        render_pdf(text_rep, pdf_path)

        # 3. Render DOCX
        # Exercises python-docx parser for hospital word template submissions
        docx_path = docx_dir / f"{prefix}_{stem}.docx"
        render_docx(data, docx_path)

        # 4. Render Image (PNG)
        # Exercises OCR intake pipeline and computer vision text extraction
        img_path = image_dir / f"{prefix}_{stem}.png"
        render_image(text_rep, img_path)

    # 5. Render Adversarial: Illegible Scan (Metrics.md)
    # Severely degraded raster image without companion txt to test OCR failure & rejection gates
    if valid_jsons:
        with open(valid_jsons[0], "r", encoding="utf-8") as f:
            sample_data = json.load(f)
        sample_text = format_request_as_text(sample_data)
        illegible_path = image_dir / "adversarial_illegible_scan.png"
        render_illegible_scan(sample_text, illegible_path)

    # 6. Render Adversarial: Unexpected Language (Hindi / Devanagari) (Metrics.md)
    # Medical pre-auth request in Hindi to test multi-lingual / translation escalation gates
    render_unexpected_language_document(base_dir)

    # Print summary output locations
    print("[+] Synthetic document rendering complete!")
    print(f"  - PDFs   : {pdf_dir}")
    print(f"  - Images : {image_dir}")
    print(f"  - DOCX   : {docx_dir}")
    print(f"  - TXT    : {txt_dir}")


def render_illegible_scan(text_content: str, output_path: Path):
    """Renders a severely degraded scanned form image to test OCR rejection gates.
    
    Applies resolution downscaling, Gaussian blur, low contrast, and compression
    artifacts to simulate an unreadable fax or corrupted scan (Metrics.md).
    """
    from PIL import ImageFilter
    
    img = Image.new("RGB", (850, 1100), color=(240, 240, 240))
    draw = ImageDraw.Draw(img)
    
    y = 30
    for line in text_content.splitlines():
        # Draw low-contrast gray text
        draw.text((40, y), line, fill=(160, 160, 160))
        y += 22

    # Severe downscaling and upscaling to destroy character edge fidelity
    small = img.resize((70, 90), resample=Image.Resampling.BILINEAR)
    upscaled = small.resize((850, 1100), resample=Image.Resampling.NEAREST)
    
    # Heavy Gaussian Blur
    blurred = upscaled.filter(ImageFilter.GaussianBlur(radius=8.0))
    
    # Save as heavily blurred PNG (NO companion .txt file so OCR must process raw pixels)
    blurred.save(str(output_path), format="PNG")


def render_unexpected_language_document(base_dir: Path):
    """Renders an adversarial test document in an unexpected language (Hindi / Devanagari).
    
    Tests Guardrail #1 and Metrics.md requirement for handling out-of-distribution language.
    """
    hindi_text = """A1 कैशलेस स्वास्थ्य बीमा पूर्व-प्राधिकरण अनुरोध पत्र (HINDI PRE-AUTH FORM)
----------------------------------------------------------------------
अनुरोध आईडी (Request ID): HINDI-REQ-2026-9912
प्रस्तुति तिथि (Submission Date): 2026-08-15
प्रारूप (Source Format): scanned_image

मरीज़ का विवरण (PATIENT DETAILS)
--------------------------------
मरीज़ का नाम (Patient Name): रमेश कुमार शर्मा (Ramesh Kumar Sharma)
आयु (Age): 48
लिंग (Gender): पुरुष (Male)
पॉलिसी संख्या (Policy Number): POL-HINDI-882190

पॉलिसी विवरण (POLICY DETAILS)
-----------------------------
योजना का प्रकार (Plan Type): व्यक्तिगत (Individual)
बीमा राशि (Sum Insured): 500000
पॉलिसी प्रारंभ तिथि (Policy Start Date): 2024-01-10
सह-भुगतान (Co-Pay): 0.00%

अस्पताल एवं नैदानिक विवरण (HOSPITAL & CLINICAL DETAILS)
------------------------------------------------------
अस्पताल का नाम (Hospital Name): अपोलो इंद्रप्रस्थ अस्पताल, नई दिल्ली
शहर (City): नई दिल्ली (New Delhi)
नेटवर्क स्थिति (Network Tier): कैशलेस नेटवर्क (cashless_network)
आईसीडी-10 कोड (ICD-10 Code): H26.9
निदान (Diagnosis): मोतियाबिंद (Cataract, unspecified)
पूर्व-मौजूदा बीमारी (Pre-Existing Condition): नहीं (No)
प्रक्रिया कोड (Procedure Code): CPT-66984
प्रक्रिया का नाम (Procedure): फेकोइमल्सीफिकेशन (Phacoemulsification with IOL)
प्रवेश का प्रकार (Admission Type): नियोजित (Planned)
प्रवेश तिथि (Admission Date): 2026-08-16

अनुमानित लागत विवरण (ESTIMATED COST BREAKDOWN)
---------------------------------------------
  कमरे का किराया (Room Rent): INR 15000.00 (room_rent)
  सर्जन शुल्क (Surgeon Fee): INR 20000.00 (surgeon_fee)
  दवाइयां (Pharmacy): INR 5000.00 (pharmacy)
  उपभोग्य वस्तुएं (Consumables): INR 5000.00 (consumables)
कुल अनुमानित राशि (Total Amount): INR 45000.00
"""
    # 1. Save TXT
    txt_path = base_dir / "txt" / "adversarial_unexpected_language_hindi.txt"
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(hindi_text)
        
    # 2. Save Image (PNG)
    img_path = base_dir / "images" / "adversarial_unexpected_language_hindi.png"
    img = Image.new("RGB", (850, 1100), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    y = 30
    for line in hindi_text.splitlines():
        draw.text((40, y), line, fill=(20, 20, 20))
        y += 22
    img.info["text"] = hindi_text
    img.save(str(img_path), format="PNG")
    with open(img_path.with_suffix(".txt"), "w", encoding="utf-8") as f:
        f.write(hindi_text)


if __name__ == "__main__":
    main()
