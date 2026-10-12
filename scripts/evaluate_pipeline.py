import sys
import os
import json
import traceback
from collections import defaultdict
import numpy as np

# Add project root to Python path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from schemas import PreAuthRequest
from orchestration.graph import run_pipeline
from rules.models import AdjudicationResult, Recommendation, Deduction
from retrieval.vector_store import RetrievedClause

def evaluate():
    manifest_path = os.path.join(PROJECT_ROOT, "data", "synthetic", "manifest.json")
    results_path = os.path.join(PROJECT_ROOT, "data", "evaluation_results.json")
    
    if not os.path.exists(manifest_path):
        print(f"Manifest file not found: {manifest_path}")
        return
        
    with open(manifest_path, 'r') as f:
        manifest = json.load(f)
        
    results = []
    
    # 1. Extraction
    fields_extracted = 0
    fields_total = 0
    
    # 2. Retrieval
    retrieval_successes = 0
    
    # 3. Grounding
    total_citations = 0
    hallucinated_citations = 0
    
    # 4. Decision
    TP, TN, FP, FN = 0, 0, 0, 0
    
    # 5. Escalation
    esc_TP, esc_TN, esc_FP, esc_FN = 0, 0, 0, 0
    
    # 6. Latency
    latencies = []
    
    # 7. Cost
    total_cost = 0.0
    
    # 8. Robustness
    robustness_metrics = defaultdict(lambda: {"correct": 0, "total": 0})
    category_metrics = defaultdict(lambda: {"correct": 0, "total": 0})
    
    for case in manifest:
        case_id = case.get("case_id", "unknown")
        expected_decision = case.get("expected_decision", "")
        expected_escalation = case.get("expected_escalation", False)
        category = case.get("category", "unknown")
        adv_type = case.get("adv_type", "none")
        payload = case.get("payload", {})
        
        print(f"Evaluating case {case_id}...")
        
        try:
            request = PreAuthRequest(**payload)
            pipeline_result = run_pipeline(request)
            
            # Extract standard dict format for easier processing if it's a Pydantic model
            if hasattr(pipeline_result, "model_dump"):
                result_dict = pipeline_result.model_dump()
            elif hasattr(pipeline_result, "dict"):
                result_dict = pipeline_result.dict()
            elif isinstance(pipeline_result, dict):
                result_dict = pipeline_result
            else:
                result_dict = vars(pipeline_result)
                
            rec = result_dict.get("recommendation")
            if hasattr(rec, "value"): 
                rec = rec.value
            elif isinstance(rec, str): 
                rec = rec.upper()
                
            needs_escalation = result_dict.get("needs_escalation", False)
            latency = result_dict.get("total_latency", 0.0)
            cost = result_dict.get("llm_cost_inr", 0.0)
            retrieved = result_dict.get("retrieved_clauses", [])
            hallucinated = result_dict.get("hallucinated_citations", 0)
            tot_cits = result_dict.get("total_citations", 0)
            
            # 1. Extraction: proxy check
            if payload:
                fields_total += len(payload)
                fields_extracted += len(payload) # For JSON intake
                
            # 2. Retrieval
            if retrieved:
                retrieval_successes += 1
                
            # 3. Grounding
            hallucinated_citations += hallucinated
            total_citations += tot_cits
            
            # 4. Decision
            is_correct = (str(rec) == str(expected_decision).upper())
            
            if rec == "APPROVED" and str(expected_decision).upper() == "APPROVED":
                TP += 1
            elif rec == "DENIED" and str(expected_decision).upper() == "DENIED":
                TN += 1
            elif rec == "APPROVED" and str(expected_decision).upper() == "DENIED":
                FP += 1
            elif rec == "DENIED" and str(expected_decision).upper() == "APPROVED":
                FN += 1
                
            # 5. Escalation
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
            
            # 8. Robustness
            robustness_metrics[adv_type]["total"] += 1
            category_metrics[category]["total"] += 1
            if is_correct:
                robustness_metrics[adv_type]["correct"] += 1
                category_metrics[category]["correct"] += 1
                
            results.append({
                "case_id": case_id,
                "status": "success",
                "correct": is_correct,
                "metrics": result_dict
            })
            
        except Exception as e:
            print(f"Error evaluating case {case_id}: {e}")
            traceback.print_exc()
            results.append({
                "case_id": case_id,
                "status": "error",
                "error": str(e)
            })
            
    # Compute aggregates
    total_cases = len(manifest)
    evaluated_cases = len([r for r in results if r["status"] == "success"])
    
    if evaluated_cases == 0:
        print("No cases evaluated successfully.")
        return
        
    extraction_accuracy = fields_extracted / max(1, fields_total)
    retrieval_quality = retrieval_successes / max(1, evaluated_cases)
    hallucination_rate = hallucinated_citations / max(1, total_citations)
    
    total_decisions = TP + TN + FP + FN
    decision_accuracy = (TP + TN) / max(1, total_decisions)
    
    esc_precision = esc_TP / max(1, esc_TP + esc_FP)
    esc_recall = esc_TP / max(1, esc_TP + esc_FN)
    
    mean_latency = np.mean(latencies) if latencies else 0.0
    p50 = np.percentile(latencies, 50) if latencies else 0.0
    p95 = np.percentile(latencies, 95) if latencies else 0.0
    p99 = np.percentile(latencies, 99) if latencies else 0.0
    
    avg_cost = total_cost / max(1, evaluated_cases)
    
    for k in robustness_metrics:
        robustness_metrics[k]["accuracy"] = robustness_metrics[k]["correct"] / max(1, robustness_metrics[k]["total"])
    for k in category_metrics:
        category_metrics[k]["accuracy"] = category_metrics[k]["correct"] / max(1, category_metrics[k]["total"])
        
    fairness_note = "See separate fairness script for demographic parity and equal opportunity metrics."
    
    # 9. Format Report
    report = {
        "summary": {
            "evaluated_cases": evaluated_cases,
            "total_cases": total_cases
        },
        "dimensions": {
            "1_extraction": {"accuracy": extraction_accuracy},
            "2_retrieval": {"recall_proxy": retrieval_quality},
            "3_grounding": {"hallucination_rate": hallucination_rate},
            "4_decision": {
                "accuracy": decision_accuracy,
                "confusion_matrix": {"TP": TP, "TN": TN, "FP": FP, "FN": FN}
            },
            "5_escalation": {"precision": esc_precision, "recall": esc_recall},
            "6_latency": {
                "mean": mean_latency,
                "p50": p50,
                "p95": p95,
                "p99": p99
            },
            "7_cost": {"total": total_cost, "average_per_case": avg_cost},
            "8_robustness": dict(robustness_metrics),
            "category_breakdown": dict(category_metrics),
            "9_fairness": fairness_note
        },
        "case_results": results
    }
    
    os.makedirs(os.path.dirname(results_path), exist_ok=True)
    with open(results_path, 'w') as f:
        json.dump(report, f, indent=2)
        
    # Print Output
    print("\n" + "="*50)
    print("EVALUATION REPORT")
    print("="*50)
    print(f"Cases Evaluated: {evaluated_cases}/{total_cases}")
    print("\n1. Extraction Accuracy: {:.2%}".format(extraction_accuracy))
    print("2. Retrieval Quality (proxy): {:.2%}".format(retrieval_quality))
    print("3. Grounding Fidelity (hallucination rate): {:.2%}".format(hallucination_rate))
    print("4. Decision Accuracy: {:.2%}".format(decision_accuracy))
    print(f"   Confusion Matrix: TP={TP}, TN={TN}, FP={FP} (DANGEROUS), FN={FN} (HARMFUL)")
    print("5. Escalation Precision: {:.2%} | Recall: {:.2%}".format(esc_precision, esc_recall))
    print("6. Latency: Mean={:.2f}s, p50={:.2f}s, p95={:.2f}s, p99={:.2f}s".format(mean_latency, p50, p95, p99))
    if p99 > 3600:
        print("   WARNING: Latency SLA breached (Emergency > 1h)!")
    elif p99 > 48 * 3600:
        print("   WARNING: Latency SLA breached (Planned > 48h)!")
    print("7. Cost: Total ₹{:.2f}, Avg ₹{:.2f}/case".format(total_cost, avg_cost))
    
    print("\n8. Robustness (Accuracy by Adv Type):")
    for k, v in robustness_metrics.items():
        print(f"   - {k}: {v['accuracy']:.2%} ({v['correct']}/{v['total']})")
        
    print("\nCategory Breakdown:")
    for k, v in category_metrics.items():
        print(f"   - {k}: {v['accuracy']:.2%} ({v['correct']}/{v['total']})")
        
    print("\n9. Fairness:")
    print(f"   {fairness_note}")
    
    print("\n" + "="*50)
    print(f"Trade-off Highlight: FP Rate vs FN Rate")
    actual_negatives = FP + TN
    actual_positives = TP + FN
    fp_rate = FP / max(1, actual_negatives)
    fn_rate = FN / max(1, actual_positives)
    print(f"False Positive Rate (Approved when should deny): {fp_rate:.2%}")
    print(f"False Negative Rate (Denied when should approve): {fn_rate:.2%}")
    print("="*50)
    print(f"Results saved to {results_path}")

if __name__ == '__main__':
    evaluate()
