import atexit
import os
import sys
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import SQLModel
import httpx

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


def test_figma_teams_endpoint(app_client, monkeypatch):
    from app.models import AnalyzeRequest, CasesBundle, GPTCase

    # Seed analysis for summary lookups
    req = AnalyzeRequest(
        figma_url="https://www.figma.com/file/demo2",
        file_key="file123",
        model="gpt-5",
        analysis_level="group",
        images_per_unit=3,
    )
    case = GPTCase(
        id="TC-2",
        frame="Header",
        feature="Signup",
        objetivo="Crear cuenta",
        pasos=["Abrir", "Completar formulario", "Enviar"],
        resultado_esperado="Cuenta creada",
    )
    bundle = CasesBundle(page_name="Page", frame_name="Frame", node_id="200:0", cases=[case])
    persistence.persist_analysis("job456", req, "file123", [bundle])

    async def fake_list_user_teams(client, token):
        return [{"id": "team1", "name": "Team Uno", "role": "owner"}]

    async def fake_list_team_projects(client, token, team_id):
        assert team_id == "team1"
        return [{"id": "project1", "name": "Proyecto A"}]

    async def fake_list_project_files(client, token, project_id):
        assert project_id == "project1"
        return [
            {
                "key": "file123",
                "name": "Dashboard",
                "thumbnail_url": "https://example.com/thumb.png",
                "last_modified": "2024-01-01T00:00:00Z",
            }
        ]

    monkeypatch.setattr(main, "list_user_teams", fake_list_user_teams)
    monkeypatch.setattr(main, "list_team_projects", fake_list_team_projects)
    monkeypatch.setattr(main, "list_project_files", fake_list_project_files)

    response = app_client.get(
        "/figma/teams",
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1
    assert data.get("errors") == []
    team = data["teams"][0]
    assert team["id"] == "team1"
    assert len(team["projects"]) == 1
    project = team["projects"][0]
    assert project["id"] == "project1"
    assert len(project["files"]) == 1
    file_entry = project["files"][0]
    assert file_entry["key"] == "file123"
    assert file_entry["analysis"]["runs"] == 1


def test_figma_teams_endpoint_handles_404(app_client, monkeypatch):
    request = httpx.Request("GET", "https://api.figma.com/v1/me/teams")
    response = httpx.Response(404, request=request)
    error = httpx.HTTPStatusError("Not Found", request=request, response=response)

    async def fake_list_user_teams(client, token):
        raise error

    monkeypatch.setattr(main, "list_user_teams", fake_list_user_teams)

    resp = app_client.get(
        "/figma/teams",
        headers={"Authorization": "Bearer test-token"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["teams"] == []
    assert data["count"] == 0
    assert any("404" in msg for msg in data.get("errors", []))
