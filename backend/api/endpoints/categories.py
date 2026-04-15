#======================================================================================================
# CRUD endpoints for content categories.
#======================================================================================================

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import get_database_manager, get_db_session
from backend.api.schemas import (
    CategoryCreate,
    CategoryListResponse,
    CategoryResponse,
    CategoryUpdate,
    MessageResponse,
)
from backend.src.managers.database_manager import DatabaseManager

router = APIRouter()


@router.post("", response_model=CategoryResponse, status_code=201)
async def create_category(
    body: CategoryCreate,
    session: AsyncSession = Depends(get_db_session),
    db: DatabaseManager = Depends(get_database_manager),
) -> CategoryResponse:
    """Create a new category."""
    url_patterns = None
    if body.url_patterns:
        url_patterns = [p.model_dump() for p in body.url_patterns]

    category = await db.create_category(
        session=session,
        name=body.name,
        description=body.description,
        keywords=body.keywords,
        url_patterns=url_patterns,
    )

    return CategoryResponse.model_validate(category)


@router.get("", response_model=CategoryListResponse)
async def list_categories(
    session: AsyncSession = Depends(get_db_session),
    db: DatabaseManager = Depends(get_database_manager),
) -> CategoryListResponse:
    """List all active categories."""
    categories = await db.list_categories(session, active_only=False)
    return CategoryListResponse(
        categories=[CategoryResponse.model_validate(c) for c in categories]
    )


@router.get("/{category_id}", response_model=CategoryResponse)
async def get_category(
    category_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    db: DatabaseManager = Depends(get_database_manager),
) -> CategoryResponse:
    """Get a single category by ID."""
    category = await db.get_category(session, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")
    return CategoryResponse.model_validate(category)


@router.put("/{category_id}", response_model=CategoryResponse)
async def update_category(
    category_id: uuid.UUID,
    body: CategoryUpdate,
    session: AsyncSession = Depends(get_db_session),
    db: DatabaseManager = Depends(get_database_manager),
) -> CategoryResponse:
    """Update a category."""
    existing = await db.get_category(session, category_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Category not found")

    url_patterns = None
    if body.url_patterns is not None:
        url_patterns = [p.model_dump() for p in body.url_patterns]

    updated = await db.update_category(
        session=session,
        category_id=category_id,
        name=body.name,
        description=body.description,
        keywords=body.keywords,
        url_patterns=url_patterns,
        is_active=body.is_active,
    )

    return CategoryResponse.model_validate(updated)


@router.delete("/{category_id}", response_model=MessageResponse)
async def delete_category(
    category_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    db: DatabaseManager = Depends(get_database_manager),
) -> MessageResponse:
    """Delete a category."""
    deleted = await db.delete_category(session, category_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Category not found")
    return MessageResponse(message="Category deleted")
