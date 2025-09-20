from __future__ import annotations

from datetime import datetime
from typing import Iterable, Optional, List, Dict, Any, Tuple

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


def list_recent_files(limit: int = 100) -> List[Dict[str, Any]]:
    """Devuelve los archivos analizados previamente ordenados por última ejecución."""

    with Session(engine) as session:
        stmt = (
            select(
                AnalysisRun.file_key,
                func.count(AnalysisRun.id),
                func.max(AnalysisRun.created_at),
                func.max(AnalysisRun.id),
            )
            .group_by(AnalysisRun.file_key)
            .order_by(func.max(AnalysisRun.created_at).desc())
        )
        if limit:
            stmt = stmt.limit(limit)
        aggregates = session.exec(stmt).all()

        last_ids = [int(last_run_id) for _, _, _, last_run_id in aggregates if last_run_id is not None]
        runs_by_id: Dict[int, AnalysisRun] = {}
        if last_ids:
            runs = session.exec(select(AnalysisRun).where(AnalysisRun.id.in_(last_ids))).all()
            runs_by_id = {run.id: run for run in runs}

        output: List[Dict[str, Any]] = []
        for file_key, runs, last_run_at, last_run_id in aggregates:
            if not file_key:
                continue
            last_run_id_int = int(last_run_id) if last_run_id is not None else None
            last_run = runs_by_id.get(last_run_id_int) if last_run_id_int else None
            output.append(
                {
                    "file_key": file_key,
                    "figma_url": last_run.figma_url if last_run else None,
                    "runs": int(runs or 0),
                    "last_run_at": last_run_at.isoformat() if last_run_at else None,
                    "last_analysis_id": last_run_id_int,
                    "last_model": last_run.model if last_run else None,
                    "analysis_level": last_run.analysis_level if last_run else None,
                }
            )
        return output


def get_case(case_id: int) -> Optional[StoredTestCase]:
    with Session(engine) as session:
        return session.get(StoredTestCase, case_id)


def delete_case(case_id: int) -> bool:
    with Session(engine) as session:
        case = session.get(StoredTestCase, case_id)
        if not case:
            return False
        run = session.get(AnalysisRun, case.run_id) if case.run_id else None
        session.delete(case)
        if run:
            run.total_cases = max((run.total_cases or 0) - 1, 0)
            run.updated_at = datetime.utcnow()
            session.add(run)
        session.commit()
        return True


def _to_gpt_case(data: Dict[str, Any]) -> GPTCase:
    try:
        return GPTCase.model_validate(data)
    except AttributeError:  # pragma: no cover - pydantic < 2
        return GPTCase.parse_obj(data)  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover - datos incompletos
        allowed = getattr(GPTCase, "model_fields", None)
        if allowed:
            filtered = {k: v for k, v in data.items() if k in allowed}
        else:  # pragma: no cover - compatibilidad pydantic < 2
            filtered = {k: v for k, v in data.items() if k in GPTCase.__fields__}
        return GPTCase(**filtered)  # type: ignore[arg-type]


def get_analysis_bundles(run_id: int) -> List[CasesBundle]:
    with Session(engine) as session:
        cases = session.exec(
            select(StoredTestCase)
            .where(StoredTestCase.run_id == run_id)
            .order_by(StoredTestCase.bundle_label, StoredTestCase.case_index, StoredTestCase.id)
        ).all()

    bundles: Dict[Tuple[str, str, str], CasesBundle] = {}
    for case in cases:
        key = (case.page_name, case.frame_name, case.node_id)
        bundle = bundles.get(key)
        if not bundle:
            bundle = CasesBundle(page_name=case.page_name, frame_name=case.frame_name, node_id=case.node_id, cases=[])
            bundles[key] = bundle
        payload = dict(case.case_data or {})
        gpt_case = _to_gpt_case(payload)
        bundle.cases.append(gpt_case)
    return list(bundles.values())


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
