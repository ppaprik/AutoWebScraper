#======================================================================================================
# EncryptionService and EncryptionError
#======================================================================================================

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from backend.config import get_settings
from backend.logging_config import get_logger


logger = get_logger("encryption_service")


class EncryptionService:
    """
    Utility class for encrypting and decrypting data using Fernet.
    """

    def __init__(self) -> None:
        settings = get_settings()
        raw_key = settings.encryption_key

        if not raw_key:
            raise ValueError(
                "ENCRYPTION_KEY is not set. Generate one with: "
                "python -c \"from cryptography.fernet import Fernet; "
                "print(Fernet.generate_key().decode())\""
            )

        try:
            self._fernet = Fernet(raw_key.encode("utf-8"))
        except Exception as exc:
            raise ValueError(
                f"ENCRYPTION_KEY is invalid (must be a valid Fernet key): {exc}"
            ) from exc

    def encrypt(self, plaintext: str) -> str:
        """
        Encrypt a plaintext string and return the ciphertext as a URL-safe base64-encoded string.
        """
        if not plaintext:
            raise ValueError("Cannot encrypt an empty string")

        token = self._fernet.encrypt(plaintext.encode("utf-8"))
        return token.decode("utf-8")

    def decrypt(self, ciphertext: str) -> str:
        """
        Decrypt a Fernet ciphertext string back to plaintext.
        """
        if not ciphertext:
            raise ValueError("Cannot decrypt an empty string")

        try:
            plaintext_bytes = self._fernet.decrypt(ciphertext.encode("utf-8"))
            return plaintext_bytes.decode("utf-8")
        except InvalidToken as exc:
            logger.error("decryption_failed", error=str(exc))
            raise EncryptionError(
                "Decryption failed — the ciphertext is invalid or the "
                "ENCRYPTION_KEY has changed since encryption."
            ) from exc

    @staticmethod
    def generate_key() -> str:
        """Generate a new Fernet encryption key (utility method)."""
        return Fernet.generate_key().decode("utf-8")


class EncryptionError(Exception):
    """Raised when decryption fails due to invalid key or tampered data."""
    pass
