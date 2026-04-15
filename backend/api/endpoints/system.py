#======================================================================================================
# Endpoints for system status and control.
#======================================================================================================

from __future__ import annotations

import asyncio
import os
from typing import Dict, List

import aiohttp
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

#----------------------------------------------------------------------------------------------------
# Container names — read from env vars set in compose.yaml
_CONTAINER_API: str = os.environ.get("CONTAINER_NAME_API", "webscraper-api")
_CONTAINER_WORKER: str = os.environ.get(
    "CONTAINER_NAME_WORKER", "webscraper-celery-worker"
)
_CONTAINER_BEAT: str = os.environ.get(
    "CONTAINER_NAME_BEAT", "webscraper-celery-beat"
)

# Docker Engine HTTP API base URL (always localhost over the Unix socket)
_DOCKER_API_BASE: str = "http://localhost/v1.41"
_DOCKER_SOCKET: str = "/var/run/docker.sock"


#----------------------------------------------------------------------------------------------------
# Schemas
class RestartResponse(BaseModel):
    """Response returned immediately after triggering restart."""
    success: bool
    message: str
    restarting: List[str]


class ContainerStatus(BaseModel):
    """Status of a single container."""
    name: str
    status: str          # "running", "restarting", "exited", "unknown"
    available: bool      # True if the container is running


class SystemStatusResponse(BaseModel):
    """Overall system status — all tracked containers."""
    containers: List[ContainerStatus]
    all_running: bool


#----------------------------------------------------------------------------------------------------
# Helpers — Docker socket HTTP calls
async def _docker_restart(container_name: str) -> bool:
    """
    POST /containers/{name}/restart from Docker Engine API.
    Returns True on success, False on error.
    """
    try:
        connector = aiohttp.UnixConnector(path=_DOCKER_SOCKET)
        async with aiohttp.ClientSession(connector=connector) as session:
            url = f"{_DOCKER_API_BASE}/containers/{container_name}/restart"
            async with session.post(url, params={"t": "15"}) as response:
                # 204 = success, 404 = container not found
                return response.status in (204, 200)
    except Exception:
        return False


async def _docker_inspect(container_name: str) -> Dict:
    """
    GET /containers/{name}/json from Docker Engine API.
    Returns the container inspect dict, or empty dict on error.
    """
    try:
        connector = aiohttp.UnixConnector(path=_DOCKER_SOCKET)
        async with aiohttp.ClientSession(connector=connector) as session:
            url = f"{_DOCKER_API_BASE}/containers/{container_name}/json"
            async with session.get(url) as response:
                if response.status == 200:
                    return await response.json()
                return {}
    except Exception:
        return {}


def _is_docker_socket_available() -> bool:
    """Check whether the Docker socket is mounted and accessible."""
    return os.path.exists(_DOCKER_SOCKET)


#----------------------------------------------------------------------------------------------------
# Background self-restart task
async def _restart_self_after_delay(delay_seconds: float = 2.0) -> None:
    """
    Schedule a self-restart of the api container 2 seconds later.
    """
    await asyncio.sleep(delay_seconds)
    await _docker_restart(_CONTAINER_API)


#----------------------------------------------------------------------------------------------------
# Endpoints
@router.post("/restart", response_model=RestartResponse)
async def restart_containers() -> RestartResponse:
    """
    Restart all containers.
    """
    if not _is_docker_socket_available():
        return RestartResponse(
            success=False,
            message=(
                "Docker socket not available. "
                "Ensure /var/run/docker.sock is mounted in compose.yaml "
                "and the container user has permission to access it."
            ),
            restarting=[],
        )

    restarting: List[str] = []

    # Restart worker and beat first — they don't serve the HTTP response
    worker_ok = await _docker_restart(_CONTAINER_WORKER)
    if worker_ok:
        restarting.append(_CONTAINER_WORKER)

    beat_ok = await _docker_restart(_CONTAINER_BEAT)
    if beat_ok:
        restarting.append(_CONTAINER_BEAT)

    # Schedule api self-restart as a background task.
    # The response is sent first, THEN this task fires.
    asyncio.create_task(_restart_self_after_delay(delay_seconds=2.0))
    restarting.append(_CONTAINER_API)

    return RestartResponse(
        success=True,
        message=(
            f"Restarting {len(restarting)} container(s). "
            "The API will be back in ~15 seconds. "
            "Note: .env changes require 'docker compose up -d' instead."
        ),
        restarting=restarting,
    )


@router.get("/status", response_model=SystemStatusResponse)
async def get_system_status() -> SystemStatusResponse:
    """
    GET /api/system/status
    Returns status of all tracked containers.
    Used to poll whether everything is back up after a restart.
    """
    tracked = [_CONTAINER_API, _CONTAINER_WORKER, _CONTAINER_BEAT]
    statuses: List[ContainerStatus] = []

    for name in tracked:
        info = await _docker_inspect(name)

        if not info:
            statuses.append(ContainerStatus(
                name=name,
                status="unknown",
                available=False,
            ))
            continue

        state = info.get("State", {})
        raw_status = state.get("Status", "unknown")
        running = state.get("Running", False)

        statuses.append(ContainerStatus(
            name=name,
            status=raw_status,
            available=running,
        ))

    all_running = all(s.available for s in statuses)

    return SystemStatusResponse(
        containers=statuses,
        all_running=all_running,
    )
