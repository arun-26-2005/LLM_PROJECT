"""
orchestration/__init__.py
-------------------------
Public API for the agent orchestration subsystem.

Exposes the main pipeline entry point used to process a pre-auth request
end-to-end: ingestion → extraction → retrieval → tool calls → rules →
LLM reasoning → citation guard → recommendation.

Usage:
    from orchestration import run_pipeline
    result = run_pipeline(intake_result)
"""

from orchestration.state import PipelineState
from orchestration.graph import run_pipeline

__all__ = [
    "run_pipeline",
    "PipelineState",
]
