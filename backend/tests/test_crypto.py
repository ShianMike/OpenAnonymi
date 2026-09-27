import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr

from app.config import ConfigurationError, Settings, load_settings
from app.db.crypto import ContentKeyUnavailable, KeyRing, ProtectedContentError, ProtectedValue


def test_protected_text_round_trip_and_rotation_without_plaintext_metadata():
    first = Fernet.generate_key()
    second = Fernet.generate_key()
    old_ring = KeyRing("first", {"first": first})
    original = old_ring.encrypt_text("Synthetic 😀\r\n東京")
    assert b"Synthetic" not in original.ciphertext
    assert original.key_id == "first"

    new_ring = KeyRing("second", {"first": first, "second": second})
    rotated = new_ring.rotate_text(original)
    assert rotated.key_id == "second"
    assert new_ring.decrypt_text(rotated) == "Synthetic 😀\r\n東京"
    assert new_ring.rotate_text(rotated) == rotated
    with pytest.raises(ContentKeyUnavailable):
        old_ring.decrypt_text(rotated)
    with pytest.raises(ProtectedContentError):
        new_ring.decrypt_text(ProtectedValue(b"invalid-token", "second"))


def test_production_requires_configured_key_and_invalid_key_is_sanitized(monkeypatch):
    with pytest.raises(ValueError):
        Settings(
            database_url="postgresql+psycopg://user:secure@localhost/review",
            allowed_origins=["https://example.test"],
            environment="production",
            _env_file=None,
        )
    monkeypatch.setenv(
        "PRIVACY_REVIEW_DATABASE_URL", "postgresql+psycopg://user:pass@localhost/review"
    )
    monkeypatch.setenv("PRIVACY_REVIEW_ALLOWED_ORIGINS", '["http://localhost:5173"]')
    monkeypatch.setenv("PRIVACY_REVIEW_ACTIVE_KEY_ID", "test")
    monkeypatch.setenv("PRIVACY_REVIEW_CONTENT_KEYS", '{"test":"synthetic-invalid-key"}')
    with pytest.raises(ConfigurationError) as error:
        load_settings()
    assert "synthetic-invalid-key" not in str(error.value)


def test_valid_keyring_from_settings():
    key = Fernet.generate_key().decode()
    settings = Settings(
        database_url="postgresql+psycopg://user:pass@localhost/review",
        allowed_origins=["http://localhost:5173"],
        environment="test",
        active_key_id="one",
        content_keys={"one": SecretStr(key)},
        _env_file=None,
    )
    ring = KeyRing.from_settings(settings)
    assert ring.decrypt_text(ring.encrypt_text("example")) == "example"
