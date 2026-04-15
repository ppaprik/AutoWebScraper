#======================================================================================================
# CRUD endpoints for credentials.
#======================================================================================================

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import get_database_manager, get_db_session
from backend.api.schemas import (
    CredentialCreate,
    CredentialListResponse,
    CredentialResponse,
    CredentialUpdate,
    MessageResponse,
)
from backend.src.managers.database_manager import DatabaseManager
from backend.src.services.encryption_service import EncryptionService

router = APIRouter()


def _credential_to_response(credential) -> CredentialResponse:
    """Convert a Credential model to a response (stripping the password)."""
    return CredentialResponse(
        id=credential.id,
        domain=credential.domain,
        username=credential.username,
        login_url=credential.login_url,
        username_selector=credential.username_selector,
        password_selector=credential.password_selector,
        submit_selector=credential.submit_selector,
        has_password=bool(credential.encrypted_password),
        created_at=credential.created_at,
        updated_at=credential.updated_at,
    )


@router.post("", response_model=CredentialResponse, status_code=201)
async def create_credential(
    body: CredentialCreate,
    session: AsyncSession = Depends(get_db_session),
    db: DatabaseManager = Depends(get_database_manager),
) -> CredentialResponse:
    """Create a new credential. The password is encrypted before storage."""
    encryption = EncryptionService()
    encrypted_password = encryption.encrypt(body.password)

    credential = await db.create_credential(
        session=session,
        domain=body.domain,
        username=body.username,
        encrypted_password=encrypted_password,
        login_url=body.login_url,
        username_selector=body.username_selector,
        password_selector=body.password_selector,
        submit_selector=body.submit_selector,
    )

    return _credential_to_response(credential)


@router.get("", response_model=CredentialListResponse)
async def list_credentials(
    session: AsyncSession = Depends(get_db_session),
    db: DatabaseManager = Depends(get_database_manager),
) -> CredentialListResponse:
    """List all credentials (passwords are never returned)."""
    credentials = await db.list_credentials(session)
    return CredentialListResponse(
        credentials=[_credential_to_response(c) for c in credentials]
    )


@router.get("/{credential_id}", response_model=CredentialResponse)
async def get_credential(
    credential_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    db: DatabaseManager = Depends(get_database_manager),
) -> CredentialResponse:
    """Get a single credential by ID (password is never returned)."""
    credential = await db.get_credential(session, credential_id)
    if credential is None:
        raise HTTPException(status_code=404, detail="Credential not found")
    return _credential_to_response(credential)


@router.put("/{credential_id}", response_model=CredentialResponse)
async def update_credential(
    credential_id: uuid.UUID,
    body: CredentialUpdate,
    session: AsyncSession = Depends(get_db_session),
    db: DatabaseManager = Depends(get_database_manager),
) -> CredentialResponse:
    """Update a credential. If a new password is provided, it is re-encrypted."""
    existing = await db.get_credential(session, credential_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Credential not found")

    encrypted_password = None
    if body.password is not None:
        encryption = EncryptionService()
        encrypted_password = encryption.encrypt(body.password)

    updated = await db.update_credential(
        session=session,
        credential_id=credential_id,
        domain=body.domain,
        username=body.username,
        encrypted_password=encrypted_password,
        login_url=body.login_url,
        username_selector=body.username_selector,
        password_selector=body.password_selector,
        submit_selector=body.submit_selector,
    )

    return _credential_to_response(updated)


@router.delete("/{credential_id}", response_model=MessageResponse)
async def delete_credential(
    credential_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    db: DatabaseManager = Depends(get_database_manager),
) -> MessageResponse:
    """Delete a credential."""
    deleted = await db.delete_credential(session, credential_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Credential not found")
    return MessageResponse(message="Credential deleted")
