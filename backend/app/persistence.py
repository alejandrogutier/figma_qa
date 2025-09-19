from __future__ import annotations

from datetime import datetime
from typing import Iterable, Optional

from sqlalchemy import func
from sqlmodel import Session, select

from .db import engine
from .db_models import AnalysisRun, StoredTestCase, serialize_case_payload
from .models import AnalyzeRequest, CasesBundle, GPTCase


def _dump_case(case: GPTCase) -> dict:
    try:
        return case.model_dump()
    except AttributeError:  # pragma: no cover - legacy pydantic support
        return case.dict()  # type: ignore[attr-defined]


def persist_analysis(
    job_id: str,
    request: AnalyzeRequest,
    file_key: str,
    bundles: Iterable[CasesBundle],
) -> int:
    bundles_list = list(bundles)
    total_cases = sum(len(bundle.cases) for bundle in bundles_list)
    run = AnalysisRun(
        job_id=job_id,
        file_key=file_key,
        figma_url=request.figma_url,
        analysis_level=request.analysis_level,
        model=request.model,
        images_per_unit=request.images_per_unit,
        image_scale=request.image_scale,
        reasoning_effort=request.reasoning_effort,
        status="completed",
        total_cases=total_cases,
        max_frames=request.max_frames,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    with Session(engine) as session:
        session.add(run)
        session.commit()
        session.refresh(run)

        for bundle_idx, bundle in enumerate(bundles_list):
            for case_idx, case in enumerate(bundle.cases):
                payload = _dump_case(case)
                stored_case = StoredTestCase(
                    run_id=run.id,
                    page_name=bundle.page_name,
                    frame_name=bundle.frame_name,
                    node_id=bundle.node_id,
                    bundle_label=bundle.frame_name,
                    case_index=case_idx,
                    case_data=payload,
                )
                session.add(stored_case)
        session.commit()
        return run.id


def list_analyses(limit: int = 50, file_key: Optional[str] = None) -> list[dict]:
    with Session(engine) as session:
        statement = select(AnalysisRun).order_by(AnalysisRun.created_at.desc())
        if file_key:
            statement = statement.where(AnalysisRun.file_key == file_key)
        statement = statement.limit(limit)
        runs = list(session.exec(statement))
        return [analysis_to_response(run, include_cases=False) for run in runs]


def get_analysis_response(run_id: int, include_cases: bool = True) -> Optional[dict]:
    with Session(engine) as session:
        run = session.get(AnalysisRun, run_id)
        if not run:
            return None
        if include_cases:
            cases = list(
                session.exec(
                    select(StoredTestCase).where(StoredTestCase.run_id == run_id).order_by(
                        StoredTestCase.bundle_label, StoredTestCase.case_index
                    )
                )
            )
            run.cases = cases  # type: ignore[assignment]
        return analysis_to_response(run, include_cases=include_cases)


def get_analysis_summary_by_file(file_keys: Optional[Iterable[str]] = None) -> dict[str, dict]:
    with Session(engine) as session:
        statement = select(
            AnalysisRun.file_key,
            func.count(AnalysisRun.id),
            func.max(AnalysisRun.created_at),
            func.max(AnalysisRun.id),
        )
        if file_keys:
            statement = statement.where(AnalysisRun.file_key.in_(list(file_keys)))
        statement = statement.group_by(AnalysisRun.file_key)
        results = session.exec(statement).all()
        summary: dict[str, dict] = {}
        for file_key, count, last_run, last_run_id in results:
            summary[file_key] = {
                "runs": int(count or 0),
                "last_run_at": last_run.isoformat() if last_run else None,
                "last_analysis_id": int(last_run_id) if last_run_id else None,
            }
        return summary


def delete_analysis(run_id: int) -> bool:
    with Session(engine) as session:
        run = session.get(AnalysisRun, run_id)
        if not run:
            return False
        # delete dependent cases explicitly to avoid FK issues when cascade is not configured
        cases = session.exec(
            select(StoredTestCase).where(StoredTestCase.run_id == run_id)
        ).all()
        for case in cases:
            session.delete(case)
        session.delete(run)
        session.commit()
        return True


def update_case_evaluation(
    case_id: int,
    *,
    evaluated: Optional[bool] = None,
    status: Optional[str] = None,
    score: Optional[float] = None,
    score_set: bool = False,
    notes: Optional[str] = None,
    checked: Optional[bool] = None,
) -> Optional[StoredTestCase]:
    with Session(engine) as session:
        case = session.get(StoredTestCase, case_id)
        if not case:
            return None
        if evaluated is not None:
            case.evaluated = evaluated
        if status is not None:
            case.status = status
        if score_set:
            case.score = score
        if notes is not None:
            case.notes = notes
        if checked is not None:
            case.checked = checked
        case.updated_at = datetime.utcnow()
        session.add(case)
        if case.run_id:
            run = session.get(AnalysisRun, case.run_id)
            if run:
                run.updated_at = datetime.utcnow()
                session.add(run)
        session.commit()
        session.refresh(case)
        return case


def analysis_to_response(run: AnalysisRun, include_cases: bool = True) -> dict:
    data = {
        "analysis_id": run.id,
        "job_id": run.job_id,
        "file_key": run.file_key,
        "figma_url": run.figma_url,
        "analysis_level": run.analysis_level,
        "model": run.model,
        "images_per_unit": run.images_per_unit,
        "image_scale": run.image_scale,
        "reasoning_effort": run.reasoning_effort,
        "max_frames": run.max_frames,
        "status": run.status,
        "total_cases": run.total_cases,
        "created_at": run.created_at.isoformat(),
        "updated_at": run.updated_at.isoformat(),
    }
    if include_cases:
        sorted_cases = sorted(
            run.cases,
            key=lambda c: (c.bundle_label or "", c.case_index),
        )
        data["cases"] = [serialize_case_payload(case) for case in sorted_cases]
    return data
