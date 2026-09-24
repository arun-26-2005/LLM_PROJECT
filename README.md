# A1 Cashless Health Insurance — Pre-Authorisation Intake System

A multi-format document intake pipeline for processing cashless health insurance pre-authorisation requests in the Indian healthcare context. The system accepts documents in **6 different formats**, extracts structured patient/policy/clinical data using regex-based parsing, validates it against strict Pydantic schemas, and produces machine-readable output for downstream decisioning.

## 🏗️ Architecture

```
                    ┌──────────────────────────────────────────────────┐
                    │              INPUT SOURCES                       │
                    │  JSON │ PDF │ Scanned PDF │ Image │ DOCX │ Text  │
                    └────────────────────┬─────────────────────────────┘
                                         │
                                         ▼
                    ┌──────────────────────────────────────────────────┐
                    │           FORMAT DETECTION (auto-sniff)          │
                    │  Magic bytes · file extension · content sniffing │
                    └────────────────────┬─────────────────────────────┘
                                         │
            ┌────────┬────────┬──────────┼──────────┬─────────┐
            ▼        ▼        ▼          ▼          ▼         ▼
        ┌──────┐ ┌──────┐ ┌────────┐ ┌───────┐ ┌──────┐ ┌──────┐
        │ JSON │ │ PDF  │ │Scanned │ │ Image │ │ DOCX │ │ Text │
        │Parser│ │PyPDF │ │  OCR   │ │  OCR  │ │python│ │Reader│
        └──┬───┘ └──┬───┘ └───┬────┘ └───┬───┘ └──┬───┘ └──┬───┘
           │        │         │           │        │        │
           │        └────┬────┴───────────┴────────┴────────┘
           │             ▼
           │    ┌──────────────────────────────────────┐
           │    │     STRUCTURED EXTRACTION ENGINE      │
           │    │  Regex patterns · field inference ·   │
           │    │  confidence scoring · cost parsing    │
           │    └─────────────────┬────────────────────┘
           │                      │
           └──────────┬───────────┘
                      ▼
           ┌──────────────────────────────────────┐
           │      PYDANTIC v2 SCHEMA VALIDATION    │
           │  PreAuthRequest · Patient · Policy ·  │
           │  Hospital · Diagnosis · Procedure ·   │
           │  CostEstimate (14 models + 8 enums)   │
           └─────────────────┬────────────────────┘
                             ▼
           ┌──────────────────────────────────────┐
           │          IntakeResult OUTPUT           │
           │  ✓ Validated request · confidence ·   │
           │  narrative summary · missing fields · │
           │  TPA query notice · clarification Qs  │
           └───────────────────────────────────────┘
```

## 📂 Project Structure

```
LLM_Project/
├── schemas/                          # Pydantic v2 data models (single source of truth)
│   ├── __init__.py                   # Public API — re-exports all types
│   └── pre_auth_request.py           # 8 enums, 7 sub-models, PreAuthRequest root model
│
├── intake/                           # Multi-format ingestion & extraction pipeline
│   ├── __init__.py                   # Main entry-point: process_intake(), detect_format()
│   ├── models.py                     # IntakeResult — unified pipeline output model
│   ├── cli.py                        # Interactive CLI with menu, clarification, TPA query
│   ├── structured_extractor.py       # Core regex+heuristic extraction engine
│   ├── narrative_generator.py        # Human-readable summary generator
│   ├── query_generator.py            # TPA/IRDAI formal query notice generator
│   ├── interactive_clarifier.py      # Interactive field-by-field clarification workflow
│   └── extractors/                   # Format-specific document handlers
│       ├── json_handler.py           # Direct Pydantic validation for JSON payloads
│       ├── pdf_handler.py            # Digital PDF text extraction (pypdf)
│       ├── ocr_handler.py            # Scanned PDF / Image OCR (pytesseract + Pillow)
│       ├── docx_handler.py           # Word document extraction (python-docx)
│       └── text_handler.py           # Plain text / free-form input
│
├── scripts/                          # Data generation & rendering utilities
│   ├── generate_synthetic_data.py    # Generates 220 synthetic pre-auth JSON records
│   └── render_synthetic_documents.py # Renders JSON → PDF, DOCX, PNG, TXT for testing
│
├── tests/                            # Automated test suite
│   └── test_intake.py                # Unit + integration tests for all 6 formats
│
├── data/                             # Generated datasets (gitignored)
│   ├── synthetic/                    # Raw JSON records (valid/ + invalid/ + manifest)
│   └── synthetic_docs/               # Rendered documents (pdf/ images/ docx/ txt/)
│
├── A1_Cashless_Preauth_Project_Plan.docx  # Original project plan document
├── requirements.txt                  # Python dependencies
├── .gitignore                        # Git ignore rules
└── README.md                         # This file
```

## 🚀 Quick Start

### Prerequisites

- **Python 3.10+**
- **Tesseract OCR** (optional, for scanned document processing)

### Installation

```bash
# Clone the repository
git clone https://github.com/<your-username>/LLM_PROJECT.git
cd LLM_PROJECT

# Create and activate virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate  # macOS/Linux
# .venv\Scripts\activate   # Windows

# Install dependencies
pip install -r requirements.txt

# (Optional) Install Tesseract for OCR support
# macOS:
brew install tesseract
# Ubuntu:
# sudo apt-get install tesseract-ocr
```

### Generate Synthetic Test Data

```bash
# Step 1: Generate 220 synthetic pre-auth JSON records
python scripts/generate_synthetic_data.py

# Step 2: Render them into PDF, DOCX, PNG, TXT formats for multi-format testing
python scripts/render_synthetic_documents.py
```

### Run the CLI

```bash
# Interactive menu mode
python -m intake.cli

# Auto-detect and process a file
python -m intake.cli data/synthetic_docs/pdf/valid_request_0001.pdf

# Force a specific format
python -m intake.cli data/synthetic/valid/request_0001.json -f 1

# Output as JSON
python -m intake.cli data/synthetic/valid/request_0001.json --json

# Interactive clarification for missing fields
python -m intake.cli data/synthetic_docs/txt/valid_request_0001.txt --clarify

# Generate formal TPA query notice
python -m intake.cli data/synthetic_docs/txt/valid_request_0001.txt --query
```

### Run Tests

```bash
# Ensure synthetic data exists first
python scripts/generate_synthetic_data.py
python scripts/render_synthetic_documents.py

# Run the full test suite
python -m pytest tests/ -v
# Or with unittest
python -m unittest tests.test_intake -v
```

## 📋 Supported Input Formats

| # | Format | Handler | Library | Notes |
|---|--------|---------|---------|-------|
| 1 | **JSON** | Direct schema validation | Pydantic v2 | 100% confidence if valid |
| 2 | **Digital PDF** | Text extraction → regex parsing | pypdf | Auto-fallback to OCR if no text |
| 3 | **Scanned PDF** | Page image extraction → OCR | pypdf + pytesseract | OCR confidence score tracked |
| 4 | **Image (JPEG/PNG)** | Image OCR | Pillow + pytesseract | Companion .txt fallback for testing |
| 5 | **DOCX** | Paragraph + table extraction | python-docx | Tables rendered as pipe-delimited rows |
| 6 | **Plain Text** | Direct regex parsing | Built-in | Handles both file and raw string input |

## 🏥 Schema Overview

The `PreAuthRequest` root model contains:

| Component | Key Fields | Validation |
|-----------|-----------|------------|
| **Patient** | full_name, age (0–120), gender, policy_number | Name length, age bounds |
| **Policy** | policy_number, plan_type, sum_insured, start_date, co_pay | Non-negative amounts, date formats |
| **Hospital** | name, city, network_tier, category | Enum validation |
| **Diagnosis** | ICD-10 code, description, pre_existing flag | ICD-10 format regex (e.g., `H26.9`) |
| **Procedure** | procedure_code, description, admission_type | Enum validation |
| **CostEstimate** | line_items[], total_amount | Total must reconcile with line items (±₹1 tolerance) |

### Cross-Field Validators

- `patient.policy_number` must match `policy.policy_number`
- `admission_date` must not be before `policy.policy_start_date`
- `cost_estimate.total_amount` must equal sum of `line_items` within ₹1

## 🧪 Synthetic Data

The generator creates **220 records** across three categories:

| Category | Count | Purpose |
|----------|-------|---------|
| **Happy Path** | 110 | Perfectly valid payloads for baseline testing |
| **Edge Cases** | 70 | Valid schema but challenging business conditions (non-network hospital, high co-pay, PED, near sum insured cap) |
| **Adversarial** | 40 | Intentionally invalid payloads (policy mismatch, backdated admission, cost reconciliation failure, invalid ICD-10) |

The data covers realistic Indian healthcare scenarios with 8 clinical diagnoses (cataract, STEMI, appendicitis, gallstones, knee replacement, pneumonia, ESRD, diabetes), 14 hospital chains, 12 cities, and 8 insurers.

## 🔧 Configuration

The system uses sensible defaults with no external configuration files required:

| Parameter | Default | Location |
|-----------|---------|----------|
| OCR text threshold | 30 characters | `intake/__init__.py` → `detect_format()` |
| Min text for scanned fallback | 20 characters | `intake/extractors/pdf_handler.py` |
| Default sum insured | ₹5,00,000 | `intake/structured_extractor.py` |
| Confidence penalty per inferred field | -8% | `intake/structured_extractor.py` |
| Cost reconciliation tolerance | ₹1.00 | `schemas/pre_auth_request.py` |

## 📄 License

This project is developed as part of the A1 Cashless Pre-Authorisation pipeline for educational and demonstration purposes.

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/your-feature`)
3. Generate test data and run tests before submitting
4. Ensure all existing tests pass (`python -m pytest tests/ -v`)
5. Submit a pull request
