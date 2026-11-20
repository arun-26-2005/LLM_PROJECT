# A1 Cashless Health Insurance Pre-Authorisation Agent

> **Course:** INT450 — Large Language Models and Agentic AI (Capstone Project)  
> **Institution:** School of Computing, SASTRA Deemed to be University, Thanjavur  
> **Team:** Arunkumar D (127003027) · Arunagiri A (127003026) · Mohankumar S (127003157)  
> **Guide:** Dr. K. Ramkumar

An end-to-end **Dual-Track Neuro-Symbolic Agentic AI system** that automates pre-authorisation recommendations for cashless health insurance hospitalisations under IRDAI regulations. The system processes multi-format hospital documents, runs parallel deterministic rules and LLM-based clinical reasoning tracks, reconciles them through a consensus arbiter, and surfaces a grounded recommendation to a human reviewer — all within **~1.2 seconds** against IRDAI's 1-hour statutory SLA.

---

## Architecture

```
  ┌─────────────────────────────────────────────────────────────────┐
  │   Hospital Intake (JSON · PDF · Scanned Image · DOCX · Text)   │
  └──────────────────────────┬──────────────────────────────────────┘
                             ▼
              ┌──────────────────────────────┐
              │  MIME Validation · PII Scrub  │
              │  Pydantic Schema Extraction   │
              └──────────────┬───────────────┘
                   ┌─────────┴─────────┐
                   ▼                   ▼
     ┌──────────────────┐   ┌──────────────────────┐
     │  Track 1: Rules  │   │  Track 2: Clinical   │
     │  (Deterministic)  │   │  LLM + RAG           │
     │                  │   │                      │
     │ • Policy check   │   │ • FAISS retrieval    │
     │ • Waiting period │   │ • Prompt-injection   │
     │ • Sub-limits     │   │   pre-screen         │
     │ • Co-pay math    │   │ • LLM reasoning      │
     │   (Decimal)      │   │   (Groq / OpenAI)    │
     └────────┬─────────┘   └──────────┬───────────┘
              └─────────┬──────────────┘
                        ▼
         ┌──────────────────────────────┐
         │   Consensus Arbiter          │
         │   (Label + Amount Mismatch)  │
         ├──────────────────────────────┤
         │   Citation Guard             │
         │   (Hallucination Purge)      │
         ├──────────────────────────────┤
         │   Escalation Gate            │
         │   (8 Risk Triggers)          │
         └──────────────┬───────────────┘
                        ▼
         ┌──────────────────────────────┐
         │  RECOMMEND_APPROVE / PARTIAL │
         │  RECOMMEND_REJECT / ESCALATE │
         └──────────────┬───────────────┘
                        ▼
         ┌──────────────────────────────┐
         │  SQLite + SHA-256 Audit Log  │
         │  Human Reviewer Dashboard    │
         └──────────────────────────────┘
```

**Key idea:** LLMs are good at clinical reasoning but bad at arithmetic. The rules engine is exact but can't assess medical necessity. Running them independently and cross-checking via the consensus arbiter gives the benefits of both without the risks of either.

---

## Quick Start

### Prerequisites

- Python 3.9+
- Node.js 18+ (for the frontend)
- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) (optional, for scanned documents)

### Installation

```bash
git clone https://github.com/arun-26-2005/LLM_PROJECT.git
cd LLM_PROJECT

# Backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# (Optional) Tesseract for OCR
brew install tesseract          # macOS
# sudo apt-get install tesseract-ocr  # Ubuntu

# Frontend
cd frontend && npm install && cd ..
```

### Environment

Create a `.env` file in the project root:

```env
OPENAI_API_KEY="your-api-key"
OPENAI_BASE_URL="https://api.groq.com/openai/v1"
LLM_MODEL="openai/gpt-oss-120b"
LLM_MAX_TOKENS="4096"
LLM_EXECUTION_MODE="LIVE_WITH_FALLBACK"   # LIVE_REQUIRED | FALLBACK_ONLY | LIVE_WITH_FALLBACK
```

### Run

```bash
# Start the API server
uvicorn main:app --reload --port 8000

# In another terminal — start the reviewer dashboard
cd frontend && npm run dev
```

The API docs are at `http://localhost:8000/docs` and the reviewer dashboard at `http://localhost:5173`.

### Generate Synthetic Data & Run Tests

```bash
# Generate test data
python scripts/generate_synthetic_data.py
python scripts/render_synthetic_documents.py

# Run the full test suite (98 tests)
python -m pytest tests/ -v
```

---

## Project Structure

```
├── main.py                    FastAPI application (API + reviewer endpoints)
│
├── intake/                    Multi-format document ingestion
│   ├── extractors/            Format handlers (JSON, PDF, OCR, DOCX, text)
│   ├── structured_extractor.py   Regex + heuristic field extraction
│   ├── pii_scrubber.py        PII redaction filter for all loggers
│   └── cli.py                 Interactive CLI with clarification workflow
│
├── schemas/                   Pydantic v2 domain models
│   └── pre_auth_request.py    14 models, 8 enums, cross-field validators
│
├── rules/                     Deterministic symbolic rules engine
│   ├── engine.py              Main adjudication orchestrator
│   ├── policy_validity.py     Active/lapsed/moratorium checks
│   ├── waiting_period.py      24/48-month specific + 60-month statutory
│   ├── sub_limits.py          Room rent, ICU caps, proportionate deductions
│   ├── copay_deductible.py    Co-pay tiers and mandatory deductibles
│   ├── exclusions.py          Permanent and conditional exclusion rules
│   └── fairness.py            Demographic counterfactual stability checks
│
├── retrieval/                 Semantic search (RAG)
│   ├── vector_store.py        FAISS index with sentence-transformers
│   ├── embedder.py            all-MiniLM-L6-v2 embedding wrapper
│   └── corpus/                Policy documents & IRDAI circulars
│
├── llm/                       LLM provider abstraction
│   ├── openai_provider.py     OpenAI-compatible client (Groq, OpenAI)
│   ├── config.py              Execution modes (live / fallback / hybrid)
│   └── response_parser.py     Structured output parsing
│
├── orchestration/             LangGraph agent pipeline
│   ├── graph.py               State machine with parallel fan-out/fan-in
│   ├── nodes.py               11 pipeline nodes (intake → recommendation)
│   ├── state.py               PipelineState TypedDict
│   └── metrics.py             Latency and cost tracking
│
├── persistence/               Data durability & audit
│   ├── database.py            SQLite (WAL mode, FK enforcement)
│   ├── repository.py          Claim CRUD operations
│   └── audit_chain.py         SHA-256 hash-chained tamper-evident log
│
├── frontend/                  React 19 + TypeScript + Vite + Tailwind
│   └── src/App.tsx            Reviewer dashboard (dual-track view, RBAC)
│
├── tests/                     98 unit + integration tests
├── scripts/                   Data generation, evaluation, ablation
├── synthetic_evaluation/      210-case benchmark dataset with ground truth
├── figures/                   Ablation study visualisations
├── data/                      Runtime data (claims DB, evaluation results)
│
├── Guardrails.md              IRDAI governance guardrails specification
├── Metrics.md                 Evaluation rubric and required metrics
└── requirements.txt           Python dependencies
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/preauth/process` | Process a JSON pre-auth request |
| `POST` | `/api/v1/preauth/upload` | Process a file upload (PDF / image / DOCX) |
| `POST` | `/api/v1/preauth/text` | Process a free-text request |
| `GET` | `/api/v1/preauth/history` | Retrieve processed claim history |
| `DELETE` | `/api/v1/preauth/history` | Clear claim history |
| `GET` | `/api/v1/preauth/audit/verify` | Verify SHA-256 audit chain integrity |
| `GET` | `/api/v1/preauth/audit/anchor` | Export external anchor for audit trail |
| `POST` | `/api/v1/preauth/{id}/review/approve` | Human reviewer approval |
| `POST` | `/api/v1/preauth/{id}/review/reject` | Human reviewer rejection |
| `POST` | `/api/v1/preauth/{id}/review/override` | Human reviewer override |
| `POST` | `/api/v1/preauth/{id}/review/request-docs` | Request additional documents |

---

## Governance Guardrails

These are the non-negotiable design constraints enforced throughout the system, aligned with IRDAI regulations and the DPDP Act 2023. See [`Guardrails.md`](Guardrails.md) for the full specification.

| # | Guardrail | How It's Enforced |
|---|-----------|-------------------|
| 1 | **Recommend, never decide** | All outputs use `RECOMMEND_*` prefix; no auto-approval/rejection |
| 2 | **Grounded output only** | Citation Guard (Node 7) strips any citation not in the FAISS corpus |
| 3 | **Synthetic data only** | 100% synthetic dataset; PII redaction filter on all loggers |
| 4 | **Deployment boundary** | Local embeddings; modular LLM swap for data residency compliance |
| 5 | **Fairness** | 0 violations across 80 demographic counterfactual perturbations |
| 6 | **Live regulatory citations** | Encodes IRDAI Master Circular 2024, ROHINI guidelines |
| 7 | **Human-in-the-loop** | 8 automatic escalation triggers; 100% escalation recall |

---

## Escalation Triggers

The escalation gate intercepts high-risk cases and routes them for mandatory human review:

| Trigger | Condition |
|---------|-----------|
| **0** | Track 1 ↔ Track 2 label or amount divergence (>5% and >₹100) |
| **1** | High financial exposure (approved amount > ₹5,00,000) |
| **2** | Non-network hospital or fraud risk indicators |
| **2.5** | Prompt-injection keywords detected in uploaded documents |
| **2.7** | Citation Guard found zero valid retrievals |
| **3** | Active pre-existing disease with uncertain disclosure |

---

## Evaluation Results

Benchmarked on a 210-case synthetic dataset (see [`Metrics.md`](Metrics.md) for the rubric):

| Metric | Value |
|--------|-------|
| Composite Decision Correctness | **98.10%** |
| Escalation Recall | **100.0%** (33/33) |
| Unsafe Auto-Approval Rate | **0.00%** |
| Recommendation False Positive Rate | **1.39%** |
| Hallucinated Citation Rate | **0.00%** |
| Mean Processing Latency | **1.24 s** (vs. 1-hour IRDAI SLA) |
| Cost per Case (live LLM) | **₹0.22** |
| Demographic Fairness | **100.0%** stability (0/80 violations) |
| Test Suite | **98/98 passing** |

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| **Orchestration** | LangGraph (state machine with parallel fan-out/fan-in) |
| **LLM** | OpenAI-compatible API (Groq / OpenAI) |
| **Embeddings** | sentence-transformers (`all-MiniLM-L6-v2`) |
| **Vector Store** | FAISS (CPU) |
| **Rules Engine** | Python `Decimal` arithmetic, custom policy modules |
| **Schema** | Pydantic v2 (14 models, 8 enums, cross-field validators) |
| **Backend** | FastAPI + Uvicorn |
| **Frontend** | React 19, TypeScript, Vite, Tailwind CSS |
| **Persistence** | SQLite (WAL mode) + SHA-256 hash-chained audit log |
| **OCR** | Tesseract 5.x via pytesseract |
| **Testing** | pytest (98 tests) |

---

## License

Academic project — developed for INT450 capstone at SASTRA University.
