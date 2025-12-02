# api/main.py
import uuid
import threading
from typing import Dict, Any, Optional
from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from crew import TestGeneration

app = FastAPI()

jobs: Dict[str, Dict[str, Any]] = {}

class GenerateRequest(BaseModel):
    url: str

class JobStatus(BaseModel):
    status: str
    result: Optional[str] = None
    error: Optional[str] = None

@app.post("/start_job", response_model=Dict[str, str])
def start_job(req: GenerateRequest):
    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "pending", "result": None, "error": None}

    def _run():
        try:
            jobs[job_id]["status"] = "running"

            result = TestGeneration().crew().kickoff(inputs={"url": req.url})

            # *** FIX — Extract final raw output only ***
            if hasattr(result, "raw"):
                final_output = result.raw
            else:
                final_output = str(result)

            jobs[job_id]["status"] = "done"
            jobs[job_id]["result"] = final_output

        except Exception as e:
            jobs[job_id]["status"] = "error"
            jobs[job_id]["error"] = str(e)

    threading.Thread(target=_run, daemon=True).start()

    return {"job_id": job_id}


@app.get("/job_status/{job_id}", response_model=JobStatus)
def job_status(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobStatus(**job)


@app.get("/get_result/{job_id}", response_class=PlainTextResponse)
def get_result(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job["status"] != "done":
        return PlainTextResponse("Pending...")

    return PlainTextResponse(job["result"])