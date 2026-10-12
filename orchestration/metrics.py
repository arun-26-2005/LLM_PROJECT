"""
orchestration/metrics.py
------------------------
Latency and cost tracking utilities for the pipeline.

Provides decorators and helper functions to instrument every pipeline node
with wall-clock timing and LLM token/cost tracking.

Metrics tracked (from Metrics.md):
    - Latency: End-to-end time per claim, per-node breakdown.
    - Cost: Tokens and INR per transaction.

Usage:
    from orchestration.metrics import track_latency, compute_cost_inr
"""

from __future__ import annotations

import functools
import logging
import time
from typing import Any, Callable

logger = logging.getLogger(__name__)

# LLM pricing (INR per 1K tokens) — approximate rates as of 2024.
# These are configurable and should be updated based on the actual
# API provider and pricing tier.
LLM_PRICING_INR = {
    "gpt-4o": {"input": 0.42, "output": 1.26},        # ~$5/$15 per 1M tokens
    "gpt-4o-mini": {"input": 0.013, "output": 0.05},   # ~$0.15/$0.60 per 1M tokens
    "claude-3.5-sonnet": {"input": 0.25, "output": 1.26},
    "claude-3-haiku": {"input": 0.02, "output": 0.10},
    "grok-2-latest": {"input": 0.17, "output": 0.84},  # ~$2/$10 per 1M tokens (~₹84/$)
    "grok-beta": {"input": 0.42, "output": 1.26},      # ~$5/$15 per 1M tokens
    "grok": {"input": 0.17, "output": 0.84},
    "default": {"input": 0.10, "output": 0.40},
}


def track_latency(node_name: str) -> Callable:
    """Decorator that adds latency tracking to a pipeline node function.

    Wraps a node function to automatically measure wall-clock execution time
    and record it in the state's `node_latencies` dict.

    Args:
        node_name: Name of the pipeline node (for reporting).

    Returns:
        Decorated function.
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(state: dict[str, Any]) -> dict[str, Any]:
            start = time.perf_counter()
            result = func(state)
            elapsed = time.perf_counter() - start

            # Update latencies in the returned state
            latencies = {**state.get("node_latencies", {}), **result.get("node_latencies", {})}
            latencies[node_name] = elapsed
            result["node_latencies"] = latencies

            logger.debug("Node '%s' completed in %.4fs.", node_name, elapsed)
            return result

        return wrapper
    return decorator


def compute_cost_inr(
    input_tokens: int,
    output_tokens: int,
    model: str = "default",
) -> float:
    """Compute the estimated cost in INR for an LLM API call.

    Args:
        input_tokens: Number of input tokens.
        output_tokens: Number of output tokens.
        model: LLM model name (must be in LLM_PRICING_INR).

    Returns:
        Estimated cost in Indian Rupees.
    """
    pricing = LLM_PRICING_INR.get(model, LLM_PRICING_INR["default"])

    input_cost = (input_tokens / 1000) * pricing["input"]
    output_cost = (output_tokens / 1000) * pricing["output"]

    total = input_cost + output_cost

    logger.debug(
        "LLM cost estimate: %d input + %d output tokens (model=%s) = ₹%.4f",
        input_tokens, output_tokens, model, total,
    )

    return total


def format_metrics_report(state: dict[str, Any]) -> str:
    """Generate a human-readable metrics report from the pipeline state.

    Args:
        state: The final PipelineState after pipeline completion.

    Returns:
        Formatted string report of latency, cost, and quality metrics.
    """
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append("PIPELINE METRICS REPORT")
    lines.append("=" * 60)

    # Latency
    latencies = state.get("node_latencies", {})
    total = state.get("total_latency", sum(latencies.values()))

    lines.append(f"\n📊 Total Latency: {total:.3f}s")
    lines.append("  Per-node breakdown:")
    for node, elapsed in sorted(latencies.items()):
        pct = (elapsed / total * 100) if total > 0 else 0
        lines.append(f"    {node:30s}  {elapsed:8.4f}s  ({pct:5.1f}%)")

    # Cost
    tokens = state.get("llm_token_count", {})
    cost = state.get("llm_cost_inr", 0.0)
    lines.append(f"\n💰 LLM Cost: ₹{cost:.4f}")
    lines.append(f"    Input tokens:  {tokens.get('input_tokens', 0):,}")
    lines.append(f"    Output tokens: {tokens.get('output_tokens', 0):,}")

    # Quality
    hallucinations = state.get("hallucinated_citations", [])
    lines.append(f"\n🛡️  Hallucinated citations: {len(hallucinations)}")
    lines.append(f"   Confidence: {state.get('confidence', 0):.2f}")
    lines.append(f"   Recommendation: {state.get('recommendation', 'N/A')}")
    lines.append(f"   Needs escalation: {state.get('needs_escalation', False)}")

    lines.append("=" * 60)

    return "\n".join(lines)
