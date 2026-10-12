"""
orchestration/graph.py
----------------------
LangGraph state-machine definition for the agent orchestration pipeline.

Wires together all pipeline nodes into a directed graph with conditional
edges for escalation routing.

Architecture Role:
    This is the top-level orchestration entry point. It defines the execution
    order and branching logic of the pre-auth adjudication pipeline.

Usage:
    from orchestration.graph import build_graph, run_pipeline

    graph = build_graph()
    result = run_pipeline(intake_result_dict)
"""

from __future__ import annotations

import logging
import time
from typing import Any

from orchestration.state import PipelineState
from orchestration.nodes import (
    validate_intake,
    retrieve_clauses_node,
    call_policy_api,
    call_hospital_api,
    apply_rules_engine,
    llm_reasoning,
    citation_guard,
    escalation_gate,
    format_recommendation,
)

logger = logging.getLogger(__name__)


def build_graph():
    """Build and compile the LangGraph state machine.

    Returns:
        A compiled LangGraph graph ready for invocation.

    Raises:
        ImportError: If langgraph is not installed.

    Graph Structure:
        validate_intake → retrieve_clauses → call_policy_api →
        call_hospital_api → apply_rules_engine → llm_reasoning →
        citation_guard → escalation_gate →
            ├─ (needs_escalation=False) → format_recommendation → END
            └─ (needs_escalation=True)  → format_recommendation → END
    """
    try:
        from langgraph.graph import StateGraph, END
    except ImportError:
        raise ImportError(
            "langgraph is required for agent orchestration. "
            "Install with: pip install langgraph>=0.2.0 langchain-core>=0.3.0"
        )

    # Build the graph
    graph = StateGraph(PipelineState)

    # Add nodes
    graph.add_node("validate_intake", validate_intake)
    graph.add_node("retrieve_clauses", retrieve_clauses_node)
    graph.add_node("call_policy_api", call_policy_api)
    graph.add_node("call_hospital_api", call_hospital_api)
    graph.add_node("apply_rules_engine", apply_rules_engine)
    graph.add_node("llm_reasoning", llm_reasoning)
    graph.add_node("citation_guard", citation_guard)
    graph.add_node("escalation_gate", escalation_gate)
    graph.add_node("format_recommendation", format_recommendation)

    # Set entry point
    graph.set_entry_point("validate_intake")

    # Wire edges (linear sequence with conditional at escalation_gate)
    graph.add_edge("validate_intake", "retrieve_clauses")
    graph.add_edge("retrieve_clauses", "call_policy_api")
    graph.add_edge("call_policy_api", "call_hospital_api")
    graph.add_edge("call_hospital_api", "apply_rules_engine")
    graph.add_edge("apply_rules_engine", "llm_reasoning")
    graph.add_edge("llm_reasoning", "citation_guard")
    graph.add_edge("citation_guard", "escalation_gate")

    # Both escalation paths lead to format_recommendation
    graph.add_edge("escalation_gate", "format_recommendation")
    graph.add_edge("format_recommendation", END)

    # Compile
    compiled = graph.compile()
    logger.info("LangGraph pipeline compiled with %d nodes.", 9)

    return compiled


def run_pipeline(intake_result: dict[str, Any]) -> dict[str, Any]:
    """Run the full pre-auth adjudication pipeline.

    This is the main entry point for processing a single claim. It builds
    (or reuses) the LangGraph graph and invokes it with the intake result.

    Args:
        intake_result: Serialized IntakeResult from Member 1's pipeline.

    Returns:
        The final PipelineState dict containing the recommendation,
        decision record, and metrics.
    """
    start = time.perf_counter()

    graph = build_graph()

    initial_state: dict[str, Any] = {
        "intake_result": intake_result,
        "node_latencies": {},
        "errors": [],
        "pipeline_status": "running",
    }

    # Run the graph
    result = graph.invoke(initial_state)

    # Record total latency
    result["total_latency"] = time.perf_counter() - start

    logger.info(
        "Pipeline completed in %.3fs. Recommendation: %s (confidence: %.2f)",
        result.get("total_latency", 0),
        result.get("recommendation", "UNKNOWN"),
        result.get("confidence", 0),
    )

    return result
