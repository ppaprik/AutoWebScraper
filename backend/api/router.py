#======================================================================================================
# Master API router.
# Collects all endpoint sub-routers under the /api prefix.
#======================================================================================================

from __future__ import annotations

from fastapi import APIRouter

from backend.api.endpoints.analytics import router as analytics_router
from backend.api.endpoints.categories import router as categories_router
from backend.api.endpoints.credentials import router as credentials_router
from backend.api.endpoints.health import router as health_router
from backend.api.endpoints.jobs import router as jobs_router
from backend.api.endpoints.logs import router as logs_router
from backend.api.endpoints.scrape import router as scrape_router
from backend.api.endpoints.settings import router as settings_router
from backend.api.endpoints.system import router as system_router

api_router = APIRouter()

# Health check — always available, no prefix
api_router.include_router(health_router, tags=["health"])

# Feature routers
api_router.include_router(jobs_router, prefix="/jobs", tags=["jobs"])
api_router.include_router(scrape_router, prefix="/scrape", tags=["scrape"])
api_router.include_router(categories_router, prefix="/categories", tags=["categories"])
api_router.include_router(credentials_router, prefix="/credentials", tags=["credentials"])
api_router.include_router(logs_router, prefix="/logs", tags=["logs"])
api_router.include_router(analytics_router, prefix="/analytics", tags=["analytics"])
api_router.include_router(settings_router, prefix="/settings", tags=["settings"])
api_router.include_router(system_router, prefix="/system", tags=["system"])
