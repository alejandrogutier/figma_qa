from __future__ import annotations

import threading
import time
from typing import Dict, Optional, Any, List

from pydantic import BaseModel, Field

from .models import CasesBundle


class JobStatus(BaseModel):
    job_id: str
    status: str = Field(default="queued")  # queued | in_progress | completed | failed
    message: Optional[str] = None
    stage: Optional[str] = None  # list_frames | render_images | fetch_nodes | generate | build_excel | completed
    file_key: Optional[str] = None
    frames_total: int = 0
    frames_processing: int = 0
    processed: int = 0
    cases_total: int = 0
    started_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
    error: Optional[str] = None
    output_path: Optional[str] = None
    results: Optional[List[CasesBundle]] = None
    analysis_id: Optional[int] = None


_JOBS: Dict[str, JobStatus] = {}
_LOCK = threading.Lock()


def create_job(job_id: str, *, file_key: Optional[str] = None) -> JobStatus:
    with _LOCK:
        st = JobStatus(job_id=job_id, status="queued", file_key=file_key)
        _JOBS[job_id] = st
        return st


def get_job(job_id: str) -> Optional[JobStatus]:
    with _LOCK:
        st = _JOBS.get(job_id)
        return JobStatus(**st.model_dump()) if st else None


def update_job(job_id: str, **kwargs: Any) -> Optional[JobStatus]:
    with _LOCK:
        st = _JOBS.get(job_id)
        if not st:
            return None
        for k, v in kwargs.items():
            if hasattr(st, k):
                setattr(st, k, v)
        st.updated_at = time.time()
        return JobStatus(**st.model_dump())


def set_progress(job_id: str, *, processed: Optional[int] = None, message: Optional[str] = None, cases_inc: int = 0):
    with _LOCK:
        st = _JOBS.get(job_id)
        if not st:
            return None
        if processed is not None:
            st.processed = processed
        if cases_inc:
            st.cases_total += cases_inc
        if message is not None:
            st.message = message
        st.updated_at = time.time()
        return JobStatus(**st.model_dump())


def set_error(job_id: str, error: str):
    with _LOCK:
        st = _JOBS.get(job_id)
        if not st:
            return None
        st.status = "failed"
        st.error = error
        st.updated_at = time.time()
        return JobStatus(**st.model_dump())


def set_completed(
    job_id: str,
    output_path: Optional[str] = None,
    *,
    results: Optional[List[CasesBundle]] = None,
    analysis_id: Optional[int] = None,
):
    with _LOCK:
        st = _JOBS.get(job_id)
        if not st:
            return None
        st.status = "completed"
        st.output_path = output_path
        st.results = results
        st.analysis_id = analysis_id
        st.updated_at = time.time()
        return JobStatus(**st.model_dump())
