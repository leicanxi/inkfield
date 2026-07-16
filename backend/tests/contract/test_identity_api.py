from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def settings() -> Settings:
    return Settings(
        app_env="test",
        app_version="test-version",
        database_url="postgresql+psycopg://app:app@localhost/test",
        redis_url="redis://localhost:6379/15",
        token_signing_key="x" * 32,
    )


def test_identity_routes_are_exposed_under_api_v1() -> None:
    app = create_app(settings())
    paths = app.openapi()["paths"]
    assert {
        "/api/v1/auth/wechat/login",
        "/api/v1/auth/refresh",
        "/api/v1/auth/logout",
        "/api/v1/auth/sessions",
        "/api/v1/auth/sessions/{session_id}",
        "/api/v1/auth/logout-all",
        "/api/v1/me",
        "/api/v1/me/preferences",
    } <= paths.keys()


def test_project_routes_match_the_existing_api_contract() -> None:
    app = create_app(settings())
    paths = app.openapi()["paths"]
    assert {
        "/api/v1/projects",
        "/api/v1/projects/{project_id}",
        "/api/v1/projects/{project_id}/route",
        "/api/v1/projects/{project_id}/closure",
        "/api/v1/projects/{project_id}/pause",
        "/api/v1/projects/{project_id}/resume",
        "/api/v1/projects/{project_id}/complete",
        "/api/v1/projects/{project_id}/archive",
    } <= paths.keys()


def test_execution_routes_match_the_existing_api_contract() -> None:
    app = create_app(settings())
    paths = app.openapi()["paths"]
    assert {
        "/api/v1/user-weeks/current",
        "/api/v1/user-weeks/{week_start}",
        "/api/v1/projects/{project_id}/weeks/current",
        "/api/v1/projects/{project_id}/weeks/{week_start}",
        "/api/v1/tasks/current-week",
        "/api/v1/tasks",
        "/api/v1/tasks/{task_id}",
        "/api/v1/tasks/{task_id}/events",
    } <= paths.keys()


def test_unconfigured_wechat_provider_fails_safely() -> None:
    with TestClient(create_app(settings())) as client:
        response = client.post(
            "/api/v1/auth/wechat/login",
            json={"code": "temporary-code", "platform": "wechat_mini"},
        )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "AUTH_PROVIDER_UNAVAILABLE"
    assert response.json()["error"]["retryable"] is True


def test_protected_route_requires_bearer_token() -> None:
    with TestClient(create_app(settings())) as client:
        response = client.get("/api/v1/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"
