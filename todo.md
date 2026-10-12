# Next Steps & Improvements (To-Do List)

> **Last updated**: 2026-10-12

Based on the evaluation rubric defined in `Metrics.md` and current project implementation, here is the status of all work items.

---

## ✅ COMPLETED

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
  - Extraction Accuracy (field-level precision/recall)
  - Retrieval Quality (non-empty clause check)
  - Grounding Fidelity (hallucinated-citation rate)
  - Decision Accuracy (confusion matrix with FP/FN trade-offs)
  - Escalation Precision (precision and recall)
  - Latency (mean, p50, p95, p99)
  - Cost (tokens and INR per transaction)
  - Robustness (per-adversarial-subtype accuracy)

### 4. Implement Fairness & Bias Testing
- [x] Created `scripts/evaluate_fairness.py` — perturbation-based fairness testing:
  - Gender swap perturbation
  - Name perturbation (cross-regional/cultural)
  - City perturbation (geographic)
  - Combined perturbation (all 3 together)
  - Outcome stability assertion (recommendation + total_approved)

### 5. Expose Trade-off Metrics (Error Directions)
- [x] Confusion matrix in `evaluate_pipeline.py` highlights FP rate vs FN rate prominently.
- [x] Explicit warning in output: "A system that never misses fraud but flags 40% of honest claims is not a good system".

### 6. Verify Synthetic Data vs. Knowledge Base Alignment
- [x] Audited all 15 corpus files across `retrieval/corpus/` against synthetic generator catalog.
- [x] Verified exact 1-to-1 match for ICD-10s (`H26.9`, `I21.0`, `K80.20`, `M17.11`, `N18.6`), waiting period matrices, tariff sub-limits, and policy plan types.

### 7. Complete Frontend Multi-Modal Intake & Review Interface
- [x] Built three intake tabs in the modal:
  - **Free Text Note**: Doctor notes / unstructured summaries $\rightarrow$ `/api/v1/preauth/text`
  - **JSON Payload**: Direct system-to-system pre-auth JSON $\rightarrow$ `/api/v1/preauth/process`
  - **File Upload**: PDF, DOCX, and Scanned Image upload $\rightarrow$ `/api/v1/preauth/upload`
- [x] Added `python-multipart` to backend dependencies for file upload handling.
- [x] Interactive review queue, status badges (`APPROVED`, `ESCALATED`, `QUERY`, `DENIED`), AI Reasoning markdown viewer, and audit log.
- [x] Fixed string interpolation syntax and Vite dev server compilation.

### 8. Structured Extractor & Citation Guard Hardening
- [x] Scoped cost extraction to `ESTIMATED COST BREAKDOWN` to eliminate bleed-over from document metadata (such as `Policy Number: POL-889169` or `Procedure Code: CPT-27447`).
- [x] Added multi-currency parsing (`INR`, `Rs`, `Rs.`, `₹`, `$`).
- [x] Added full `PlanType` enum recognition (`group`, `senior_citizen`, `critical_illness`, etc.).
- [x] Bounded patient, hospital, and diagnosis regexes to single lines (`(?:\r?\n|$)`).
- [x] Safeguarded financial reconciliation against negative adjustment amounts.
- [x] Updated citation guard in `orchestration/nodes.py` to recognize numbered subsections (`3.1 Initial Waiting Period`) under parent Section clauses (`SECTION 3`).
- [x] Full test suite green: **55/55 tests passing** in `pytest`.

---

## 🔲 REMAINING WORK

### 9. Regenerate Synthetic Dataset
- [ ] Run `python scripts/generate_synthetic_data.py` to regenerate the full 210-case golden test set into `data/synthetic/` with all new adversarial cases and manifest ground-truth labels.

### 10. Run Full Benchmark & Fairness Evaluations
- [ ] Execute `python scripts/evaluate_pipeline.py` to generate the complete 9-dimension report and `data/evaluation_results.json`.
- [ ] Execute `python scripts/evaluate_fairness.py` to run the 20-case $\times$ 4-perturbation suite and generate `data/fairness_results.json`.
- [ ] Verify results against target thresholds defined in `Metrics.md`.

### 11. Document in Unexpected Language (Hindi / Devanagari)
- [ ] Implement Hindi / Devanagari medical note generation and verify OCR handling in `render_synthetic_documents.py`.

### 12. Endorsement Reversal Test
- [ ] Add a conflicting endorsement document to `retrieval/corpus/` that overrides base policy terms, testing retrieval and reasoning priority.

### 13. Illegible Scan Test
- [ ] Implement an image degradation filter in `render_synthetic_documents.py` (Gaussian blur, compression artifacts, low DPI) to test OCR confidence scoring and rejection gates.
