from datetime import datetime
from typing import Optional, List

from sqlalchemy import Column, JSON
from sqlmodel import Field, Relationship, SQLModel


class StoredTestCase(SQLModel, table=True):
    __tablename__ = "stored_test_cases"

    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="analysis_runs.id", index=True)
    page_name: str
    frame_name: str
    node_id: str
    bundle_label: Optional[str] = Field(default=None, index=True)
    case_index: int = Field(default=0)
    case_data: dict = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    evaluated: bool = Field(default=False)
    status: str = Field(default="pending")
    score: Optional[float] = Field(default=None)
    notes: Optional[str] = Field(default=None)
    checked: bool = Field(default=False)

    run: "AnalysisRun" = Relationship(back_populates="cases")


class AnalysisRun(SQLModel, table=True):
    __tablename__ = "analysis_runs"

    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: str = Field(index=True)
    file_key: str = Field(index=True)
    figma_url: Optional[str] = Field(default=None)
    analysis_level: str
    model: str
    images_per_unit: int
    image_scale: float
    reasoning_effort: Optional[str] = None
    max_frames: Optional[int] = Field(default=None)
    status: str = Field(default="completed")
    total_cases: int = Field(default=0)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    cases: List["StoredTestCase"] = Relationship(back_populates="run")


def serialize_case_payload(case: StoredTestCase) -> dict:
    base = dict(case.case_data or {})
    base.setdefault("page_name", case.page_name)
    base.setdefault("frame_name", case.frame_name)
    base.setdefault("node_id", case.node_id)
    base.setdefault("bundle_label", case.bundle_label)
    base.setdefault("image_url", base.get("image_url"))
    base["evaluation"] = {
        "evaluated": case.evaluated,
        "status": case.status,
        "score": case.score,
        "notes": case.notes,
        "checked": case.checked,
        "case_id": case.id,
    }
    return base
