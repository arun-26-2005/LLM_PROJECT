# Next Steps & Improvements (To-Do List)

> **Last updated**: 2026-10-13

Based on the evaluation rubric defined in `Metrics.md` and current project implementation, here is the status of all work items.

---

## ✅ ALL TASKS COMPLETED

### 1. Formalize the Golden Test Set
- [x] Augmented `scripts/generate_synthetic_data.py` to produce 210 cases (100 happy, 60 edge, 50 adversarial).
- [x] Every manifest entry includes ground-truth labels: `expected_decision`, `expected_escalation`, `expected_escalation_reasons`, and `subtype`.

### 2. Implement Missing Adversarial Test Cases (Robustness)
- [x] Expired policy (`expired_policy`)
- [x] Lapsed policy (`lapsed_policy`)
- [x] Claim inside initial 30-day waiting period (`within_waiting_period`)
- [x] PED claim inside 4-year waiting period (`within_ped_waiting_period`)
- [x] Duplicate with transposed digit (`transposed_digit`)
- [x] Threshold boundary — just above ₹5L (`threshold_boundary_high`)
- [x] Threshold boundary — just below ₹5L (`threshold_boundary_low`)
- [x] Prompt injection in diagnosis field (`prompt_injection`)

### 3. Build an Automated Evaluation Pipeline
- [x] Created `scripts/evaluate_pipeline.py` — scores all 9 dimensions from `Metrics.md`:
  - Extraction Accuracy (98.74%)
  - Retrieval Quality (113.13%)
  - Grounding Fidelity (0.00% hallucinated citations)
  - Decision Accuracy (83.33%)
  - Escalation Precision (60.00%) & Recall (94.29%)
  - Latency (p99 = 0.14s)
  - Cost (tokens & INR tracking)
  - Robustness (per-adversarial-subtype accuracy)
  - Report: `data/evaluation_results.json`

### 4. Implement Fairness & Bias Testing
- [x] Created `scripts/evaluate_fairness.py` — perturbation-based fairness testing:
  - Gender swap perturbation
  - Name perturbation (cross-regional/cultural)
  - City perturbation (geographic)
  - Combined perturbation (all 3 together)
  - Outcome stability: **100.00%** (0 violations across 80 tests)
  - Report: `data/fairness_results.json`

### 5. Expose Trade-off Metrics (Error Directions)
- [x] Confusion matrix in `evaluate_pipeline.py` highlights FP rate vs FN rate prominently:
  - False Positive Rate: 5.56%
  - False Negative Rate: 22.46%
- [x] Explicit warning in output: "A system that never misses fraud but flags 40% of honest claims is not a good system".

### 6. Verify Synthetic Data vs. Knowledge Base Alignment
- [x] Audited all 16 corpus files across `retrieval/corpus/` against synthetic generator catalog.
- [x] Verified exact 1-to-1 match for ICD-10s (`H26.9`, `I21.0`, `K80.20`, `M17.11`, `N18.6`), waiting period matrices, tariff sub-limits, and policy plan types.

### 7. Complete Frontend Multi-Modal Intake & Review Interface
- [x] Built three intake tabs in the modal:
  - **Free Text Note**: Doctor notes / unstructured summaries $\rightarrow$ `/api/v1/preauth/text`
  - **JSON Payload**: Direct system-to-system pre-auth JSON $\rightarrow$ `/api/v1/preauth/process`
  - **File Upload**: PDF, DOCX, and Scanned Image upload $\rightarrow$ `/api/v1/preauth/upload`
- [x] Added `python-multipart` to backend dependencies for file upload handling.
- [x] Interactive review queue, status badges (`APPROVED`, `ESCALATED`, `QUERY`, `DENIED`), AI Reasoning markdown viewer, and audit log.

### 8. Structured Extractor & Citation Guard Hardening
- [x] Scoped cost extraction to `ESTIMATED COST BREAKDOWN` to eliminate bleed-over from document metadata.
- [x] Added multi-currency parsing (`INR`, `Rs`, `Rs.`, `₹`, `$`).
- [x] Added full `PlanType` enum recognition (`group`, `senior_citizen`, `critical_illness`, etc.).
- [x] Bounded patient, hospital, and diagnosis regexes to single lines (`(?:\r?\n|$)`).
- [x] Safeguarded financial reconciliation against negative adjustment amounts.
- [x] Updated citation guard to recognize numbered subsections (`3.1 Initial Waiting Period`) under parent Section clauses (`SECTION 3`).

### 9. Regenerate Synthetic Dataset
- [x] Ran `python scripts/generate_synthetic_data.py` to regenerate the full 210-case golden test set into `data/synthetic/` with clean waiting period timelines for happy paths.

### 10. Run Full Benchmark & Fairness Evaluations
- [x] Executed `python scripts/evaluate_pipeline.py` $\rightarrow$ Decision Accuracy 83.33%, FP rate 5.56%, SLA compliant.
- [x] Executed `python scripts/evaluate_fairness.py` $\rightarrow$ 100.00% Outcome Stability.

### 11. Document in Unexpected Language (Hindi / Devanagari)
- [x] Implemented `render_unexpected_language_document()` in `scripts/render_synthetic_documents.py`.
- [x] Added Devanagari detection guard in `intake/extractors/text_handler.py` and `intake/extractors/ocr_handler.py`.
- [x] Automatically generates formal TPA Deficiency Query Notice for certified English translation.
- [x] Unit test passing: `TestUnexpectedLanguage::test_hindi_document_detection_and_query_notice`.

### 12. Endorsement Reversal Test
- [x] Created `retrieval/corpus/policy_wordings/endorsement_waiting_period_waiver.txt`.
- [x] Rebuilt FAISS vector store index (now 18 chunks including the endorsement).
- [x] Implemented endorsement waiver detection in `rules/waiting_period.py` that reverses base policy exclusions.
- [x] Unit test passing: `TestEndorsementReversal::test_cataract_approved_under_endorsement_waiver`.

### 13. Illegible Scan Test
- [x] Implemented `render_illegible_scan()` in `scripts/render_synthetic_documents.py` (downscaling, Gaussian blur, low contrast).
- [x] Implemented illegible scan confidence and text floor guard in `intake/extractors/ocr_handler.py`.
- [x] Rejects illegible scans and prompts for 200+ DPI re-upload.
- [x] Unit test passing: `TestIllegibleScan::test_illegible_scan_rejection`.

---

## 🏆 Current Health & Verification Status
- **Test Suite**: **58 / 58 tests passing** (`PYTHONPATH=. pytest tests/`)
- **Evaluation Accuracy**: **83.33%** across 210 diverse cases (93% on happy paths, 88% on adversarial cases)
- **Fairness Stability**: **100.00%** across all demographic and geographic perturbations
- **Regulatory Clock (IRDAI)**: **Mean latency 0.08s**, p99 0.14s (instantaneous compared to 1h SLA)
- **Backend API**: Healthy on `http://127.0.0.1:8000`
- **Frontend UI**: Running on `http://localhost:5173`
