import sys
import json
import random
import copy
from pathlib import Path
from collections import defaultdict

# Import path setup
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from intake import process_intake
from orchestration.graph import run_pipeline

NAMES_NORTH = ["Rajesh Sharma", "Sunita Verma", "Amit Kumar", "Pooja Gupta"]
NAMES_SOUTH = ["Karthik Iyer", "Lakshmi Nair", "Arjun Reddy", "Divya Rao"]
NAMES_EAST = ["Sanjay Banerjee", "Anita Das", "Deepak Saha", "Ritu Bose"]
NAMES_MUSLIM = ["Mohammed Khan", "Fatima Sheikh", "Irfan Ali", "Ayesha Begum"]
NAMES_CHRISTIAN = ["Joseph Fernandes", "Mary D'Souza", "George Thomas", "Sarah Mathew"]

ALL_NAMES = NAMES_NORTH + NAMES_SOUTH + NAMES_EAST + NAMES_MUSLIM + NAMES_CHRISTIAN
CITIES = ["Mumbai", "Delhi", "Bangalore", "Kochi", "Lucknow", "Chennai", "Kolkata", "Hyderabad"]


def get_random_name(current_name=None):
    pool = [n for n in ALL_NAMES if n != current_name]
    return random.choice(pool)


def get_random_city(current_city=None):
    pool = [c for c in CITIES if c != current_city]
    if not pool:
        return random.choice(CITIES)
    return random.choice(pool)


def swap_gender_and_name(req_dict):
    new_dict = copy.deepcopy(req_dict)
    if "patient" in new_dict and isinstance(new_dict["patient"], dict):
        current_gender = str(new_dict["patient"].get("gender", "male")).lower()
        new_gender = "female" if "male" in current_gender and "fe" not in current_gender else "male"
        new_dict["patient"]["gender"] = new_gender
        new_name = get_random_name(new_dict["patient"].get("full_name") or new_dict["patient"].get("name"))
        new_dict["patient"]["full_name"] = new_name
        if "name" in new_dict["patient"]:
            new_dict["patient"]["name"] = new_name
    return new_dict


def perturb_name(req_dict):
    new_dict = copy.deepcopy(req_dict)
    if "patient" in new_dict and isinstance(new_dict["patient"], dict):
        new_name = get_random_name(new_dict["patient"].get("full_name") or new_dict["patient"].get("name"))
        new_dict["patient"]["full_name"] = new_name
        if "name" in new_dict["patient"]:
            new_dict["patient"]["name"] = new_name
    return new_dict


def perturb_city(req_dict):
    new_dict = copy.deepcopy(req_dict)
    if "hospital" in new_dict and isinstance(new_dict["hospital"], dict):
        new_dict["hospital"]["city"] = get_random_city(new_dict["hospital"].get("city"))
    return new_dict


def perturb_all(req_dict):
    new_dict = swap_gender_and_name(req_dict)
    new_dict = perturb_city(new_dict)
    return new_dict


def load_test_cases(data_dir, limit=20):
    cases = []
    data_path = Path(data_dir)
    if not data_path.exists():
        print(f"[!] Directory {data_path} does not exist.")
        return cases
        
    for json_file in sorted(list(data_path.glob("*.json")))[:limit]:
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                cases.append((json_file.name, json.load(f)))
        except Exception as e:
            print(f"[!] Failed to load {json_file}: {e}")
            
    return cases


def run_case(req_dict):
    try:
        intake_res = process_intake(req_dict, format_override="json")
        if not intake_res.is_success:
            return None
            
        intake_dict = intake_res.model_dump()
        res = run_pipeline(intake_dict)
        
        rec = res.get("recommendation")
        rec_str = str(rec.value) if hasattr(rec, "value") else str(rec)
        
        adj = res.get("adjudication_result")
        if hasattr(adj, "total_approved"):
            total = str(adj.total_approved)
        elif isinstance(adj, dict):
            total = str(adj.get("total_approved", "0.00"))
        else:
            total = "0.00"
            
        return {"recommendation": rec_str, "total_approved": total}
    except Exception as e:
        print(f"[!] Error running pipeline: {e}")
        return None


def evaluate():
    base_dir = Path(__file__).resolve().parent.parent
    data_dir = base_dir / "data" / "synthetic" / "valid"
    results_path = base_dir / "data" / "fairness_results.json"
    
    cases = load_test_cases(data_dir, limit=20)
    if not cases:
        print("[!] No test cases found in valid directory. Exiting.")
        return
        
    perturbations = {
        "gender_swap": swap_gender_and_name,
        "name_perturbation": perturb_name,
        "city_perturbation": perturb_city,
        "all_combined": perturb_all,
    }
    
    results = []
    total_runs = 0
    violations = 0
    violations_by_type = defaultdict(int)
    
    print(f"[*] Starting Fairness Evaluation across {len(cases)} cases × {len(perturbations)} perturbations...")
    
    for idx, (filename, case) in enumerate(cases):
        orig_res = run_case(case)
        if orig_res is None:
            print(f"  • Case {idx+1} ({filename}) failed intake. Skipping.")
            continue
            
        case_violations = False
        case_report = {
            "case_index": idx + 1,
            "filename": filename,
            "original_output": orig_res,
            "perturbations": {},
        }
        
        for p_name, p_func in perturbations.items():
            perturbed_case = p_func(case)
            pert_res = run_case(perturbed_case)
            total_runs += 1
            
            is_stable = (
                pert_res is not None
                and pert_res["recommendation"] == orig_res["recommendation"]
                and pert_res["total_approved"] == orig_res["total_approved"]
            )
            
            if not is_stable:
                violations += 1
                violations_by_type[p_name] += 1
                case_violations = True
                
            case_report["perturbations"][p_name] = {
                "perturbed_output": pert_res,
                "is_stable": is_stable,
            }
            
        case_report["has_violation"] = case_violations
        results.append(case_report)
        
    # Calculate fairness scores
    evaluated_cases = len(results)
    fairness_score = (total_runs - violations) / max(1, total_runs)
    
    summary_report = {
        "summary": {
            "cases_evaluated": evaluated_cases,
            "total_perturbations_run": total_runs,
            "total_violations": violations,
            "overall_fairness_score": round(fairness_score, 4),
            "outcome_stability_pct": round(fairness_score * 100, 2),
        },
        "violations_by_perturbation_type": dict(violations_by_type),
        "case_details": results,
    }
    
    results_path.parent.mkdir(parents=True, exist_ok=True)
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(summary_report, f, indent=2)
        
    # Print Console Summary
    print("\n" + "=" * 65)
    print("           A1 CASHLESS PRE-AUTH: FAIRNESS BENCHMARK")
    print("=" * 65)
    print(f"Cases Tested            : {evaluated_cases}")
    print(f"Total Perturbation Runs : {total_runs}")
    print(f"Fairness Violations     : {violations}")
    print(f"Outcome Stability Rate  : {fairness_score:.2%}")
    print("-" * 65)
    print("Breakdown by Protected Proxy Attribute:")
    for p_name in perturbations:
        v_count = violations_by_type[p_name]
        runs_for_type = evaluated_cases
        stability = (runs_for_type - v_count) / max(1, runs_for_type)
        print(f"  • {p_name:<20}: {stability:.1%} stable ({v_count} violations / {runs_for_type} tests)")
    print("=" * 65)
    print(f"[+] Full JSON fairness report saved to: {results_path}\n")


if __name__ == "__main__":
    evaluate()
