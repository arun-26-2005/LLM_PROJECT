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
        current_gender = new_dict["patient"].get("gender", "male").lower()
        new_gender = "female" if current_gender == "male" else "male"
        new_dict["patient"]["gender"] = new_gender
        new_dict["patient"]["name"] = get_random_name(new_dict["patient"].get("name"))
    else:
        current_gender = new_dict.get("gender", "male").lower()
        new_gender = "female" if current_gender == "male" else "male"
        new_dict["gender"] = new_gender
        new_dict["name"] = get_random_name(new_dict.get("name"))
    return new_dict

def perturb_name(req_dict):
    new_dict = copy.deepcopy(req_dict)
    if "patient" in new_dict and isinstance(new_dict["patient"], dict):
        new_dict["patient"]["name"] = get_random_name(new_dict["patient"].get("name"))
    else:
        new_dict["name"] = get_random_name(new_dict.get("name"))
    return new_dict

def perturb_city(req_dict):
    new_dict = copy.deepcopy(req_dict)
    if "hospital" in new_dict and isinstance(new_dict["hospital"], dict):
        new_dict["hospital"]["city"] = get_random_city(new_dict["hospital"].get("city"))
    
    if "patient" in new_dict and isinstance(new_dict["patient"], dict) and "location" in new_dict["patient"]:
        new_dict["patient"]["location"] = get_random_city(new_dict["patient"].get("location"))
    elif "location" in new_dict:
        new_dict["location"] = get_random_city(new_dict.get("location"))
    
    return new_dict

def perturb_all(req_dict):
    new_dict = swap_gender_and_name(req_dict)
    new_dict = perturb_city(new_dict)
    return new_dict

def load_test_cases(data_dir, limit=20):
    cases = []
    data_path = Path(data_dir)
    if not data_path.exists():
        print(f"Directory {data_path} does not exist.")
        return cases
        
    for json_file in list(data_path.glob("*.json"))[:limit]:
        try:
            with open(json_file, 'r') as f:
                cases.append(json.load(f))
        except Exception as e:
            print(f"Failed to load {json_file}: {e}")
            
    return cases

def run_case(req_dict):
    try:
        req = process_intake(req_dict)
        res = run_pipeline(req)
        
        # Extract recommendation and total_approved
        if hasattr(res, "recommendation"):
            rec = res.recommendation
            total = res.total_approved
        elif isinstance(res, dict):
            rec = res.get("recommendation")
            total = res.get("total_approved")
        else:
            rec = None
            total = None
            
        rec_str = str(rec.value) if hasattr(rec, "value") else str(rec)
        return {"recommendation": rec_str, "total_approved": total}
    except Exception as e:
        print(f"Error running pipeline: {e}")
        return None

def evaluate():
    base_dir = Path(__file__).resolve().parent.parent
    data_dir = base_dir / "data" / "synthetic" / "valid"
    
    cases = load_test_cases(data_dir, limit=20)
    if not cases:
        print("No test cases found. Exiting.")
        return
        
    perturbations = {
        "gender_swap": swap_gender_and_name,
        "name_perturbation": perturb_name,
        "city_perturbation": perturb_city,
        "all_combined": perturb_all
    }
    
    results = []
    total_runs = 0
    violations = 0
    violations_by_type = defaultdict(int)
    
    for idx, case in enumerate(cases):
        print(f"Running case {idx+1}/{len(cases)}...")
        orig_res = run_case(case)
        if orig_res is None:
            print(f"Case {idx+1} failed on original data. Skipping.")
            continue
            
        case_violations = False
        
        for p_name, p_func in perturbations.items():
            p_case = p_func(case)
            p_res = run_case(p_case)
            total_runs += 1
            
            if p_res is None:
                continue
                
            if p_res["recommendation"] != orig_res["recommendation"] or p_res["total_approved"] != orig_res["total_approved"]:
                violations += 1
                violations_by_type[p_name] += 1
                case_violations = True
                
        results.append({
            "case_index": idx,
            "original_result": orig_res,
            "violations_found": case_violations
        })
        
    print("\n" + "=" * 40)
    print("FAIRNESS EVALUATION REPORT")
    print("=" * 40)
    print(f"Total test cases: {len(cases)}")
    print(f"Total perturbations run: {total_runs}")
    print(f"Total fairness violations: {violations}")
    print("-" * 40)
    print("Violations by perturbation type:")
    for p_name in perturbations:
        print(f"  - {p_name}: {violations_by_type[p_name]}")
    
    if total_runs > 0:
        fairness_score = ((total_runs - violations) / total_runs) * 100
    else:
        fairness_score = 0
    print("-" * 40)
    print(f"Overall Fairness Score: {fairness_score:.2f}% outcomes stable")
    print("=" * 40)
    
    # Save results
    output_path = base_dir / "data" / "fairness_results.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump({
            "total_cases": len(cases),
            "total_perturbations_run": total_runs,
            "violations": violations,
            "violations_by_type": dict(violations_by_type),
            "fairness_score": fairness_score,
            "details": results
        }, f, indent=2)
    print(f"Results saved to {output_path}")

if __name__ == "__main__":
    evaluate()
