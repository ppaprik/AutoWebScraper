# =============================================================================
# Settings endpoints
# =============================================================================

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.src.services.settings_service import (
    MUTABLE_ENV_KEYS,
    PROTECTED_ENV_KEYS,
    apply_settings,
    get_all_settings,
)

router = APIRouter()


# =============================================================================
# Schemas (local — settings-specific, no need to pollute main schemas.py)
# =============================================================================

class SettingsResponse(BaseModel):
    """Full settings snapshot returned by GET /settings."""
    config: Dict[str, Dict[str, str]]
    env: Dict[str, str]
    requires_restart: bool = False


class SettingsUpdateRequest(BaseModel):
    """
    Partial update payload for PUT /settings.

    Both fields are optional — you can update just .config,
    just .env, or both in the same request.

    config: Dict[section, Dict[key, value]]
        Only provided sections/keys are changed. Others are untouched.
        Example: {"scraper": {"max_pages_per_job": "5000"}}

    env: Dict[key, value]
        Only MUTABLE_ENV_KEYS are accepted. Protected keys raise 400.
        Example: {"API_LOG_LEVEL": "debug", "CELERY_WORKER_CONCURRENCY": "8"}
    """
    config: Optional[Dict[str, Dict[str, str]]] = None
    env: Optional[Dict[str, str]] = None


class SettingsUpdateResponse(BaseModel):
    """Response returned after a successful PUT /settings."""
    success: bool = True
    requires_restart: bool
    changed_keys: List[str]
    message: str


class SettingsSchemaResponse(BaseModel):
    """
    Metadata about which settings keys are available,
    which are hot-reloadable, and which require restart.
    """
    mutable_env_keys: List[str]
    protected_env_keys: List[str]
    hot_reload_note: str
    restart_required_note: str


# =============================================================================
# Endpoints
# =============================================================================

@router.get("", response_model=SettingsResponse)
async def get_settings() -> SettingsResponse:
    """
    Return all current settings.
    """
    data = get_all_settings()
    return SettingsResponse(**data)


@router.put("", response_model=SettingsUpdateResponse)
async def update_settings(
    body: SettingsUpdateRequest,
) -> SettingsUpdateResponse:
    """
    Apply changes to .config and/or environment variables.
    """
    if not body.config and not body.env:
        raise HTTPException(
            status_code=400,
            detail="No settings provided. Include 'config' or 'env' in the request body.",
        )

    try:
        requires_restart, changed_keys = apply_settings(
            config_updates=body.config,
            env_updates=body.env,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if not changed_keys:
        return SettingsUpdateResponse(
            success=True,
            requires_restart=False,
            changed_keys=[],
            message="No values changed — all provided values matched current settings.",
        )

    if requires_restart:
        message = (
            f"{len(changed_keys)} setting(s) saved. "
            "Environment variable changes require a container restart to take effect."
        )
    else:
        message = (
            f"{len(changed_keys)} setting(s) saved and applied immediately."
        )

    return SettingsUpdateResponse(
        success=True,
        requires_restart=requires_restart,
        changed_keys=changed_keys,
        message=message,
    )


@router.get("/schema", response_model=SettingsSchemaResponse)
async def get_settings_schema() -> SettingsSchemaResponse:
    """
    Return metadata about which settings keys are available,
    which are hot-reloadable, and which require restart.
    """
    return SettingsSchemaResponse(
        mutable_env_keys=sorted(MUTABLE_ENV_KEYS),
        protected_env_keys=sorted(PROTECTED_ENV_KEYS),
        hot_reload_note=(
            "All .config values are applied immediately. "
            "No restart required."
        ),
        restart_required_note=(
            "Environment variable changes are saved to .env but take effect "
            "only after restarting the api and celery-worker containers."
        ),
    )
