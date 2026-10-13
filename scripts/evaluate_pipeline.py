import sys
import os
import json
import traceback
from collections import defaultdict
import numpy as np

# Add project root to Python path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from intake import process_intake
from orchestration.graph import run_pipeline


def evaluate():
    """Runs automated evaluation across all 9 dimensions defined in Metrics.md."""
    manifest_path = os.path.join(PROJECT_ROOT, "data", "synthetic", "manifest.json")
    results_path = os.path.join(PROJECT_ROOT, "data", "evaluation_results.json")
    
    if not os.path.exists(manifest_path):
        print(f"Manifest file not found: {manifest_path}")
        return
        
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
        
    results = []
    
    # 1. Extraction metrics
    fields_extracted = 0
    fields_total = 0
    
    # 2. Retrieval metrics
    retrieval_successes = 0
    
    # 3. Grounding metrics
    total_citations = 0
    hallucinated_citations = 0
    
    # 4. Decision metrics (Confusion matrix)
    TP, TN, FP, FN = 0, 0, 0, 0
    
    # 5. Escalation metrics
    esc_TP, esc_TN, esc_FP, esc_FN = 0, 0, 0, 0
    
    # 6. Latency
    latencies = []
    
    # 7. Cost
    total_cost = 0.0
    
    # 8. Robustness
    robustness_metrics = defaultdict(lambda: {"correct": 0, "total": 0})
    category_metrics = defaultdict(lambda: {"correct": 0, "total": 0})
    
    print(f"[*] Starting evaluation on {len(manifest)} test cases...")
    
    for case in manifest:
        case_id = case.get("id", case.get("request_id", "unknown"))
        expected_decision = case.get("expected_decision", "APPROVE")
        expected_escalation = case.get("expected_escalation", False)
        category = case.get("category", "unknown")
        subtype = case.get("subtype", case.get("adv_type", "none"))
        file_path = case.get("path")
        
        if not file_path or not os.path.exists(file_path):
            continue
            
        with open(file_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
            
        try:
            # 1. Intake Processing
            intake_res = process_intake(payload, format_override="json")
            
            if payload:
                # Count major schema sections
                fields_total += len(payload)
                if intake_res.is_success:
                    fields_extracted += len(payload)
                else:
                    fields_extracted += max(0, len(payload) - len(intake_res.validation_errors))
            
            if not intake_res.is_success:
                # Payload was rejected at intake validation gate
                rec = "DENY"
                needs_escalation = False
                latency = 0.005
                cost = 0.0
                retrieved = []
                hallucinated = 0
                tot_cits = 0
                result_dict = {
                    "recommendation": "RECOMMEND_DENY",
                    "needs_escalation": False,
                    "validation_errors": intake_res.validation_errors,
                }
            else:
                intake_dict = intake_res.model_dump()
                pipeline_result = run_pipeline(intake_dict)
                result_dict = pipeline_result if isinstance(pipeline_result, dict) else pipeline_result.model_dump()
                
                raw_rec = result_dict.get("recommendation", "")
                if hasattr(raw_rec, "value"):
                    raw_rec = raw_rec.value
                raw_rec_str = str(raw_rec).upper()
                
                needs_escalation = bool(result_dict.get("needs_escalation", False))
                
                if "AUTHORISE" in raw_rec_str or "APPROVE" in raw_rec_str:
                    rec = "APPROVE"
                elif "DENY" in raw_rec_str:
                    rec = "DENY"
                elif "QUERY" in raw_rec_str:
                    rec = "QUERY"
                else:
                    rec = raw_rec_str
                    
                latency = result_dict.get("total_latency", 0.0)
                cost = result_dict.get("llm_cost_inr", 0.0)
                retrieved = result_dict.get("retrieved_clauses", [])
                hallucinated_list = result_dict.get("hallucinated_citations", [])
                hallucinated = len(hallucinated_list) if isinstance(hallucinated_list, list) else int(hallucinated_list or 0)
                tot_cits = len(retrieved)

            # 2. Retrieval Check
            if retrieved:
                retrieval_successes += 1
                
            # 3. Grounding Check
            hallucinated_citations += hallucinated
            total_citations += max(1, tot_cits)
            
            # 4. Decision Correctness Check
            expected_dec_str = str(expected_decision).upper()
            
            if expected_dec_str == "ESCALATE":
                # For cases expected to escalate (e.g. non-network hospital, high-value, PED)
                is_correct = needs_escalation
            elif expected_dec_str == "APPROVE":
                is_correct = (rec == "APPROVE")
            elif expected_dec_str == "DENY":
                is_correct = (rec == "DENY")
            else:
                is_correct = (rec == expected_dec_str)
                
            # Decision Confusion Matrix (Approve vs Deny)
            if rec == "APPROVE" and expected_dec_str == "APPROVE":
                TP += 1
            elif rec == "DENY" and expected_dec_str in ["DENY", "ESCALATE"]:
                TN += 1
            elif rec == "APPROVE" and expected_dec_str in ["DENY", "ESCALATE"]:
                FP += 1  # False positive: approved fraud/ineligible claim
            elif rec == "DENY" and expected_dec_str == "APPROVE":
                FN += 1  # False negative: denied honest claim
                
            # 5. Escalation Confusion Matrix
            if needs_escalation and expected_escalation:
                esc_TP += 1
            elif not needs_escalation and not expected_escalation:
                esc_TN += 1
            elif needs_escalation and not expected_escalation:
                esc_FP += 1
            elif not needs_escalation and expected_escalation:
                esc_FN += 1
                
            # 6. Latency
            latencies.append(latency)
            
            # 7. Cost
            total_cost += cost
            
            # 8. Robustness by Category & Subtype
            robustness_metrics[subtype]["total"] += 1
            category_metrics[category]["total"] += 1
            if is_correct:
                robustness_metrics[subtype]["correct"] += 1
                category_metrics[category]["correct"] += 1
                
            results.append({
                "case_id": case_id,
                "category": category,
                "subtype": subtype,
                "expected_decision": expected_decision,
                "actual_recommendation": rec,
                "needs_escalation": needs_escalation,
                "is_correct": is_correct,
                "latency_s": round(latency, 3),
            })
            
        except Exception as e:
            print(f"[!] Error evaluating case {case_id}: {e}")
            traceback.print_exc()
            results.append({
                "case_id": case_id,
                "status": "error",
                "error": str(e),
            })
            
    # Compute aggregate metrics
    total_cases = len(manifest)
    evaluated_cases = len(results)
    
    if evaluated_cases == 0:
        print("[!] No cases evaluated successfully.")
        return
        
    extraction_accuracy = fields_extracted / max(1, fields_total)
    retrieval_quality = retrieval_successes / max(1, len([r for r in results if r.get("category") != "adversarial"]))
    hallucination_rate = hallucinated_citations / max(1, total_citations)
    
    total_decisions = TP + TN + FP + FN
    decision_accuracy = (TP + TN) / max(1, total_decisions)
    
    esc_precision = esc_TP / max(1, esc_TP + esc_FP)
    esc_recall = esc_TP / max(1, esc_TP + esc_FN)
    
    mean_latency = float(np.mean(latencies)) if latencies else 0.0
    p50 = float(np.percentile(latencies, 50)) if latencies else 0.0
    p95 = float(np.percentile(latencies, 95)) if latencies else 0.0
    p99 = float(np.percentile(latencies, 99)) if latencies else 0.0
    
    avg_cost = total_cost / max(1, evaluated_cases)
    
    for k in robustness_metrics:
        robustness_metrics[k]["accuracy"] = robustness_metrics[k]["correct"] / max(1, robustness_metrics[k]["total"])
    for k in category_metrics:
        category_metrics[k]["accuracy"] = category_metrics[k]["correct"] / max(1, category_metrics[k]["total"])
        
    fairness_note = "Detailed demographic parity and equal opportunity metrics available in data/fairness_results.json."
    
    # 9. Format Report Output
    report = {
        "summary": {
            "evaluated_cases": evaluated_cases,
            "total_cases": total_cases,
            "overall_accuracy": decision_accuracy,
        },
        "dimensions": {
            "1_extraction": {"accuracy": round(extraction_accuracy, 4)},
            "2_retrieval": {"recall_proxy": round(retrieval_quality, 4)},
            "3_grounding": {"hallucination_rate": round(hallucination_rate, 4)},
            "4_decision": {
                "accuracy": round(decision_accuracy, 4),
                "confusion_matrix": {"TP": TP, "TN": TN, "FP": FP, "FN": FN},
                "fp_rate": round(FP / max(1, FP + TN), 4),
                "fn_rate": round(FN / max(1, TP + FN), 4),
            },
            "5_escalation": {
                "precision": round(esc_precision, 4),
                "recall": round(esc_recall, 4),
                "confusion_matrix": {"esc_TP": esc_TP, "esc_TN": esc_TN, "esc_FP": esc_FP, "esc_FN": esc_FN},
            },
            "6_latency": {
                "mean_seconds": round(mean_latency, 3),
                "p50_seconds": round(p50, 3),
                "p95_seconds": round(p95, 3),
                "p99_seconds": round(p99, 3),
                "sla_compliant": bool(p99 < 3600),
            },
            "7_cost": {
                "total_inr": round(total_cost, 2),
                "avg_per_case_inr": round(avg_cost, 4),
            },
            "8_robustness": {
                "by_subtype": dict(robustness_metrics),
                "by_category": dict(category_metrics),
            },
            "9_fairness": fairness_note,
        },
        "case_results": results,
    }
    
    os.makedirs(os.path.dirname(results_path), exist_ok=True)
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
        
    # Print Formatted Console Dashboard
    print("\n" + "=" * 65)
    print("           A1 CASHLESS PRE-AUTH: 9-DIMENSION BENCHMARK")
    print("=" * 65)
    print(f"Total Cases Evaluated: {evaluated_cases} / {total_cases}")
    print("\n1. Extraction Accuracy  : {:.2%}".format(extraction_accuracy))
    print("2. Retrieval Quality     : {:.2%}".format(retrieval_quality))
    print("3. Grounding Fidelity    : {:.2%} hallucination rate".format(hallucination_rate))
    print("4. Decision Accuracy     : {:.2%}".format(decision_accuracy))
    print(f"   Confusion Matrix      : TP={TP} | TN={TN} | FP={FP} | FN={FN}")
    print("5. Escalation Precision  : {:.2%} | Recall: {:.2%}".format(esc_precision, esc_recall))
    print("6. Latency Profile       : Mean={:.2f}s | p50={:.2f}s | p95={:.2f}s | p99={:.2f}s".format(
        mean_latency, p50, p95, p99
    ))
    print("   SLA Status            : {}".format("PASSED (< 1h IRDAI limit)" if p99 < 3600 else "FAILED"))
    print("7. Processing Cost       : Total ₹{:.2f} | Average ₹{:.4f}/case".format(total_cost, avg_cost))
    
    print("\n8. Robustness Breakdown by Category:")
    for cat, stats in category_metrics.items():
        print(f"   • {cat:<15}: {stats['accuracy']:.1%} ({stats['correct']}/{stats['total']})")
        
    print("\n   Robustness Breakdown by Adversarial/Edge Subtype:")
    for sub, stats in robustness_metrics.items():
        if sub != "happy_path":
            print(f"   • {sub:<25}: {stats['accuracy']:.1%} ({stats['correct']}/{stats['total']})")
            
    print("\n9. Fairness & Non-Discrimination:")
    print(f"   {fairness_note}")
    
    print("\n" + "-" * 65)
    print("Trade-Off Highlight (Error Direction Analysis):")
    fp_rate = FP / max(1, FP + TN)
    fn_rate = FN / max(1, TP + FN)
    print(f"  • False Positive Rate (Ineligible claim approved) : {fp_rate:.2%}")
    print(f"  • False Negative Rate (Legitimate claim denied)   : {fn_rate:.2%}")
    print("  * Target: Keep FP near 0% to prevent financial loss, while keeping FN low to protect patients.")
    print("=" * 65)
    print(f"[+] Full JSON evaluation report saved to: {results_path}\n")


if __name__ == "__main__":
    evaluate()
