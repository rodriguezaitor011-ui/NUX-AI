import os
import json
from app import auth
from app.config import settings


def test_access_and_refresh_token_creation(tmp_path):
    # Ensure a consistent secret for tests
    settings.SECRET_KEY = "test-secret-for-pytest"

    payload = {"user_id": 1, "email": "test@example.com"}

    access = auth.create_access_token(payload)
    decoded = auth.decode_token(access)
    assert decoded is not None
    assert decoded.get("user_id") == 1

    refresh = auth.create_refresh_token(payload)
    decoded_r = auth.decode_token(refresh)
    assert decoded_r is not None
    assert decoded_r.get("type") == "refresh"
    jti = decoded_r.get("jti")
    assert jti is not None

    # Revocation flow: revoke and check
    # Use a temporary revocation file
    rev_file = tmp_path / "revoked_refresh_tokens.json"
    auth.REVOCATION_FILE = str(rev_file)

    # Initially not revoked
    assert not auth.is_refresh_token_revoked(jti)

    auth.revoke_refresh_token(jti)
    assert auth.is_refresh_token_revoked(jti)

    # Cleanup
    if rev_file.exists():
        rev_file.unlink()
