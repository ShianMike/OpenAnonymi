"""Encrypt protected fields with cryptography's Fernet and explicit key IDs."""

from dataclasses import dataclass

from cryptography.fernet import Fernet, InvalidToken

from app.config import Settings


class ContentKeyUnavailable(RuntimeError):
    pass


class ProtectedContentError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProtectedValue:
    ciphertext: bytes
    key_id: str


class KeyRing:
    def __init__(self, active_key_id: str, keys: dict[str, bytes]):
        if active_key_id not in keys:
            raise ContentKeyUnavailable("An active content key is not configured")
        self._active_key_id = active_key_id
        self._keys = {key_id: Fernet(key) for key_id, key in keys.items()}

    @classmethod
    def from_settings(cls, settings: Settings) -> "KeyRing":
        if not settings.active_key_id:
            raise ContentKeyUnavailable("Content encryption is not configured")
        return cls(
            settings.active_key_id,
            {
                key_id: key.get_secret_value().encode("ascii")
                for key_id, key in settings.content_keys.items()
            },
        )

    @property
    def active_key_id(self) -> str:
        return self._active_key_id

    def encrypt_text(self, value: str) -> ProtectedValue:
        return ProtectedValue(
            ciphertext=self._keys[self._active_key_id].encrypt(value.encode("utf-8")),
            key_id=self._active_key_id,
        )

    def decrypt_text(self, protected: ProtectedValue) -> str:
        key = self._keys.get(protected.key_id)
        if key is None:
            raise ContentKeyUnavailable("The content key for this record is unavailable")
        try:
            return key.decrypt(protected.ciphertext).decode("utf-8")
        except (InvalidToken, UnicodeDecodeError):
            raise ProtectedContentError("Protected content could not be read") from None

    def rotate_text(self, protected: ProtectedValue) -> ProtectedValue:
        if protected.key_id == self._active_key_id:
            return protected
        return self.encrypt_text(self.decrypt_text(protected))
