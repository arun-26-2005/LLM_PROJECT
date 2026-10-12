"""
rules/__init__.py
-----------------
Public API for the deterministic rules engine.

Usage:
    from rules import apply_rules, AdjudicationResult, Recommendation
"""

from rules.models import (
    AdjudicationResult,
    Deduction,
    DeductionCategory,
    PolicyStatusInfo,
    Recommendation,
    WaitingPeriodInfo,
)
from rules.engine import apply_rules

__all__ = [
    "apply_rules",
    "AdjudicationResult",
    "Deduction",
    "DeductionCategory",
    "PolicyStatusInfo",
    "Recommendation",
    "WaitingPeriodInfo",
]
