from app.core.admin_auth import create_session_token, verify_password, verify_session_token


def test_password_and_signed_session_validation() -> None:
    secret = "s" * 32
    token = create_session_token(secret=secret, ttl_seconds=60, now=1_000)

    assert verify_password("correct horse battery", "correct horse battery") is True
    assert verify_password("wrong", "correct horse battery") is False
    assert verify_session_token(token, secret=secret, now=1_059) is True
    assert verify_session_token(token, secret=secret, now=1_060) is False
    assert verify_session_token(f"{token}tampered", secret=secret, now=1_001) is False
