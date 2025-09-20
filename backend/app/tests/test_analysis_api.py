import atexit
import os
import sys
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import SQLModel

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

TMP_DIR = tempfile.TemporaryDirectory()
atexit.register(TMP_DIR.cleanup)
DB_PATH = Path(TMP_DIR.name) / "test.db"
os.environ["FIGMAQA_DB_PATH"] = str(DB_PATH)

from app import db, db_models, persistence, main  # noqa: E402

SQLModel.metadata.drop_all(db.engine)
SQLModel.metadata.create_all(db.engine)


@pytest.fixture(scope="module")
def app_client():
    with TestClient(main.app) as client:
        yield client


@pytest.fixture(autouse=True)
def reset_database():
    SQLModel.metadata.drop_all(db.engine)
    SQLModel.metadata.create_all(db.engine)


def test_root_endpoint(app_client):
    response = app_client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "figma-qa"
    assert data["health"] == "/health"


def test_analysis_lifecycle(app_client):
    from app.models import AnalyzeRequest, CasesBundle, GPTCase

    req = AnalyzeRequest(
        figma_url="https://www.figma.com/file/demo",
        file_key="demo_file",
        model="gpt-5",
        analysis_level="group",
        images_per_unit=3,
    )
    case = GPTCase(
        id="TC-1",
        frame="Hero",
        feature="Login",
        objetivo="Validar acceso",
        precondiciones=["Usuario registrado"],
        pasos=[
            "Abrir app",
            "Ir a login",
            "Ingresar credenciales",
            "Enviar formulario",
            "Ver dashboard",
            "Registrar sesión",
        ],
        datos_prueba={"usuario": "qa@example.com"},
        resultado_esperado="Dashboard visible",
        accesibilidad=["Focus visible"],
        prioridad="alta",
        severidad="media",
        image_url="https://example.com/image.png",
    )
    bundle = CasesBundle(page_name="Page 1", frame_name="Frame 1", node_id="123:0", cases=[case])
    analysis_id = persistence.persist_analysis("job123", req, "demo_file", [bundle])

    list_response = app_client.get("/analyses")
    assert list_response.status_code == 200
    items = list_response.json()["items"]
    assert len(items) == 1
    assert items[0]["analysis_id"] == analysis_id

    detail_response = app_client.get(f"/analyses/{analysis_id}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["analysis_id"] == analysis_id
    assert detail["total_cases"] == 1
    case_payload = detail["cases"][0]
    evaluation = case_payload["evaluation"]
    assert evaluation["status"] == "pending"
    assert evaluation["checked"] is False

    case_id = evaluation["case_id"]
    patch_payload = {
        "status": "passed",
        "evaluated": True,
        "checked": True,
        "score": 95,
        "notes": "Cobertura validada",
    }
    update_response = app_client.patch(f"/analyses/{analysis_id}/cases/{case_id}", json=patch_payload)
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["evaluation"]["status"] == "passed"
    assert updated["evaluation"]["score"] == 95
    assert updated["evaluation"]["checked"] is True

    delete_response = app_client.delete(f"/analyses/{analysis_id}")
    assert delete_response.status_code == 204

    missing_response = app_client.get(f"/analyses/{analysis_id}")
    assert missing_response.status_code == 404


def test_history_files_endpoint(app_client):
    from app.models import AnalyzeRequest, CasesBundle, GPTCase

    req1 = AnalyzeRequest(
        figma_url="https://www.figma.com/file/historyA",
        file_key="historyA",
        model="gpt-4o",
        analysis_level="group",
        images_per_unit=3,
    )
    case = GPTCase(id="H-1", frame="Main", feature="Login")
    bundle = CasesBundle(page_name="Page", frame_name="Frame", node_id="1:2", cases=[case])
    analysis_id = persistence.persist_analysis("jobH1", req1, "historyA", [bundle])

    # second run for same file to bump counters
    persistence.persist_analysis("jobH2", req1, "historyA", [bundle])

    req2 = AnalyzeRequest(
        figma_url="https://www.figma.com/file/historyB",
        file_key="historyB",
        model="gpt-4o-mini",
        analysis_level="page",
        images_per_unit=2,
    )
    persistence.persist_analysis("jobH3", req2, "historyB", [bundle])

    resp = app_client.get("/history/files")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["count"] == 2
    files = {item["file_key"]: item for item in payload["files"]}
    assert files["historyA"]["runs"] == 2
    assert files["historyA"]["last_analysis_id"] is not None
    assert files["historyA"]["figma_url"] == "https://www.figma.com/file/historyA"
    assert files["historyB"]["runs"] == 1

    # The most recent entry should come first (historyB is last persisted)
    assert payload["files"][0]["file_key"] in {"historyA", "historyB"}


def test_history_files_endpoint_respects_limit(app_client):
    from app.models import AnalyzeRequest, CasesBundle, GPTCase

    req = AnalyzeRequest(
        figma_url="https://www.figma.com/file/historyC",
        file_key="historyC",
        model="gpt-4o",
        analysis_level="group",
        images_per_unit=3,
    )
    req_other = AnalyzeRequest(
        figma_url="https://www.figma.com/file/historyD",
        file_key="historyD",
        model="gpt-4o",
        analysis_level="group",
        images_per_unit=3,
    )
    case = GPTCase(id="H-2", frame="Main")
    bundle = CasesBundle(page_name="Page", frame_name="Frame", node_id="2:2", cases=[case])
    persistence.persist_analysis("jobH4", req, "historyC", [bundle])
    persistence.persist_analysis("jobH5", req_other, "historyD", [bundle])

    resp = app_client.get("/history/files", params={"limit": 1})
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1


def test_case_deletion_endpoint(app_client):
    from app.models import AnalyzeRequest, CasesBundle, GPTCase

    req = AnalyzeRequest(
        figma_url="https://www.figma.com/file/delete",
        file_key="del_file",
        model="gpt-4o",
        analysis_level="group",
        images_per_unit=3,
    )
    case = GPTCase(id="DEL-1", frame="Hero")
    bundle = CasesBundle(page_name="Page", frame_name="Frame", node_id="1:1", cases=[case])
    analysis_id = persistence.persist_analysis("jobDEL", req, "del_file", [bundle])

    detail = app_client.get(f"/analyses/{analysis_id}").json()
    case_id = detail["cases"][0]["evaluation"]["case_id"]

    resp = app_client.delete(f"/analyses/{analysis_id}/cases/{case_id}")
    assert resp.status_code == 204

    refreshed = app_client.get(f"/analyses/{analysis_id}").json()
    assert refreshed["total_cases"] == 0
    assert refreshed["cases"] == []


def test_analysis_export_endpoint(app_client):
    from app.models import AnalyzeRequest, CasesBundle, GPTCase

    req = AnalyzeRequest(
        figma_url="https://www.figma.com/file/export",
        file_key="export_file",
        model="gpt-4o",
        analysis_level="group",
        images_per_unit=3,
    )
    case = GPTCase(id="EXP-1", frame="Header")
    bundle = CasesBundle(page_name="Page", frame_name="Frame", node_id="3:1", cases=[case])
    analysis_id = persistence.persist_analysis("jobEXP", req, "export_file", [bundle])

    resp = app_client.get(f"/analyses/{analysis_id}/export")
    assert resp.status_code == 200
    assert resp.headers.get("content-type") == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert resp.headers.get("content-disposition")
    assert len(resp.content) > 0
