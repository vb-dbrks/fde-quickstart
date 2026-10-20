from fastapi.testclient import TestClient

from tests.helpers import IsolatedSettings


def test_health_reports_the_database(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_client_side_routes_serve_the_spa(client: TestClient) -> None:
    for path in ("/", "/notes", "/admin/roles"):
        response = client.get(path)
        assert response.status_code == 200, path
        assert "<title>test app</title>" in response.text


def test_static_files_are_served(client: TestClient) -> None:
    response = client.get("/favicon.svg")
    assert response.status_code == 200
    assert response.text == "<svg></svg>"


def test_unknown_api_routes_are_json_404s(client: TestClient) -> None:
    response = client.get("/api/does-not-exist")
    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}


def test_files_outside_the_static_dir_are_not_served(client: TestClient) -> None:
    response = client.get("/%2E%2E/secret.txt")
    assert "outside the static dir" not in response.text


def test_openapi_schema_lives_under_api(client: TestClient) -> None:
    assert client.get("/api/openapi.json").json()["info"]["title"] == "Quickstart App"


def test_admin_emails_are_normalised() -> None:
    settings = IsolatedSettings(app_admin_emails=" Lead@Example.com, ,ops@example.com ")
    assert settings.admin_emails == {"lead@example.com", "ops@example.com"}


def test_databricks_apps_is_detected_from_the_app_name() -> None:
    assert not IsolatedSettings(databricks_app_name=None).on_databricks
    assert IsolatedSettings(databricks_app_name="my-app").on_databricks
