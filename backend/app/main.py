from __future__ import annotations

import asyncio
import logging
import time
import uuid
import os
import tempfile
from typing import Any, Dict, List

import httpx
from fastapi import FastAPI, HTTPException, Header, Query
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from pydantic import ValidationError
from starlette.background import BackgroundTask
from fastapi.middleware.cors import CORSMiddleware

from .figma_client import (
    extract_file_key,
    list_frames,
    list_pages,
    get_images_for_nodes,
    get_nodes_details,
    summarize_frame_document,
    group_frames_by_section_or_prefix,
)
from .gpt import generate_cases, generate_cases_for_page, generate_cases_for_group
from .models import (
    AnalyzeRequest,
    CasesBundle,
    FrameSummary,
    PageSummary,
    UpdateCaseRequest,
    RerunAnalysisRequest,
)
from .excel import build_workbook
from .oauth import build_authorize_url, exchange_code_for_token, refresh_access_token
from .jobs import create_job, get_job, update_job, set_progress, set_error, set_completed
from .db import init_db
from .persistence import (
    persist_analysis,
    list_analyses,
    get_analysis_response,
    delete_analysis,
    update_case_evaluation,
    get_analysis_summary_by_file,
    list_recent_files,
    get_case,
    delete_case,
    get_analysis_bundles,
)
from .db_models import serialize_case_payload
from . import db_models  # noqa: F401 - ensure SQLModel tables are registered



from dotenv import load_dotenv


load_dotenv()
init_db()

# Config de logging simple con timestamps
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")

oauth_logger = logging.getLogger("app.oauth")
analyze_logger = logging.getLogger("app.analyze")
oauth_logger.setLevel(logging.INFO)
analyze_logger.setLevel(logging.INFO)


app = FastAPI(title="Figma QA Case Generator", version="0.1.0")

# CORS para frontend local (configurable)
frontend_origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/")
async def root():
    return {"service": "figma-qa", "docs": "/docs", "health": "/health"}


@app.post("/analyze")
async def analyze(req: AnalyzeRequest, authorization: str | None = Header(default=None)):
    job_id = uuid.uuid4().hex[:8]
    analyze_logger.info(
        "[%s] Analyze request received. figma_url=%s file_key=%s model=%s image_scale=%s max_frames=%s",
        job_id,
        getattr(req, 'figma_url', None), getattr(req, 'file_key', None), req.model, req.image_scale, req.max_frames,
    )
    try:
        file_key = extract_file_key(req.file_key or req.figma_url or "")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    openai_key = os.getenv("OPENAI_API_KEY")
    if not openai_key:
        raise HTTPException(
            status_code=500,
            detail="Falta OPENAI_API_KEY en el entorno del servidor",
        )

    # Selecciona token de Figma: body o Authorization: Bearer
    bearer_token = None
    if authorization and authorization.lower().startswith("bearer "):
        bearer_token = authorization.split(" ", 1)[1].strip()

    token = req.figma_token or bearer_token
    if not token:
        raise HTTPException(status_code=400, detail="Falta figma_token o cabecera Authorization: Bearer")

    # Ejecutar como job en background
    create_job(job_id, file_key=file_key)
    update_job(job_id, status="in_progress", message="Iniciando análisis…")

    async def _run_job():
        t0 = time.perf_counter()
        try:
            def _normalize_label(name: str) -> str:
                if not name:
                    return ""
                s = name.strip().lower()
                # corta por separadores comunes de variantes
                import re as _re
                s = _re.split(r"[\/|>:·-]", s)[0].strip()
                s = _re.sub(r"\b(primary|secondary|tertiary|default|filled|outlined|ghost|success|warning|error|info|active|inactive|disabled)\b", "", s).strip()
                s = _re.sub(r"\s+", " ", s)
                return s or name.strip().lower()
            async with httpx.AsyncClient() as client:
                frames_info = await list_frames(client, token, file_key)
                if not frames_info:
                    update_job(job_id, status="failed", message="No se encontraron frames en el archivo")
                    return
                total_frames = len(frames_info)
                # Agrupa por página si aplica
                by_page: dict[str, dict] = {}
                for p_name, p_id, f, nid in frames_info:
                    entry = by_page.setdefault(p_id, {"name": p_name, "items": []})
                    entry["items"].append((f, nid))

                # Construye unidades de trabajo: páginas o frames (group/section se construyen más abajo)
                if req.analysis_level == "page":
                    units = [(v["name"], v["items"]) for v in by_page.values()]
                    update_job(
                        job_id,
                        frames_total=total_frames,
                        frames_processing=len(units),
                        message=f"Unidades a procesar: {len(units)} (nivel: {req.analysis_level})",
                        stage="prepare",
                    )
                elif req.analysis_level == "frame":
                    frames_limited = frames_info[: (req.max_frames or len(frames_info))]
                    units = [(p_name, [(f, nid)]) for (p_name, p_id, f, nid) in frames_limited]
                    update_job(
                        job_id,
                        frames_total=total_frames,
                        frames_processing=len(units),
                        message=f"Unidades a procesar: {len(units)} (nivel: {req.analysis_level})",
                        stage="prepare",
                    )
                else:
                    units = []  # se definirán tras armar groups_units
                analyze_logger.info(
                    "[%s] Analyze start file=%s frames_total=%s pages=%s units=%s level=%s image_scale=%s model=%s",
                    job_id,
                    file_key,
                    total_frames,
                    len(by_page),
                    len(units),
                    req.analysis_level,
                    req.image_scale,
                    req.model,
                )

                # Nodes (detalles de todos los frames) – primero para poder agrupar por grupos
                t_nodes = time.perf_counter()
                update_job(job_id, message="Obteniendo detalles de nodos…", stage="fetch_nodes")
                all_frame_node_ids = [nid for _, _, _, nid in frames_info]
                nodes_payload = await get_nodes_details(client, token, file_key, all_frame_node_ids)
                nodes_map = nodes_payload.get("nodes") or {}
                analyze_logger.info(
                    "[%s] Nodes details fetched for %s frames in %.2fs",
                    job_id, len(nodes_map), time.perf_counter() - t_nodes,
                )
                update_job(job_id, message=f"Detalles de {len(nodes_map)} nodos listos…", stage="fetch_nodes_done")

            # Construcción de unidades por grupo/section (después de tener nodes_map)
            if req.analysis_level == "group":
                groups_units: list[tuple[str, str, list[tuple[str, str]]]] = []
                max_groups_per_page = int(os.getenv("MAX_GROUPS_PER_PAGE", "8"))
                for p_id, meta in by_page.items():
                    p_name = meta["name"]
                    items = meta["items"]
                    label_map: dict[str, list[tuple[str, str]]] = {}
                    for frame_name, node_id in items:
                        node = nodes_map.get(node_id) or {}
                        doc = node.get("document") or {}
                        _, elements = summarize_frame_document(doc)
                        labels = []
                        for e in elements:
                            t = (e.get("type") or "").lower()
                            nm = (e.get("name") or "").strip()
                            if t in ("component", "group") and nm:
                                labels.append(_normalize_label(nm))
                        labels = list(dict.fromkeys(labels))
                        for lab in labels:
                            label_map.setdefault(lab, []).append((frame_name, node_id))
                    # top-N grupos por página por cantidad de frames
                    sorted_groups = sorted(label_map.items(), key=lambda kv: len(kv[1]), reverse=True)
                    chosen = sorted_groups[:max_groups_per_page]
                    for lab, frames_list in chosen:
                        seen = set()
                        uniq = []
                        for fr_name, nid in frames_list:
                            if nid in seen:
                                continue
                            seen.add(nid)
                            uniq.append((fr_name, nid))
                        groups_units.append((p_name, lab or "(otros)", uniq))
                analyze_logger.info("[%s] Group mode: pages=%s groups_selected=%s (max_per_page=%s)", job_id, len(by_page), len(groups_units), max_groups_per_page)
            elif req.analysis_level == "section":
                # Agrupa por SECTION; para frames sin sección, agrupa por prefijo de nombre.
                groups_units: list[tuple[str, str, list[tuple[str, str]]]] = []
                max_groups_per_page = int(os.getenv("MAX_SECTIONS_PER_PAGE", "10"))
                min_group_size = int(os.getenv("MIN_FRAMES_PER_UNIT", "2"))
                # Necesitamos los documentos de página para detectar SECTIONs
                async with httpx.AsyncClient() as client:
                    pages = await list_pages(client, token, file_key)
                    page_ids = [pid for _, pid in pages]
                    payload = await get_nodes_details(client, token, file_key, page_ids)
                    pages_map = payload.get("nodes") or {}
                for p_id, meta in by_page.items():
                    p_name = meta["name"]
                    items = meta["items"]  # [(frame_name, node_id)]
                    node = pages_map.get(p_id) or {}
                    doc = node.get("document") or {}
                    groups_for_page = group_frames_by_section_or_prefix(doc, items, min_group_size=min_group_size)
                    # Top N por cantidad de frames
                    sorted_groups = sorted(groups_for_page, key=lambda kv: len(kv[1]), reverse=True)
                    chosen = sorted_groups[:max_groups_per_page]
                    for label, frames_list in chosen:
                        uniq = []
                        seen = set()
                        for fr_name, nid in frames_list:
                            if nid in seen:
                                continue
                            seen.add(nid)
                            uniq.append((fr_name, nid))
                        groups_units.append((p_name, label, uniq))
                # Límite global de unidades por sección (top por tamaño)
                max_sections_global = int(os.getenv("MAX_SECTIONS_GLOBAL", "12"))
                groups_units = sorted(groups_units, key=lambda x: len(x[2]), reverse=True)
                if max_sections_global > 0:
                    groups_units = groups_units[:max_sections_global]
                analyze_logger.info(
                    "[%s] Section mode: pages=%s groups_selected=%s (max_per_page=%s max_global=%s)",
                    job_id, len(by_page), len(groups_units), max_groups_per_page, max_sections_global,
                )
                update_job(
                    job_id,
                    frames_total=total_frames,
                    frames_processing=len(groups_units),
                    message=f"Unidades a procesar: {len(groups_units)} (nivel: section)",
                )
            # Límite global para modo group
            if req.analysis_level == "group":
                max_groups_global = int(os.getenv("MAX_GROUPS_GLOBAL", "12"))
                groups_units = sorted(groups_units, key=lambda x: len(x[2]), reverse=True)
                if max_groups_global > 0:
                    groups_units = groups_units[:max_groups_global]
                update_job(
                    job_id,
                    frames_total=total_frames,
                    frames_processing=len(groups_units),
                    message=f"Unidades a procesar: {len(groups_units)} (nivel: group)",
                )

            # Ahora que tenemos units (o groups_units), calcula los nodeIds de imágenes a renderizar
            limit_images = 12
            if req.analysis_level in ("group", "section"):
                image_node_ids: list[str] = []
                for _, _, items in groups_units:
                    for _, nid in items[:limit_images]:
                        image_node_ids.append(nid)
                image_node_ids = list(dict.fromkeys(image_node_ids))
            else:
                image_node_ids = []
                for _, items in units:
                    pick = items[:limit_images] if req.analysis_level == "page" else items[:1]
                    for _, nid in pick:
                        image_node_ids.append(nid)
                image_node_ids = list(dict.fromkeys(image_node_ids))

            t_imgs = time.perf_counter()
            update_job(job_id, message=f"Renderizando imágenes ({len(image_node_ids)} nodos)…", stage="render_images")
            async with httpx.AsyncClient() as client:
                images_map = await get_images_for_nodes(
                    client, token, file_key, image_node_ids, scale=req.image_scale
                )
            analyze_logger.info(
                "[%s] Images resolved for %s/%s nodes in %.2fs",
                job_id, len(images_map), len(image_node_ids), time.perf_counter() - t_imgs,
            )
            update_job(job_id, message=f"Imágenes listas ({len(images_map)})…", stage="render_images_done")

            bundles: List[CasesBundle] = []
            if req.analysis_level in ("group", "section"):
                limit_images = 12
                for idx, (page_name, group_label, items) in enumerate(groups_units, start=1):
                    t_frame = time.perf_counter()
                    unit_noun = "grupo" if req.analysis_level == "group" else "sección"
                    set_progress(job_id, processed=idx - 1, message=f"Procesando {unit_noun} {idx}/{len(groups_units)}…")
                    analyze_logger.info(
                        "[%s] Processing %s %s/%s page=%s label=%s frames_in_unit=%s",
                        job_id, unit_noun, idx, len(groups_units), page_name, group_label, len(items),
                    )
                    page_fs: List[FrameSummary] = []
                    for frame_name, node_id in items[: limit_images]:
                        node = nodes_map.get(node_id) or {}
                        doc = node.get("document") or {}
                        texts, elements = summarize_frame_document(doc)
                        image_url = images_map.get(node_id)
                        if not image_url:
                            continue
                        page_fs.append(
                            FrameSummary(
                                file_key=file_key,
                                page_name=page_name,
                                frame_name=frame_name,
                                node_id=node_id,
                                image_url=image_url,
                                texts=texts,
                                elements=[{"type": e.get("type"), "name": e.get("name")} for e in elements],
                            )
                        )
                    ps = PageSummary(file_key=file_key, page_name=page_name, frames=page_fs)
                    try:
                        cases = await asyncio.to_thread(
                            generate_cases_for_group, ps, group_label, model=req.model, images_per_unit=limit_images
                        )
                        analyze_logger.info(
                            "[%s] Generated %s cases for label=%s in %.2fs",
                            job_id, len(cases), group_label, time.perf_counter() - t_frame,
                        )
                    except Exception as e:
                        analyze_logger.error("[%s] GPT error unit_label=%s error=%s", job_id, group_label, e)
                        cases = []
                    bundles.append(
                        CasesBundle(page_name=page_name, frame_name=(f"[GROUP] {group_label}" if req.analysis_level == "group" else f"[SECTION] {group_label}"), node_id=(items[0][1] if items else f"label:{group_label}"), cases=cases)
                    )
                    set_progress(job_id, processed=idx, cases_inc=len(cases))
            else:
                for idx, (page_name, items) in enumerate(units, start=1):
                    t_frame = time.perf_counter()
                    unit_label = "página" if req.analysis_level == "page" else "frame"
                    set_progress(job_id, processed=idx - 1, message=f"Procesando {unit_label} {idx}/{len(units)}…")
                    update_job(job_id, stage="generate")
                    if req.analysis_level == "page":
                        analyze_logger.info(
                            "[%s] Processing page %s/%s name=%s frames_in_page=%s",
                            job_id, idx, len(units), page_name, len(items),
                        )
                        page_fs: List[FrameSummary] = []
                        for frame_name, node_id in items[: req.images_per_unit]:
                            node = nodes_map.get(node_id) or {}
                            doc = node.get("document") or {}
                            texts, elements = summarize_frame_document(doc)
                            image_url = images_map.get(node_id)
                            if not image_url:
                                continue
                            page_fs.append(
                                FrameSummary(
                                    file_key=file_key,
                                    page_name=page_name,
                                    frame_name=frame_name,
                                    node_id=node_id,
                                    image_url=image_url,
                                    texts=texts,
                                    elements=[{"type": e.get("type"), "name": e.get("name")} for e in elements],
                                )
                            )
                        ps = PageSummary(file_key=file_key, page_name=page_name, frames=page_fs)
                        try:
                            cases = await asyncio.to_thread(
                                generate_cases_for_page, ps, model=req.model, images_per_unit=req.images_per_unit, reasoning_effort=req.reasoning_effort
                            )
                            analyze_logger.info(
                                "[%s] Generated %s cases for page %s in %.2fs",
                                job_id, len(cases), page_name, time.perf_counter() - t_frame,
                            )
                            # Fallback: si la página no generó casos, intenta por frames seleccionados
                            if not cases:
                                fcases = []
                                for frame_name, node_id in items[: req.images_per_unit]:
                                    node = nodes_map.get(node_id) or {}
                                    doc = node.get("document") or {}
                                    texts, elements = summarize_frame_document(doc)
                                    image_url = images_map.get(node_id)
                                    if not image_url:
                                        continue
                                    fs = FrameSummary(
                                        file_key=file_key,
                                        page_name=page_name,
                                        frame_name=frame_name,
                                        node_id=node_id,
                                        image_url=image_url,
                                        texts=texts,
                                        elements=[{"type": e.get("type"), "name": e.get("name")} for e in elements],
                                    )
                                    try:
                                        part = await asyncio.to_thread(generate_cases, fs, model=req.model, reasoning_effort=req.reasoning_effort)
                                        fcases.extend(part)
                                    except Exception as e:
                                        analyze_logger.error("[%s] Fallback GPT error frame id=%s error=%s", job_id, node_id, e)
                                if fcases:
                                    cases = fcases
                                    analyze_logger.info("[%s] Fallback produced %s cases for page %s", job_id, len(cases), page_name)
                                else:
                                    update_job(job_id, message=f"Sin casos en página '{page_name}'. Prueba subir images_per_unit o cambiar modelo.")
                        except Exception as e:
                            analyze_logger.error("[%s] GPT error page=%s error=%s", job_id, page_name, e)
                            cases = []
                        bundles.append(
                            CasesBundle(
                                page_name=page_name,
                                frame_name=f"[PAGE] {page_name}",
                                node_id=(items[0][1] if items else f"page:{page_name}"),
                                cases=cases,
                            )
                        )
                        set_progress(job_id, processed=idx, cases_inc=len(cases))
                        continue
                    # frame mode
                    frame_name, node_id = items[0]
                    analyze_logger.info(
                        "[%s] Processing frame %s/%s page=%s frame=%s id=%s",
                        job_id, idx, len(units), page_name, frame_name, node_id,
                    )
                    node = nodes_map.get(node_id) or {}
                    doc = node.get("document") or {}
                    texts, elements = summarize_frame_document(doc)
                    image_url = images_map.get(node_id)
                    if not image_url:
                        analyze_logger.warning("[%s] Skipping frame without image_url id=%s", job_id, node_id)
                        continue
                    summary = FrameSummary(
                        file_key=file_key,
                        page_name=page_name,
                        frame_name=frame_name,
                        node_id=node_id,
                        image_url=image_url,
                        texts=texts,
                        elements=[{"type": e.get("type"), "name": e.get("name")} for e in elements],
                    )
                    try:
                        cases = await asyncio.to_thread(generate_cases, summary, model=req.model, reasoning_effort=req.reasoning_effort)
                        analyze_logger.info(
                            "[%s] Generated %s cases for frame id=%s in %.2fs",
                            job_id, len(cases), node_id, time.perf_counter() - t_frame,
                        )
                    except Exception as e:
                        analyze_logger.error("[%s] GPT error frame id=%s error=%s", job_id, node_id, e)
                        cases = []
                    bundles.append(CasesBundle(page_name=page_name, frame_name=frame_name, node_id=node_id, cases=cases))
                    set_progress(job_id, processed=idx, cases_inc=len(cases))

            if not bundles:
                update_job(job_id, status="failed", message="No se pudieron generar casos (sin imágenes o sin frames)")
                return

            t_xlsx = time.perf_counter()
            update_job(job_id, stage="build_excel", message="Construyendo Excel…")
            tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
            tmp_path = tmp.name
            tmp.close()
            analysis_id = await asyncio.to_thread(persist_analysis, job_id, req, file_key, bundles)
            await asyncio.to_thread(build_workbook, bundles, tmp_path)
            analyze_logger.info(
                "[%s] Analyze done file=%s bundles=%s cases=%s output=%s total_time=%.2fs xlsx_time=%.2fs",
                job_id,
                file_key,
                len(bundles),
                sum(len(b.cases) for b in bundles),
                tmp_path,
                time.perf_counter() - t0,
                time.perf_counter() - t_xlsx,
            )
            set_completed(job_id, tmp_path, results=bundles, analysis_id=analysis_id)
            update_job(job_id, message="Listo para descargar", stage="completed")
        except Exception as e:
            set_error(job_id, str(e))
            update_job(job_id, message=str(e), stage="failed")

    asyncio.create_task(_run_job())
    return {"job_id": job_id, "status_url": f"/jobs/{job_id}", "download_url": None}


@app.get("/oauth/figma/start")
async def oauth_figma_start(state: str = Query(default="state")):
    try:
        url = build_authorize_url(state=state)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"authorize_url": url}


@app.get("/oauth/figma/callback")
async def oauth_figma_callback(code: str, state: str | None = None):
    post_redirect = os.getenv("FIGMA_POST_LOGIN_REDIRECT")
    try:
        token = await exchange_code_for_token(code)
        oauth_logger.info("OAuth success. state=%s token_keys=%s", state, ",".join(sorted([k for k in token.keys() if k.endswith('_token') or k in ('token_type','expires_in','scope')])))
        # Redirige al frontend si FIGMA_POST_LOGIN_REDIRECT está configurado
        if post_redirect:
            from urllib.parse import urlencode

            qs = urlencode(
                {
                    k: v
                    for k, v in token.items()
                    if k in ("access_token", "refresh_token", "expires_in", "token_type", "scope") and v is not None
                }
            )
            sep = '&' if ('?' in post_redirect) else '?'
            return RedirectResponse(url=f"{post_redirect}{sep}{qs}")
        # En el MVP, si no hay redirect, devolvemos el JSON con el token.
        return token
    except Exception as e:
        if post_redirect:
            from urllib.parse import urlencode
            err_text = str(e)
            oauth_logger.error("OAuth error. state=%s error=%s", state, err_text, exc_info=True)
            qs = urlencode({"error": err_text[:500]})
            sep = '&' if ('?' in post_redirect) else '?'
            return RedirectResponse(url=f"{post_redirect}{sep}{qs}")
        raise HTTPException(status_code=502, detail=f"Error canjeando código: {e}")


@app.post("/oauth/figma/refresh")
async def oauth_figma_refresh(refresh_token: str):
    try:
        token = await refresh_access_token(refresh_token)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error refrescando token: {e}")
    return token


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
@app.get("/favicon.ico")
async def favicon():
    # Evita 404 en callback desde navegador:
    return Response(status_code=204)


@app.get("/jobs/{job_id}")
async def job_status(job_id: str):
    st = get_job(job_id)
    if not st:
        raise HTTPException(status_code=404, detail="Job no encontrado")
    data = st.model_dump()
    if st.status == "completed":
        data["download_url"] = f"/jobs/{job_id}/download"
        if st.analysis_id:
            analysis = get_analysis_response(st.analysis_id)
            if analysis:
                data["analysis"] = analysis
    return data


@app.get("/jobs/{job_id}/download")
async def job_download(job_id: str):
    st = get_job(job_id)
    if not st:
        raise HTTPException(status_code=404, detail="Job no encontrado")
    if st.status != "completed" or not st.output_path:
        raise HTTPException(status_code=409, detail="Job no listo para descargar")

    def _cleanup(path: str):
        try:
            os.remove(path)
        except Exception:
            pass

    return FileResponse(
        st.output_path,
        filename="casos_prueba.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        background=BackgroundTask(_cleanup, st.output_path),
    )


@app.get("/analyses")
async def analyses_endpoint(
    limit: int = Query(default=50, ge=1, le=500),
    file_key: str | None = Query(default=None),
):
    items = list_analyses(limit=limit, file_key=file_key)
    return {"items": items, "count": len(items)}


@app.get("/analyses/{analysis_id}")
async def analysis_detail(analysis_id: int, include_cases: bool = Query(default=True)):
    data = get_analysis_response(analysis_id, include_cases=include_cases)
    if not data:
        raise HTTPException(status_code=404, detail="Análisis no encontrado")
    return data


@app.delete("/analyses/{analysis_id}", status_code=204)
async def analysis_delete(analysis_id: int):
    if not delete_analysis(analysis_id):
        raise HTTPException(status_code=404, detail="Análisis no encontrado")
    return Response(status_code=204)


@app.patch("/analyses/{analysis_id}/cases/{case_id}")
async def analysis_case_update(analysis_id: int, case_id: int, payload: UpdateCaseRequest):
    try:
        data = payload.model_dump(exclude_unset=True)
    except AttributeError:  # Compatibilidad con Pydantic < 2
        data = payload.dict(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="No se enviaron campos a actualizar")
    case = update_case_evaluation(
        case_id,
        evaluated=data.get("evaluated"),
        status=data.get("status"),
        score=data.get("score"),
        score_set="score" in data,
        notes=data.get("notes"),
        checked=data.get("checked"),
    )
    if not case or case.run_id != analysis_id:
        raise HTTPException(status_code=404, detail="Caso no encontrado para este análisis")
    return serialize_case_payload(case)


@app.delete("/analyses/{analysis_id}/cases/{case_id}", status_code=204)
async def analysis_case_delete(analysis_id: int, case_id: int):
    stored = get_case(case_id)
    if not stored or stored.run_id != analysis_id:
        raise HTTPException(status_code=404, detail="Caso no encontrado para este análisis")
    if not delete_case(case_id):
        raise HTTPException(status_code=404, detail="Caso no encontrado para este análisis")
    return Response(status_code=204)


@app.post("/analyses/{analysis_id}/rerun")
async def analysis_rerun(
    analysis_id: int,
    payload: RerunAnalysisRequest,
    authorization: str | None = Header(default=None),
):
    stored = get_analysis_response(analysis_id, include_cases=False)
    if not stored:
        raise HTTPException(status_code=404, detail="Análisis no encontrado")
    figma_token = payload.figma_token
    if not figma_token and not authorization:
        raise HTTPException(status_code=400, detail="Proporciona figma_token en el cuerpo o Authorization: Bearer")

    merged = AnalyzeRequest(
        figma_url=stored.get("figma_url"),
        file_key=stored["file_key"],
        figma_token=figma_token,
        model=payload.model or stored["model"],
        reasoning_effort=payload.reasoning_effort or stored.get("reasoning_effort") or "medium",
        image_scale=payload.image_scale or stored["image_scale"],
        max_frames=payload.max_frames if payload.max_frames is not None else stored.get("max_frames"),
        analysis_level=payload.analysis_level or stored["analysis_level"],
        images_per_unit=payload.images_per_unit or stored["images_per_unit"],
    )
    return await analyze(merged, authorization=authorization)


@app.get("/_figma/pages")
async def figma_pages_endpoint(
    figma_url: str | None = Query(default=None),
    file_key: str | None = Query(default=None),
    figma_token: str | None = Query(default=None),
    authorization: str | None = Header(default=None),
):
    """Diagnóstico: lista páginas y conteo de frames por página.

    Enviar token via Authorization: Bearer <token> o ?figma_token=...
    """
    try:
        key = extract_file_key(file_key or figma_url or "")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
    token = figma_token or token
    if not token:
        raise HTTPException(status_code=400, detail="Falta figma_token o Authorization: Bearer")

    async with httpx.AsyncClient() as client:
        try:
            pages = await list_pages(client, token, key)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Error listando páginas: {e}")

        try:
            frames = await list_frames(client, token, key)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Error listando frames: {e}")

    counts: dict[str, dict] = {}
    for p_name, p_id, f_name, nid in frames:
        entry = counts.setdefault(p_id, {"page_name": p_name, "frame_count": 0, "samples": []})
        entry["frame_count"] += 1
        if len(entry["samples"]) < 6:
            entry["samples"].append({"frame": f_name, "node_id": nid})

    pages_out = []
    for p_name, p_id in pages:
        entry = counts.get(p_id) or {"page_name": p_name, "frame_count": 0, "samples": []}
        pages_out.append({"page_id": p_id, **entry})

    return {
        "file_key": key,
        "pages_total": len(pages),
        "frames_total": len(frames),
        "pages": pages_out,
    }


@app.get("/history/files")
async def history_files_endpoint(limit: int = Query(default=100, ge=1, le=500)):
    files = list_recent_files(limit=limit)
    return {"files": files, "count": len(files)}


@app.get("/analyses/{analysis_id}/export")
async def analysis_export(analysis_id: int):
    analysis = get_analysis_response(analysis_id, include_cases=False)
    if not analysis:
        raise HTTPException(status_code=404, detail="Análisis no encontrado")
    bundles = get_analysis_bundles(analysis_id)
    tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
    tmp_path = tmp.name
    tmp.close()
    await asyncio.to_thread(build_workbook, bundles, tmp_path)

    def _cleanup(path: str):
        try:
            os.remove(path)
        except Exception:
            pass

    filename = f"analysis_{analysis_id}.xlsx"
    return FileResponse(
        tmp_path,
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        background=BackgroundTask(_cleanup, tmp_path),
    )
