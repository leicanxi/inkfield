from app.core.observability import redact_sensitive


def test_sensitive_fields_are_redacted() -> None:
    event = {
        "event": "login_failed",
        "token": "secret-token",
        "password": "secret-password",
        "user_id": "safe-id",
    }
    result = redact_sensitive(None, "info", event)
    assert result["token"] == "[REDACTED]"
    assert result["password"] == "[REDACTED]"
    assert result["user_id"] == "safe-id"
