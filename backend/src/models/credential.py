#======================================================================================================
# A login credential for a specific domain
#======================================================================================================

from __future__ import annotations

from typing import Optional

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.src.models.base import Base, TimestampMixin


class Credential(Base, TimestampMixin):
    """
    Login credentials for a specific domain.
    The encrypted_password field holds the Fernet-encrypted ciphertext.
    """

    __tablename__ = "credentials"

    # Domain this credential applies to (e.g., "example.com")
    domain: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)

    # Login URL for the authentication form
    login_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Username / email (stored in plaintext)
    username: Mapped[str] = mapped_column(String(255), nullable=False)

    # Password (encrypted at rest using Fernet)
    encrypted_password: Mapped[str] = mapped_column(Text, nullable=False)

    # Optional: CSS selector for the username input field
    username_selector: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Optional: CSS selector for the password input field
    password_selector: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Optional: CSS selector for the submit button
    submit_selector: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Optional: extra headers or cookies needed after login (JSON string)
    extra_auth_data: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<Credential(id={self.id}, domain='{self.domain}')>"
