from __future__ import annotations

from typing import Dict, List, Tuple

import pandas as pd

from .models import CasesBundle, GPTCase


COLUMNS = [
    "ID",
    "Página",
    "Frame",
    "Feature",
    "Objetivo",
    "Prioridad",
    "Severidad",
    "Precondiciones",
    "Pasos",
    "Datos de prueba",
    "Resultado esperado",
    "Casos negativos",
    "Bordes",
    "Accesibilidad",
    "Dispositivo/Resolución",
    "Dependencias",
    "Observaciones",
]


def _case_to_row(page: str, frame: str, case: GPTCase) -> Dict[str, str]:
    return {
        "ID": case.id or "",
        "Página": page,
        "Frame": frame,
        "Feature": case.feature or "",
        "Objetivo": case.objetivo or "",
        "Prioridad": case.prioridad or "",
        "Severidad": case.severidad or "",
        "Precondiciones": "\n".join(case.precondiciones or []),
        "Pasos": "\n".join(case.pasos or []),
        "Datos de prueba": str(case.datos_prueba or {}),
        "Resultado esperado": case.resultado_esperado or "",
        "Casos negativos": "\n".join(case.negativo or []),
        "Bordes": "\n".join(case.bordes or []),
        "Accesibilidad": "\n".join(case.accesibilidad or []),
        "Dispositivo/Resolución": case.dispositivo or "",
        "Dependencias": "\n".join(case.dependencias or []),
        "Observaciones": case.observaciones or "",
    }


def build_workbook(bundles: List[CasesBundle], output_path: str) -> str:
    # Unifica todos los casos en una sola hoja
    rows: List[Dict[str, str]] = []
    for b in bundles:
        for c in b.cases:
            rows.append(_case_to_row(b.page_name, b.frame_name, c))

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        if rows:
            df = pd.DataFrame(rows, columns=COLUMNS)
            df.to_excel(writer, index=False, sheet_name="Casos")
        else:
            msg = "No se generaron casos. Revisa permisos del archivo, nivel de análisis o incrementa images_per_unit."
            pd.DataFrame([{"Mensaje": msg}]).to_excel(writer, index=False, sheet_name="Casos")

    return output_path
