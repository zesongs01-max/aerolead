"""
Discovery API Router
Provides the /web/discover endpoint that runs the web scraping pipeline.
"""

import threading
import uuid
from typing import Dict, Any
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import SessionLocal, Tenant
from app.discovery import run_discovery_pipeline

router = APIRouter(prefix="/web")

# In-memory job store: job_id -> { status, progress, result }
_jobs: Dict[str, dict] = {}


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _run_job(job_id: str, query: str, location: str, required_techs: list, max_results: int, tenant_id: str):
    """Runs the discovery pipeline in a background thread and deducts credits."""
    db = SessionLocal()
    try:
        def on_progress(msg: str):
            _jobs[job_id]["progress"].append(msg)

        result = run_discovery_pipeline(
            db=db,
            query=query,
            location=location,
            required_techs=required_techs,
            max_results=max_results,
            progress_callback=on_progress,
        )
        
        # Deduct credits: 1 credit per company found
        companies_found = result.get("companies_found", 0)
        if tenant_id and companies_found > 0:
            tenant = db.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()
            if tenant:
                charge = round(companies_found * 1.0, 2)
                tenant.credit_balance = max(0.0, round(tenant.credit_balance - charge, 2))
                db.commit()
                _jobs[job_id]["progress"].append(f"💳 Charged {charge} credits for discovering {companies_found} companies.")

        _jobs[job_id]["status"] = "complete"
        _jobs[job_id]["result"] = result
    except Exception as e:
        _jobs[job_id]["status"] = "error"
        _jobs[job_id]["error"] = str(e)
    finally:
        db.close()


@router.post("/discover/start")
def start_discovery(payload: Dict[str, Any], db: Session = Depends(get_db)):
    """
    Kicks off a background discovery job.
    Returns a job_id that can be polled for progress.
    """
    query = payload.get("query", "").strip()
    location = payload.get("location", "").strip()
    required_techs = payload.get("required_techs", [])
    max_results = int(payload.get("max_results", 15))
    tenant_id = payload.get("tenant_id")

    if not query:
        return {"error": "query is required"}

    if tenant_id:
        tenant = db.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()
        if tenant and tenant.credit_balance < 1.0:
            return {"error": "Insufficient credits to start web discovery."}

    job_id = uuid.uuid4().hex
    _jobs[job_id] = {
        "status": "running",
        "progress": [],
        "result": None,
        "error": None,
    }

    thread = threading.Thread(
        target=_run_job,
        args=(job_id, query, location, required_techs, max_results, tenant_id),
        daemon=True,
    )
    thread.start()

    return {"job_id": job_id, "status": "started"}


@router.get("/discover/status/{job_id}")
def get_discovery_status(job_id: str):
    """
    Polls the status and progress logs of a running discovery job.
    """
    job = _jobs.get(job_id)
    if not job:
        return {"error": "Job not found"}

    return {
        "status": job["status"],
        "progress": job["progress"],
        "result": job["result"],
        "error": job["error"],
    }
