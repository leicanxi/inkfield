import pytest
from pydantic import ValidationError

from app.core.config import Settings


def valid_settings(**overrides: str) -> Settings:
    values = {
        "database_url": "postgresql+psycopg://app:app@localhost/test",
        "redis_url": "redis://localhost:6379/0",
        "token_signing_key": "x" * 32,
    }
    values.update(overrides)
    return Settings(
        database_url=values["database_url"],
        redis_url=values["redis_url"],
        token_signing_key=values["token_signing_key"],
    )


def test_required_configuration_is_accepted() -> None:
    settings = valid_settings()
    assert settings.app_env == "local"
    assert settings.token_signing_key.get_secret_value() == "x" * 32
    assert "x" * 32 not in repr(settings)


@pytest.mark.parametrize(
    "overrides",
    [
        {"database_url": "sqlite:///test.db"},
        {"redis_url": "http://localhost"},
        {"token_signing_key": "too-short"},
    ],
)
def test_invalid_critical_configuration_fails(overrides: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        valid_settings(**overrides)


def test_missing_critical_configuration_fails() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
