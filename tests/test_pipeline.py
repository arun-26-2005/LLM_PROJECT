"""
tests/test_pipeline.py
----------------------
End-to-end integration tests for the orchestration pipeline.

Tests the full LangGraph pipeline:
    validate_intake → retrieve_clauses → call_policy_api →
    call_hospital_api → apply_rules_engine → llm_reasoning →
    citation_guard → escalation_gate → format_recommendation

Usage:
    python -m pytest tests/test_pipeline.py -v
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest


# ============================================================================
# Fixtures — Synthetic IntakeResult dicts
# ============================================================================


def _make_intake_result(
    is_success: bool = True,
    policy_number: str = "POL-ACTIVE-001",
    plan_type: str = "individual",
    sum_insured: str = "500000.00",
    co_pay_pct: str = "0.00",
    icd10_code: str = "I21.0",
    diagnosis_desc: str = "Acute STEMI",
    is_pre_existing: bool = False,
    procedure_desc: str = "Primary PCI with DES",
    admission_type: str = "emergency",
    network_tier: str = "cashless_network",
    total_amount: str = "250000.00",
    policy_start_date: str = "2023-01-01",
    admission_date: str = "2025-06-15",
) -> dict:
    """Create a synthetic IntakeResult dict for pipeline testing."""
    if not is_success:
        return {
            "is_success": False,
            "validation_errors": ["Failed to extract structured data from input."],
            "request": None,
        }

    request_id = str(uuid.uuid4())
    patient_id = str(uuid.uuid4())
    hospital_id = str(uuid.uuid4())

    return {
        "is_success": True,
        "confidence_score": 0.92,
        "validation_errors": [],
        "request": {
            "request_id": request_id,
            "submitted_at": str(date.today()),
            "source_format": "json",
            "status": "pending",
            "admission_date": admission_date,
            "patient": {
                "patient_id": patient_id,
                "full_name": "Rajesh Kumar",
                "age": 45,
                "gender": "male",
                "policy_number": policy_number,
            },
            "policy": {
                "policy_number": policy_number,
                "plan_type": plan_type,
                "sum_insured": sum_insured,
                "policy_start_date": policy_start_date,
                "waiting_period_months": 0,
                "sub_limits": {"limits": {"room_rent_per_day": "5000.00"}},
                "co_pay_pct": co_pay_pct,
            },
            "hospital": {
                "hospital_id": hospital_id,
                "name": "Synthetic Metro Hospital",
                "city": "Mumbai",
                "network_tier": network_tier,
                "category": "multi_specialty",
            },
            "diagnosis": {
                "icd10_code": icd10_code,
                "description": diagnosis_desc,
                "is_pre_existing": is_pre_existing,
            },
            "procedure": {
                "procedure_code": "PCI-001",
                "description": procedure_desc,
                "admission_type": admission_type,
            },
            "cost_estimate": {
                "line_items": [
                    {"item": "Room Rent (5 days)", "amount": "40000.00",
                     "category": "room_rent"},
                    {"item": "Surgeon Fee", "amount": "80000.00",
                     "category": "surgeon_fee"},
                    {"item": "Stent (DES)", "amount": "30000.00",
                     "category": "implants"},
                    {"item": "Diagnostics", "amount": "25000.00",
                     "category": "diagnostic"},
                    {"item": "Pharmacy", "amount": "35000.00",
                     "category": "pharmacy"},
                    {"item": "ICU Charges", "amount": "20000.00",
                     "category": "icu_charges"},
                    {"item": "Consultation", "amount": "15000.00",
                     "category": "consultation_fee"},
                    {"item": "Nursing", "amount": "5000.00",
                     "category": "nursing"},
                ],
                "total_amount": total_amount,
            },
        },
    }


# ============================================================================
# Tests: Individual Node Functions
# ============================================================================


class TestValidateIntake:
    """Tests for the validate_intake node."""

    def test_successful_intake(self):
        from orchestration.nodes import validate_intake

        state = {"intake_result": _make_intake_result(), "node_latencies": {}}
        result = validate_intake(state)

        assert result["pre_auth_request"] is not None
        assert result["pipeline_status"] == "running"
        assert "validate_intake" in result["node_latencies"]

    def test_failed_intake(self):
        from orchestration.nodes import validate_intake

        state = {"intake_result": _make_intake_result(is_success=False), "node_latencies": {}}
        result = validate_intake(state)

        assert result["pre_auth_request"] is None
        assert result["recommendation"] == "RECOMMEND_QUERY"
        assert result["pipeline_status"] == "failed"


class TestRetrieveClausesNode:
    """Tests for the retrieve_clauses_node."""

    def test_builds_query_from_request(self):
        from orchestration.nodes import retrieve_clauses_node

        intake = _make_intake_result()
        state = {
            "pre_auth_request": intake["request"],
            "node_latencies": {},
        }
        result = retrieve_clauses_node(state)

        assert "retrieval_query" in result
        assert "STEMI" in result["retrieval_query"]
        assert isinstance(result["retrieved_clauses"], list)
        assert "retrieve_clauses" in result["node_latencies"]

    def test_null_request_returns_empty(self):
        from orchestration.nodes import retrieve_clauses_node

        state = {"pre_auth_request": None, "node_latencies": {}}
        result = retrieve_clauses_node(state)

        assert result["retrieved_clauses"] == []
        assert result["retrieval_query"] == ""


class TestCallPolicyApi:
    """Tests for the call_policy_api node."""

    def test_active_policy(self):
        from orchestration.nodes import call_policy_api

        intake = _make_intake_result()
        state = {"pre_auth_request": intake["request"], "node_latencies": {}}
        result = call_policy_api(state)

        assert result["policy_status"]["is_active"] is True
        assert result["policy_status"]["status"] == "ACTIVE"
        assert result["waiting_period_info"]["initial_wp_clear"] is True

    def test_lapsed_policy(self):
        from orchestration.nodes import call_policy_api

        intake = _make_intake_result(policy_number="POL-LAPSED-001")
        state = {"pre_auth_request": intake["request"], "node_latencies": {}}
        result = call_policy_api(state)

        assert result["policy_status"]["is_active"] is False
        assert result["policy_status"]["status"] == "LAPSED"

    def test_days_since_inception_computed(self):
        from orchestration.nodes import call_policy_api

        intake = _make_intake_result(
            policy_start_date="2025-06-01",
            admission_date="2025-06-15",
        )
        state = {"pre_auth_request": intake["request"], "node_latencies": {}}
        result = call_policy_api(state)

        assert result["policy_status"]["days_since_inception"] == 14
        assert result["waiting_period_info"]["initial_wp_clear"] is False


class TestCallHospitalApi:
    """Tests for the call_hospital_api node."""

    def test_network_hospital(self):
        from orchestration.nodes import call_hospital_api

        intake = _make_intake_result()
        state = {"pre_auth_request": intake["request"], "node_latencies": {}}
        result = call_hospital_api(state)

        assert result["hospital_empanelment"]["is_empanelled"] is True

    def test_non_network_hospital(self):
        from orchestration.nodes import call_hospital_api

        intake = _make_intake_result(network_tier="non_network")
        state = {"pre_auth_request": intake["request"], "node_latencies": {}}
        result = call_hospital_api(state)

        assert result["hospital_empanelment"]["is_empanelled"] is False
        assert result["hospital_empanelment"]["tier"] == "non_network"


class TestEscalationGate:
    """Tests for the escalation_gate node."""

    def test_no_escalation_on_clean_case(self):
        from orchestration.nodes import escalation_gate

        state = {
            "adjudication_result": {
                "confidence_score": 0.85,
                "total_claimed": "200000",
                "escalation_triggers": [],
            },
            "pre_auth_request": _make_intake_result()["request"],
            "hospital_empanelment": {"is_empanelled": True},
            "hallucinated_citations": [],
            "node_latencies": {},
        }
        result = escalation_gate(state)

        assert result["needs_escalation"] is False
        assert result["escalation_triggers"] == []

    def test_low_confidence_triggers_escalation(self):
        from orchestration.nodes import escalation_gate

        state = {
            "adjudication_result": {
                "confidence_score": 0.45,
                "total_claimed": "200000",
                "escalation_triggers": [],
            },
            "pre_auth_request": _make_intake_result()["request"],
            "hospital_empanelment": {"is_empanelled": True},
            "hallucinated_citations": [],
            "node_latencies": {},
        }
        result = escalation_gate(state)

        assert result["needs_escalation"] is True
        assert any("Low confidence" in t for t in result["escalation_triggers"])

    def test_high_value_triggers_escalation(self):
        from orchestration.nodes import escalation_gate

        state = {
            "adjudication_result": {
                "confidence_score": 0.90,
                "total_claimed": "800000",
                "escalation_triggers": [],
            },
            "pre_auth_request": _make_intake_result()["request"],
            "hospital_empanelment": {"is_empanelled": True},
            "hallucinated_citations": [],
            "node_latencies": {},
        }
        result = escalation_gate(state)

        assert result["needs_escalation"] is True
        assert any("claim value" in t.lower() for t in result["escalation_triggers"])

    def test_ped_triggers_escalation(self):
        from orchestration.nodes import escalation_gate

        intake = _make_intake_result(is_pre_existing=True)
        state = {
            "adjudication_result": {
                "confidence_score": 0.90,
                "total_claimed": "200000",
                "escalation_triggers": [],
            },
            "pre_auth_request": intake["request"],
            "hospital_empanelment": {"is_empanelled": True},
            "hallucinated_citations": [],
            "node_latencies": {},
        }
        result = escalation_gate(state)

        assert result["needs_escalation"] is True
        assert "PED-flagged diagnosis" in result["escalation_triggers"]

    def test_hallucinated_citations_trigger_escalation(self):
        from orchestration.nodes import escalation_gate

        state = {
            "adjudication_result": {
                "confidence_score": 0.90,
                "total_claimed": "200000",
                "escalation_triggers": [],
            },
            "pre_auth_request": _make_intake_result()["request"],
            "hospital_empanelment": {"is_empanelled": True},
            "hallucinated_citations": ["Section 99.9"],
            "node_latencies": {},
        }
        result = escalation_gate(state)

        assert result["needs_escalation"] is True
        assert any("Hallucinated" in t for t in result["escalation_triggers"])


class TestCitationGuard:
    """Tests for the citation_guard node (Guardrail #2)."""

    def test_grounded_citations_pass(self):
        from orchestration.nodes import citation_guard

        state = {
            "raw_llm_output": "Per Section 3.1, the initial waiting period has elapsed.",
            "retrieved_clauses": [
                {"chunk_text": "SECTION 3 — WAITING PERIODS\n3.1 Initial Waiting Period...",
                 "source_file": "individual_health_standard.txt"},
            ],
            "node_latencies": {},
        }
        result = citation_guard(state)

        assert result["hallucinated_citations"] == []

    def test_hallucinated_section_detected(self):
        from orchestration.nodes import citation_guard

        state = {
            "raw_llm_output": "Per Section 99.9, this claim is denied.",
            "retrieved_clauses": [
                {"chunk_text": "SECTION 3 — WAITING PERIODS\n3.1 Initial...",
                 "source_file": "individual_health_standard.txt"},
            ],
            "node_latencies": {},
        }
        result = citation_guard(state)

        assert len(result["hallucinated_citations"]) >= 1
        assert "Section 99.9" in result["hallucinated_citations"]

    def test_empty_output_passes(self):
        from orchestration.nodes import citation_guard

        state = {
            "raw_llm_output": "",
            "retrieved_clauses": [],
            "node_latencies": {},
        }
        result = citation_guard(state)

        assert result["hallucinated_citations"] == []


class TestFormatRecommendation:
    """Tests for the format_recommendation node."""

    def test_normal_completion(self):
        from orchestration.nodes import format_recommendation

        state = {
            "adjudication_result": {
                "recommendation": "RECOMMEND_AUTHORISE",
                "confidence_score": 0.85,
            },
            "reasoning_narrative": "Claim is valid.",
            "retrieved_clauses": [],
            "escalation_triggers": [],
            "needs_escalation": False,
            "hallucinated_citations": [],
            "node_latencies": {},
            "llm_token_count": {},
            "llm_cost_inr": 0.0,
        }
        result = format_recommendation(state)

        assert result["recommendation"] == "RECOMMEND_AUTHORISE"
        assert result["confidence"] == 0.85
        assert result["pipeline_status"] == "completed"
        assert "decision_record" in result

    def test_escalated_status(self):
        from orchestration.nodes import format_recommendation

        state = {
            "adjudication_result": {
                "recommendation": "RECOMMEND_AUTHORISE",
                "confidence_score": 0.55,
            },
            "reasoning_narrative": "Uncertain case.",
            "retrieved_clauses": [],
            "escalation_triggers": ["Low confidence (0.55)"],
            "needs_escalation": True,
            "hallucinated_citations": [],
            "node_latencies": {},
            "llm_token_count": {},
            "llm_cost_inr": 0.0,
        }
        result = format_recommendation(state)

        assert result["pipeline_status"] == "escalated"


# ============================================================================
# Tests: Full Pipeline (requires langgraph)
# ============================================================================


class TestFullPipeline:
    """End-to-end tests for the complete LangGraph pipeline."""

    @pytest.fixture(autouse=True)
    def _check_langgraph(self):
        """Skip tests if langgraph is not installed."""
        pytest.importorskip("langgraph", reason="langgraph not installed")

    def test_happy_path_pipeline(self):
        from orchestration.graph import run_pipeline

        intake = _make_intake_result()
        result = run_pipeline(intake)

        assert result["pipeline_status"] in ("completed", "escalated")
        assert result["recommendation"] in (
            "RECOMMEND_AUTHORISE", "RECOMMEND_QUERY", "RECOMMEND_DENY",
        )
        assert "decision_record" in result
        assert result["total_latency"] > 0
        assert "validate_intake" in result.get("node_latencies", {})

    def test_failed_intake_pipeline(self):
        from orchestration.graph import run_pipeline

        intake = _make_intake_result(is_success=False)
        result = run_pipeline(intake)

        assert result["recommendation"] == "RECOMMEND_QUERY"
        assert result["pipeline_status"] in ("failed", "completed", "escalated")

    def test_lapsed_policy_pipeline(self):
        from orchestration.graph import run_pipeline

        intake = _make_intake_result(policy_number="POL-LAPSED-TEST")
        result = run_pipeline(intake)

        # Should either deny or query
        assert result["recommendation"] in (
            "RECOMMEND_DENY", "RECOMMEND_QUERY",
        )

    def test_ped_case_escalated(self):
        from orchestration.graph import run_pipeline

        intake = _make_intake_result(is_pre_existing=True)
        result = run_pipeline(intake)

        # PED cases should trigger escalation
        assert result.get("needs_escalation") is True or \
               "PED-flagged diagnosis" in result.get("escalation_triggers", [])

    def test_metrics_are_populated(self):
        from orchestration.graph import run_pipeline

        intake = _make_intake_result()
        result = run_pipeline(intake)

        # Check that node latencies are tracked
        latencies = result.get("node_latencies", {})
        assert len(latencies) >= 5  # At least 5 nodes should have latencies

        # Check LLM cost tracking exists (may be 0 if no API key)
        assert "llm_cost_inr" in result or "decision_record" in result

    def test_decision_record_is_complete(self):
        from orchestration.graph import run_pipeline

        intake = _make_intake_result()
        result = run_pipeline(intake)

        dr = result.get("decision_record", {})
        assert "recommendation" in dr
        assert "reasoning" in dr
        assert "adjudication" in dr
        assert "metrics" in dr
