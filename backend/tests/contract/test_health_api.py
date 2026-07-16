from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def test_liveness_uses_success_envelope_and_correlation_id() -> None:
    settings = Settings(
        app_env="test",
        app_version="test-version",
        database_url="postgresql+psycopg://app:app@localhost/test",
        redis_url="redis://localhost:6379/15",
        token_signing_key="x" * 32,
    )
    with TestClient(create_app(settings)) as client:
        response = client.get("/health/live", headers={"X-Correlation-ID": "contract-test-1"})
    assert response.status_code == 200
    assert response.headers["X-Correlation-ID"] == "contract-test-1"
    assert response.json() == {
        "data": {"status": "ok", "version": "test-version", "dependencies": {}},
        "correlation_id": "contract-test-1",
    }
