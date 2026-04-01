import app


def test_hash_password_generates_pbkdf2_hash():
    password_hash = app.hash_password("secreto123")

    assert password_hash.startswith("$pbkdf2-sha256$")
    assert app.verify_password("secreto123", password_hash) is True


def test_verify_password_rejects_unknown_hash():
    assert app.verify_password("secreto123", "hash-invalido") is False
