from __future__ import annotations

from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field


class UpdateCaseRequest(BaseModel):
    evaluated: Optional[bool] = None
    status: Optional[str] = None
    score: Optional[float] = None
    notes: Optional[str] = None
    checked: Optional[bool] = None


class RerunAnalysisRequest(BaseModel):
    figma_token: Optional[str] = None
    analysis_level: Optional[Literal["frame", "page", "group", "section"]] = None
    model: Optional[str] = None
    reasoning_effort: Optional[Literal["low", "medium", "high"]] = None
    image_scale: Optional[float] = None
    images_per_unit: Optional[int] = None
    max_frames: Optional[int] = None


class AnalyzeRequest(BaseModel):
    figma_url: Optional[str] = Field(None, description="URL completa del archivo Figma")
    file_key: Optional[str] = Field(None, description="File key de Figma si no envías URL")
    figma_token: Optional[str] = Field(
        None,
        description="Access Token de Figma (PAT o OAuth). Si no se envía, se usa Authorization: Bearer",
    )
    model: str = Field(
        default="gpt-5",
        description="Modelo de OpenAI para generar casos (por defecto gpt-5 si está disponible)",
    )
    reasoning_effort: Literal["low", "medium", "high"] = Field(
        default="medium", description="Nivel de esfuerzo de razonamiento para modelos reasoning"
    )
    image_scale: float = Field(
        default=2.0, description="Escala de render para imágenes de Figma (1–4)"
    )
    max_frames: Optional[int] = Field(
        default=None,
        ge=1,
        le=200,
        description="Límite superior de frames a procesar (para pruebas rápidas)",
    )
    analysis_level: Literal["frame", "page", "group", "section"] = Field(
        default="group",
        description="Nivel de análisis: frame individual o por página",
    )
    images_per_unit: int = Field(default=12, ge=1, le=12, description="Máximo de imágenes por unidad (interno)")


class Element(BaseModel):
    type: str
    name: Optional[str] = None
    variant: Optional[Dict[str, Any]] = None


class FrameSummary(BaseModel):
    file_key: str
    page_name: str
    frame_name: str
    node_id: str
    image_url: str
    texts: List[str] = Field(default_factory=list)
    elements: List[Element] = Field(default_factory=list)


class GPTCase(BaseModel):
    id: Optional[str] = None
    frame: Optional[str] = None
    feature: Optional[str] = None
    objetivo: Optional[str] = None
    precondiciones: Optional[List[str]] = None
    pasos: Optional[List[str]] = None
    datos_prueba: Optional[Dict[str, Any]] = None
    resultado_esperado: Optional[str] = None
    negativo: Optional[List[str]] = None
    bordes: Optional[List[str]] = None
    accesibilidad: Optional[List[str]] = None
    prioridad: Optional[str] = None
    severidad: Optional[str] = None
    dispositivo: Optional[str] = None
    dependencias: Optional[List[str]] = None
    observaciones: Optional[str] = None
    image_url: Optional[str] = None


class CasesBundle(BaseModel):
    page_name: str
    frame_name: str
    node_id: str
    cases: List[GPTCase]


class PageSummary(BaseModel):
    file_key: str
    page_name: str
    frames: List[FrameSummary] = Field(default_factory=list)
