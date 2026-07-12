"""
Discovery API Router
Provides the /web/discover endpoint that runs the web scraping pipeline.
"""

import threading
import uuid
from typing import Dict, Any
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import SessionLocal
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


def _run_job(job_id: str, query: str, location: str, required_techs: list, max_results: int):
    """Runs the discovery pipeline in a background thread."""
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
        _jobs[job_id]["status"] = "complete"
        _jobs[job_id]["result"] = result
    except Exception as e:
        _jobs[job_id]["status"] = "error"
        _jobs[job_id]["error"] = str(e)
    finally:
        db.close()


@router.post("/discover/start")
def start_discovery(payload: Dict[str, Any]):
    """
    Kicks off a background discovery job.
    Returns a job_id that can be polled for progress.
    """
    query = payload.get("query", "").strip()
    location = payload.get("location", "").strip()
    required_techs = payload.get("required_techs", [])
    max_results = int(payload.get("max_results", 15))

    if not query:
        return {"error": "query is required"}

    job_id = uuid.uuid4().hex
    _jobs[job_id] = {
        "status": "running",
        "progress": [],
        "result": None,
        "error": None,
    }

    thread = threading.Thread(
        target=_run_job,
        args=(job_id, query, location, required_techs, max_results),
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
