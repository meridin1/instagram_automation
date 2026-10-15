from app.core.security import hash_password, verify_password, create_access_token, decode_access_token


def test_password_hash_roundtrip():
    password = "StrongPass123!"
    hashed = hash_password(password)
    assert hashed != password
    assert verify_password(password, hashed)
    assert not verify_password("wrong", hashed)


def test_jwt_roundtrip():
    token = create_access_token("u1", "c1")
    payload = decode_access_token(token)
    assert payload["sub"] == "u1"
    assert payload["client_id"] == "c1"
