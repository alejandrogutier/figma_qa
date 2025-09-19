from __future__ import annotations

import json
from typing import List

from openai import OpenAI
import logging
import time

from .models import FrameSummary, GPTCase, PageSummary


def _chat_json(client: OpenAI, *, model: str, messages: list) -> tuple[str, dict | None]:
    log = logging.getLogger("app.gpt")
    try:
        completion = client.chat.completions.create(
            model=model,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        usage = getattr(completion, "usage", None)
        raw = completion.choices[0].message.content or "{}"
        return raw, (usage.model_dump() if hasattr(usage, "model_dump") else usage)
    except Exception as e:
        log.error("Chat completion failed model=%s error=%s", model, e)
        raise


SYSTEM_PROMPT = (
    "Eres un QA Senior encargado de construir una MATRIZ COMPLETA de pruebas funcionales y no funcionales a partir de una maqueta (texto + imagen). "
    "Devuelve SOLO JSON válido con la forma exacta: {\"casos\": [ { ... } ] }. "
    "Cada caso debe rellenar todos los campos: id, frame, feature, objetivo, precondiciones (lista), pasos (lista, mínimo 6 pasos detallados con datos concretos), datos_prueba (objeto con claves y valores realistas), resultado_esperado (específico y medible), negativo (lista de escenarios adversos), bordes (lista con validaciones de límites y estados extremos), accesibilidad (lista con WCAG, navegación por teclado, lectores de pantalla), prioridad, severidad, dispositivo, dependencias (lista), observaciones. "
    "Genera una cobertura exhaustiva: flujo feliz, validaciones de formularios, estados vacíos/errores, permisos/roles, navegación cruzada, sincronización multi-dispositivo, resiliencia ante fallas de red, i18n, responsive y compatibilidad asistiva. "
    "Incluye variaciones positivas, negativas y de regresión. No reutilices pasos genéricos; usa información concreta de los textos y componentes detectados. "
    "Aporta suficientes casos para cubrir completamente la funcionalidad (normalmente 8-15 por funcionalidad). Si falta información, asume convenciones razonables y documenta las hipótesis en observaciones. "
    "NO incluyas texto fuera del JSON ni comentarios."
)


def _build_user_text(summary: FrameSummary) -> str:
    lines = [
        f"Archivo: {summary.file_key}",
        f"Página: {summary.page_name}",
        f"Frame: {summary.frame_name} (id {summary.node_id})",
        "",
        "Textos detectados:",
    ]
    for t in summary.texts[:200]:
        lines.append(f"- {t}")
    lines.append("")
    lines.append("Controles detectados:")
    for e in summary.elements[:100]:
        lines.append(f"- {e.get('type')}: {e.get('name','')}")
    lines.append("")
    lines.append(
        "Objetivo: genera casos de prueba funcionales para este frame, pensando en flujos completos y validaciones realistas."
    )
    return "\n".join(lines)


def generate_cases(summary: FrameSummary, *, model: str = "gpt-5", reasoning_effort: str | None = None) -> List[GPTCase]:
    client = OpenAI()
    log = logging.getLogger("app.gpt")

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": [
            {"type": "text", "text": _build_user_text(summary)},
            {"type": "image_url", "image_url": {"url": summary.image_url}},
        ]},
    ]

    for m in [model, "gpt-4o", "gpt-4o-mini"]:
        try:
            t0 = time.perf_counter()
            raw, usage = _chat_json(client, model=m, messages=messages)
            log.info("GPT %s time=%.2fs frame=%s", m, time.perf_counter() - t0, summary.node_id)
            try:
                data = json.loads(raw or "{}")
            except json.JSONDecodeError:
                data = {"casos": []}
            casos = data.get("casos") or data.get("cases") or data.get("test_cases") or data.get("testcases") or data.get("pruebas") or []
            out: List[GPTCase] = []
            for c in casos:
                try:
                    case = GPTCase(**c)
                except Exception:
                    case = GPTCase(
                        id=str(c.get("id")) if c.get("id") is not None else None,
                        frame=c.get("frame"), feature=c.get("feature"), objetivo=c.get("objetivo"),
                        precondiciones=c.get("precondiciones"), pasos=c.get("pasos"), datos_prueba=c.get("datos_prueba"),
                        resultado_esperado=c.get("resultado_esperado"), negativo=c.get("negativo"), bordes=c.get("bordes"),
                        accesibilidad=c.get("accesibilidad"), prioridad=c.get("prioridad"), severidad=c.get("severidad"),
                        dispositivo=c.get("dispositivo"), dependencias=c.get("dependencias"), observaciones=c.get("observaciones"),
                    )
                if not case.image_url:
                    case.image_url = summary.image_url
                out.append(case)
            if out:
                return out
            log.warning("GPT returned 0 cases (model=%s) for frame=%s Raw=%s", m, summary.node_id, (raw or "")[:300])
        except Exception as e:
            log.error("GPT error model=%s frame=%s err=%s", m, summary.node_id, e)
            continue
    return []


def _build_user_text_for_page(ps: PageSummary, limit_frames: int = 6) -> str:
    lines = [
        f"Archivo: {ps.file_key}",
        f"Página: {ps.page_name}",
        "",
        "Resumen por frames (nombres y elementos):",
    ]
    for fs in ps.frames[:limit_frames]:
        lines.append(f"- Frame: {fs.frame_name} (id {fs.node_id})")
        if fs.elements:
            names = ", ".join([f"{e.type}:{e.name or ''}" for e in fs.elements[:8]])
            lines.append(f"  · Controles: {names}")
        if fs.texts:
            sample = ", ".join(fs.texts[:6])
            lines.append(f"  · Textos: {sample}")
    lines.append("")
    lines.append(
        "Objetivo: genera casos de prueba funcionales a nivel de página, considerando los frames mostrados como una misma funcionalidad o sección coherente. Evita duplicar casos idénticos por frame; consolida donde aplique."
    )
    return "\n".join(lines)


def _build_user_text_for_group(ps: PageSummary, group_name: str, limit_frames: int = 6) -> str:
    lines = [
        f"Archivo: {ps.file_key}",
        f"Página: {ps.page_name}",
        f"Grupo objetivo: {group_name}",
        "",
        "Frames relevantes:",
    ]
    for fs in ps.frames[:limit_frames]:
        lines.append(f"- Frame: {fs.frame_name} (id {fs.node_id})")
        if fs.elements:
            names = ", ".join([f"{e.type}:{e.name or ''}" for e in fs.elements[:8]])
            lines.append(f"  · Controles/Componentes: {names}")
        if fs.texts:
            sample = ", ".join(fs.texts[:6])
            lines.append(f"  · Textos: {sample}")
    lines.append("")
    lines.append(
        "Objetivo: genera casos de prueba FUNCIONALES para el grupo indicado, consolidando comportamientos y validaciones comunes observadas en los frames. Evita duplicar casos idénticos por frame."
    )
    return "\n".join(lines)


def generate_cases_for_group(ps: PageSummary, group_name: str, *, model: str = "gpt-5", images_per_unit: int = 12) -> List[GPTCase]:
    client = OpenAI()
    log = logging.getLogger("app.gpt")

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": [{"type": "text", "text": _build_user_text_for_group(ps, group_name, images_per_unit)}]},
    ]
    img_parts = []
    for fs in ps.frames[:images_per_unit]:
        img_parts.append({"type": "text", "text": f"Imagen del frame: {fs.frame_name}"})
        img_parts.append({"type": "image_url", "image_url": {"url": fs.image_url}})
    messages[1]["content"].extend(img_parts)
    primary_image = ps.frames[0].image_url if ps.frames else None

    for m in [model, "gpt-4o", "gpt-4o-mini"]:
        try:
            t0 = time.perf_counter()
            raw, usage = _chat_json(client, model=m, messages=messages)
            log.info("GPT %s time=%.2fs group=%s page=%s", m, time.perf_counter() - t0, group_name, ps.page_name)
            try:
                data = json.loads(raw or "{}")
            except json.JSONDecodeError:
                data = {"casos": []}
            casos = data.get("casos") or data.get("cases") or data.get("test_cases") or data.get("testcases") or data.get("pruebas") or []
            out: List[GPTCase] = []
            for c in casos:
                try:
                    case = GPTCase(**c)
                except Exception:
                    case = GPTCase(
                        id=str(c.get("id")) if c.get("id") is not None else None,
                        frame=c.get("frame"), feature=c.get("feature"), objetivo=c.get("objetivo"), precondiciones=c.get("precondiciones"),
                        pasos=c.get("pasos"), datos_prueba=c.get("datos_prueba"), resultado_esperado=c.get("resultado_esperado"), negativo=c.get("negativo"),
                        bordes=c.get("bordes"), accesibilidad=c.get("accesibilidad"), prioridad=c.get("prioridad"), severidad=c.get("severidad"),
                        dispositivo=c.get("dispositivo"), dependencias=c.get("dependencias"), observaciones=c.get("observaciones"),
                    )
                if not case.image_url:
                    case.image_url = primary_image
                out.append(case)
            if out:
                return out
            log.warning("GPT returned 0 cases (model=%s) for group=%s page=%s Raw=%s", m, group_name, ps.page_name, (raw or "")[:300])
        except Exception as e:
            log.error("GPT error model=%s group=%s page=%s err=%s", m, group_name, ps.page_name, e)
            continue
    return []
def generate_cases_for_page(ps: PageSummary, *, model: str = "gpt-5", images_per_unit: int = 6, reasoning_effort: str | None = None) -> List[GPTCase]:
    client = OpenAI()
    log = logging.getLogger("app.gpt")

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": [{"type": "text", "text": _build_user_text_for_page(ps, images_per_unit)}]},
    ]
    # Añadir imágenes
    img_parts = []
    for fs in ps.frames[:images_per_unit]:
        img_parts.append({"type": "text", "text": f"Imagen del frame: {fs.frame_name}"})
        img_parts.append({"type": "image_url", "image_url": {"url": fs.image_url}})
    messages[1]["content"].extend(img_parts)
    primary_image = ps.frames[0].image_url if ps.frames else None

    for m in [model, "gpt-4o", "gpt-4o-mini"]:
        try:
            t0 = time.perf_counter()
            raw, usage = _chat_json(client, model=m, messages=messages)
            log.info("GPT %s time=%.2fs page=%s", m, time.perf_counter() - t0, ps.page_name)
            try:
                data = json.loads(raw or "{}")
            except json.JSONDecodeError:
                data = {"casos": []}
            casos = data.get("casos") or data.get("cases") or data.get("test_cases") or data.get("testcases") or data.get("pruebas") or []
            out: List[GPTCase] = []
            for c in casos:
                try:
                    case = GPTCase(**c)
                except Exception:
                    case = GPTCase(
                        id=str(c.get("id")) if c.get("id") is not None else None,
                        frame=c.get("frame"), feature=c.get("feature"), objetivo=c.get("objetivo"),
                        precondiciones=c.get("precondiciones"), pasos=c.get("pasos"), datos_prueba=c.get("datos_prueba"),
                        resultado_esperado=c.get("resultado_esperado"), negativo=c.get("negativo"), bordes=c.get("bordes"),
                        accesibilidad=c.get("accesibilidad"), prioridad=c.get("prioridad"), severidad=c.get("severidad"),
                        dispositivo=c.get("dispositivo"), dependencias=c.get("dependencias"), observaciones=c.get("observaciones"),
                    )
                if not case.image_url:
                    case.image_url = primary_image
                out.append(case)
            if out:
                return out
            log.warning("GPT returned 0 cases (model=%s) for page=%s Raw=%s", m, ps.page_name, (raw or "")[:300])
        except Exception as e:
            log.error("GPT error model=%s page=%s err=%s", m, ps.page_name, e)
            continue
    return []
