"""
orchestration/mock_api/app.py
-----------------------------
FastAPI application simulating the insurer's core systems.

Provides mock endpoints that the LangGraph agent calls as "tools":
    - Policy Admin System (PAS): policy status, waiting periods, sub-limits
    - Hospital Empanelment: network tier, agreed tariffs

These stubs return synthetic data derived from the pre-auth request fields,
simulating what a real core system would respond with.

Usage:
    # Start the mock server
    uvicorn orchestration.mock_api.app:app --port 8100

    # Or run programmatically in tests
    from orchestration.mock_api.app import app
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal

logger = logging.getLogger(__name__)

try:
    from fastapi import FastAPI, HTTPException
    from pydantic import BaseModel
except ImportError:
    raise ImportError(
        "fastapi is required for mock APIs. "
        "Install with: pip install fastapi>=0.110.0 uvicorn>=0.27.0"
    )


# ============================================================================
# FastAPI App
# ============================================================================

app = FastAPI(
    title="A1 Pre-Auth Mock Core Systems",
    description=(
        "Mock Policy Admin System (PAS) and Hospital Empanelment APIs "
        "for the Cashless Pre-Authorisation Agent pipeline."
    ),
    version="1.0.0",
)


# ============================================================================
# Response Models
# ============================================================================


class PolicyStatusResponse(BaseModel):
    """Response from the Policy Admin System for policy status lookup."""
    policy_number: str
    status: str  # "ACTIVE", "LAPSED", "EXPIRED"
    is_active: bool
    remaining_sum_insured: str  # Decimal as string
    co_pay_pct: str
    days_since_inception: int


class WaitingPeriodResponse(BaseModel):
    """Response from PAS for waiting period evaluation."""
    policy_number: str
    initial_wp_clear: bool
    specific_disease_wp_clear: bool
    ped_wp_clear: bool
    days_elapsed: int
    applicable_wp_months: int


class SubLimitBalanceResponse(BaseModel):
    """Response from PAS for sub-limit balance lookup."""
    policy_number: str
    limits: dict[str, str]
    consumed: dict[str, str]


class HospitalEmpanelmentResponse(BaseModel):
    """Response from the Hospital Empanelment API."""
    hospital_id: str
    is_empanelled: bool
    tier: str
    agreed_room_rate: str
    tariff_package: str


# ============================================================================
# Endpoints
# ============================================================================


@app.get("/api/policy/{policy_number}/status", response_model=PolicyStatusResponse)
async def get_policy_status(policy_number: str) -> PolicyStatusResponse:
    """Look up policy status from the mock Policy Admin System.

    Mock Logic:
        - Policies starting with "POL-" are ACTIVE by default.
        - Policy numbers containing "LAPSED" return LAPSED status.
        - Policy numbers containing "EXPIRED" return EXPIRED status.
        - Default sum insured: ₹5,00,000 remaining.
    """
    status = "ACTIVE"
    is_active = True

    if "LAPSED" in policy_number.upper():
        status = "LAPSED"
        is_active = False
    elif "EXPIRED" in policy_number.upper():
        status = "EXPIRED"
        is_active = False

    return PolicyStatusResponse(
        policy_number=policy_number,
        status=status,
        is_active=is_active,
        remaining_sum_insured="500000.00",
        co_pay_pct="0.00",
        days_since_inception=365,
    )


@app.get("/api/policy/{policy_number}/waiting-period", response_model=WaitingPeriodResponse)
async def get_waiting_period(
    policy_number: str,
    days_since_inception: int = 365,
) -> WaitingPeriodResponse:
    """Evaluate waiting period status for a policy.

    Mock Logic:
        - Initial 30-day WP: clear if days_since_inception >= 30.
        - Specific disease 2-year WP: clear if days_since_inception >= 730.
        - PED 4-year WP: clear if days_since_inception >= 1460.
    """
    return WaitingPeriodResponse(
        policy_number=policy_number,
        initial_wp_clear=days_since_inception >= 30,
        specific_disease_wp_clear=days_since_inception >= 730,
        ped_wp_clear=days_since_inception >= 1460,
        days_elapsed=days_since_inception,
        applicable_wp_months=0,
    )


@app.get("/api/policy/{policy_number}/sub-limit-balance", response_model=SubLimitBalanceResponse)
async def get_sub_limit_balance(policy_number: str) -> SubLimitBalanceResponse:
    """Look up sub-limit balances for a policy.

    Mock Logic:
        Returns default sub-limits with zero consumed.
    """
    return SubLimitBalanceResponse(
        policy_number=policy_number,
        limits={
            "room_rent_per_day": "5000.00",
            "icu_per_day": "10000.00",
            "ambulance": "2000.00",
        },
        consumed={
            "room_rent_per_day": "0.00",
            "icu_per_day": "0.00",
            "ambulance": "0.00",
        },
    )


@app.get("/api/hospital/{hospital_id}/empanelment", response_model=HospitalEmpanelmentResponse)
async def get_hospital_empanelment(hospital_id: str) -> HospitalEmpanelmentResponse:
    """Look up hospital empanelment status.

    Mock Logic:
        - All hospitals are empanelled by default.
        - Hospital IDs containing "NON" return non-network status.
    """
    is_empanelled = "NON" not in hospital_id.upper()
    tier = "cashless_network" if is_empanelled else "non_network"

    return HospitalEmpanelmentResponse(
        hospital_id=hospital_id,
        is_empanelled=is_empanelled,
        tier=tier,
        agreed_room_rate="5000.00",
        tariff_package="standard_metro",
    )


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "mock-core-systems"}
