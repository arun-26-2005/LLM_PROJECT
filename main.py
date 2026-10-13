"""
main.py
-------
FastAPI entry point for the A1 Cashless Pre-Auth Pipeline.
Provides endpoints to process pre-auth requests and view swagger docs.

Usage:
    uvicorn main:app --reload --port 8000
"""

from fastapi import FastAPI, HTTPException, Body, UploadFile, File
from pydantic import BaseModel, Field
from typing import Any, Dict
import tempfile
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from intake import process_intake
from orchestration import run_pipeline
from schemas import SourceFormat

app = FastAPI(
    title="A1 Cashless Pre-Auth API",
    description="API for evaluating health insurance pre-authorisation requests via LangGraph rules engine.",
    version="1.0.0",
)

class PreAuthPayload(BaseModel):
    """
    Standard JSON payload representing a hospital's pre-auth request.
    This structure should match the schema expected by the JSON intake handler.
    """
    request_id: str = Field(..., description="Unique ID for the request")
    submitted_at: str = Field(..., description="Submission date (YYYY-MM-DD)")
    source_format: str = Field(default="json")
    status: str = Field(default="pending")
    admission_date: str = Field(..., description="Expected admission date")
    patient: Dict[str, Any]
    policy: Dict[str, Any]
    hospital: Dict[str, Any]
    diagnosis: Dict[str, Any]
    procedure: Dict[str, Any]
    cost_estimate: Dict[str, Any]


@app.post("/api/v1/preauth/process", summary="Process a Pre-Auth Request")
async def process_preauth_request(payload: Dict[str, Any] = Body(
    ...,
    openapi_examples={
        "standard_stemi": {
            "summary": "Standard STEMI Emergency",
            "value": {
                "request_id": "123e4567-e89b-12d3-a456-426614174000",
                "submitted_at": "2025-06-01",
                "source_format": "json",
                "status": "pending",
                "admission_date": "2025-06-01",
                "patient": {
                    "patient_id": "123e4567-e89b-12d3-a456-426614174001",
                    "full_name": "Rajesh Kumar",
                    "age": 45,
                    "gender": "male",
                    "policy_number": "POL-ACTIVE-101"
                },
                "policy": {
                    "policy_number": "POL-ACTIVE-101",
                    "plan_type": "individual",
                    "sum_insured": "500000.00",
                    "policy_start_date": "2023-01-01",
                    "waiting_period_months": 0,
                    "sub_limits": {"limits": {"room_rent_per_day": "5000.00"}},
                    "co_pay_pct": "0.00"
                },
                "hospital": {
                    "hospital_id": "123e4567-e89b-12d3-a456-426614174002",
                    "name": "Synthetic Metro Hospital",
                    "city": "Mumbai",
                    "network_tier": "cashless_network",
                    "category": "multi_specialty"
                },
                "diagnosis": {
                    "icd10_code": "I21.0",
                    "description": "Acute STEMI",
                    "is_pre_existing": False
                },
                "procedure": {
                    "procedure_code": "PCI-001",
                    "description": "Primary PCI with DES",
                    "admission_type": "emergency"
                },
                "cost_estimate": {
                    "line_items": [
                        {"item": "Room Rent", "amount": "4000.00", "category": "room_rent"},
                        {"item": "Surgeon Fee", "amount": "80000.00", "category": "surgeon_fee"}
                    ],
                    "total_amount": "84000.00"
                }
            }
        }
    }
)):
    """
    Submit a JSON payload representing a hospital pre-authorization request.
    
    The payload runs through:
    1. Intake validation (Track 1)
    2. LangGraph state machine & rules engine (Track 2 & 3)
    
    Returns the final adjudication recommendation and reasoning narrative.
    """
    try:
        # 1. Process intake
        # The detect_format logic in process_intake will correctly handle dicts as JSON ("1")
        intake_result = process_intake(payload, format_override="1")
        
        if not intake_result.is_success:
            return {
                "status": "error",
                "message": "Intake validation failed.",
                "validation_errors": intake_result.validation_errors,
            }
            
        # We need to serialize the intake result into a dict to pass into the graph
        # Since IntakeResult is a Pydantic model (or dataclass), we use model_dump
        if hasattr(intake_result, "model_dump"):
            intake_dict = intake_result.model_dump()
        elif hasattr(intake_result, "dict"):
            intake_dict = intake_result.dict()
        else:
            intake_dict = intake_result.__dict__

        # 2. Run LangGraph pipeline
        final_state = run_pipeline(intake_dict)

        # 3. Format response
        return {
            "status": "success",
            "pipeline_status": final_state.get("pipeline_status"),
            "recommendation": final_state.get("recommendation"),
            "confidence": final_state.get("confidence"),
            "needs_escalation": final_state.get("needs_escalation"),
            "escalation_triggers": final_state.get("escalation_triggers", []),
            "reasoning": final_state.get("reasoning_narrative"),
            "adjudication_metrics": final_state.get("adjudication_result", {}),
            "latencies": final_state.get("node_latencies", {}),
        }

    except Exception as e:
        import traceback
        return {
            "status": "error",
            "message": str(e),
            "traceback": traceback.format_exc(),
        }


from fastapi import Request

@app.post("/api/v1/preauth/text", summary="Process Free-Text Request")
async def process_text_request(request: Request):
    """
    Submit raw text (e.g., doctor's clinical notes) for pre-authorization.
    The system will use LLM extraction to populate the structured schema before running rules.
    """
    try:
        body_bytes = await request.body()
        text_content = body_bytes.decode('utf-8').strip()
        
        if not text_content:
            return {"status": "error", "message": "Text payload cannot be empty."}

        intake_result = process_intake(text_content, format_override="6")
        
        if not intake_result.is_success:
            return {
                "status": "error",
                "message": "Text extraction failed.",
                "validation_errors": getattr(intake_result, "validation_errors", [])
            }

        intake_dict = intake_result.model_dump() if hasattr(intake_result, "model_dump") else intake_result.__dict__
        final_state = run_pipeline(intake_dict)

        return {
            "status": "success",
            "extracted_request": intake_dict.get("request"),
            "pipeline_status": final_state.get("pipeline_status"),
            "recommendation": final_state.get("recommendation"),
            "reasoning": final_state.get("reasoning_narrative"),
        }
    except Exception as e:
        import traceback
        return {"status": "error", "message": str(e), "traceback": traceback.format_exc()}


@app.post("/api/v1/preauth/upload", summary="Process File Upload (PDF/Image/DOCX)")
async def process_file_upload(file: UploadFile = File(...)):
    """
    Upload a document (e.g., scanned PDF, image, DOCX) for pre-authorization processing.
    The system will auto-detect the format and run the correct extraction pipeline.
    """
    try:
        # Save file to a temporary location for the intake processor
        suffix = os.path.splitext(file.filename)[1]
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name

        try:
            intake_result = process_intake(tmp_path, original_filename=file.filename)
            
            if not intake_result.is_success:
                return {
                    "status": "error",
                    "message": f"Extraction failed for file {file.filename}.",
                    "validation_errors": getattr(intake_result, "validation_errors", [])
                }

            intake_dict = intake_result.model_dump() if hasattr(intake_result, "model_dump") else intake_result.__dict__
            final_state = run_pipeline(intake_dict)

            return {
                "status": "success",
                "extracted_request": intake_dict.get("request"),
                "pipeline_status": final_state.get("pipeline_status"),
                "recommendation": final_state.get("recommendation"),
                "reasoning": final_state.get("reasoning_narrative"),
            }
        finally:
            os.unlink(tmp_path)
    except Exception as e:
        import traceback
        return {"status": "error", "message": str(e), "traceback": traceback.format_exc()}


@app.get("/health")
async def health_check():
    """Simple health check endpoint."""
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
