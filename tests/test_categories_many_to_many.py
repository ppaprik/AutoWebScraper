#======================================================================================================
# Tests for the many-to-many relationship between Category and ScrapeResult.
#======================================================================================================

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from backend.src.managers.database_manager import CategoryInUseError, DatabaseManager
from backend.src.models import Category, CrawlMode, Job, ScrapeResult


#----------------------------------------------------------------------------------------------------
# Fixtures
@pytest.fixture
def db_manager() -> DatabaseManager:
    """A fresh DatabaseManager instance (sync — no DB call needed)."""
    return DatabaseManager()


@pytest_asyncio.fixture
async def job(db_session: AsyncSession, db_manager: DatabaseManager) -> Job:
    """A persisted Job row for linking scrape results."""
    return await db_manager.create_job(
        session=db_session,
        name="Test Job",
        start_url="https://example.com",
        crawl_mode=CrawlMode.SINGLE,
    )


@pytest_asyncio.fixture
async def scrape_result(
    db_session: AsyncSession,
    db_manager: DatabaseManager,
    job: Job,
) -> ScrapeResult:
    """A persisted ScrapeResult row with minimal content."""
    return await db_manager.store_scrape_result(
        session=db_session,
        job_id=job.id,
        url="https://example.com/page1",
        content=[{"type": "paragraph", "content": "Hello world."}],
        http_status=200,
        page_title="Test Page",
    )


@pytest_asyncio.fixture
async def food_category(
    db_session: AsyncSession,
    db_manager: DatabaseManager,
) -> Category:
    """A persisted 'Food' category."""
    return await db_manager.create_category(
        session=db_session,
        name="Food",
        keywords=["recipe", "cooking", "restaurant"],
    )


@pytest_asyncio.fixture
async def tech_category(
    db_session: AsyncSession,
    db_manager: DatabaseManager,
) -> Category:
    """A persisted 'Technology' category."""
    return await db_manager.create_category(
        session=db_session,
        name="Technology",
        keywords=["software", "programming", "AI"],
    )


#----------------------------------------------------------------------------------------------------
# get_category_by_name
class TestGetCategoryByName:

    @pytest.mark.asyncio
    async def test_finds_existing_category(
        self,
        db_session: AsyncSession,
        db_manager: DatabaseManager,
        food_category: Category,
    ) -> None:
        """Returns the category when it exists."""
        result = await db_manager.get_category_by_name(db_session, "Food")
        assert result is not None
        assert result.id == food_category.id

    @pytest.mark.asyncio
    async def test_lookup_is_case_insensitive(
        self,
        db_session: AsyncSession,
        db_manager: DatabaseManager,
        food_category: Category,
    ) -> None:
        """Lookup works regardless of capitalisation."""
        for variant in ("food", "FOOD", "FoOd"):
            result = await db_manager.get_category_by_name(db_session, variant)
            assert result is not None, f"Expected result for variant '{variant}'"
            assert result.id == food_category.id

    @pytest.mark.asyncio
    async def test_returns_none_for_nonexistent_name(
        self,
        db_session: AsyncSession,
        db_manager: DatabaseManager,
    ) -> None:
        """Returns None when no category has the given name."""
        result = await db_manager.get_category_by_name(db_session, "DoesNotExist")
        assert result is None


#----------------------------------------------------------------------------------------------------
# get_or_create_category_by_name
class TestGetOrCreateCategoryByName:

    @pytest.mark.asyncio
    async def test_creates_new_category(
        self,
        db_session: AsyncSession,
        db_manager: DatabaseManager,
    ) -> None:
        """When the category does not exist, a new row is inserted."""
        category, created = await db_manager.get_or_create_category_by_name(
            db_session, "Space"
        )
        assert created is True
        assert category is not None
        assert category.name == "Space"
        assert category.id is not None

    @pytest.mark.asyncio
    async def test_returns_existing_category(
        self,
        db_session: AsyncSession,
        db_manager: DatabaseManager,
        food_category: Category,
    ) -> None:
        """When the category already exists, returns it without creating a new row."""
        category, created = await db_manager.get_or_create_category_by_name(
            db_session, "Food"
        )
        assert created is False
        assert category.id == food_category.id

    @pytest.mark.asyncio
    async def test_get_or_create_is_case_insensitive(
        self,
        db_session: AsyncSession,
        db_manager: DatabaseManager,
        food_category: Category,
    ) -> None:
        """Case-insensitive lookup prevents duplicate categories."""
        category, created = await db_manager.get_or_create_category_by_name(
            db_session, "FOOD"
        )
        assert created is False
        assert category.id == food_category.id

    @pytest.mark.asyncio
    async def test_auto_created_category_is_active(
        self,
        db_session: AsyncSession,
        db_manager: DatabaseManager,
    ) -> None:
        """Auto-created categories are active by default."""
        category, created = await db_manager.get_or_create_category_by_name(
            db_session, "Gaming"
        )
        assert created is True
        assert category.is_active is True


#----------------------------------------------------------------------------------------------------
# assign_categories_to_result and get_categories_for_result
class TestCategoryAssignment:

    @pytest.mark.asyncio
    async def test_assign_single_category(
        self,
        db_session: AsyncSession,
        db_manager: DatabaseManager,
        scrape_result: ScrapeResult,
        food_category: Category,
    ) -> None:
        """A single category can be assigned to a scrape result."""
        await db_manager.assign_categories_to_result(
            session=db_session,
            scrape_result_id=scrape_result.id,
            category_ids=[food_category.id],
        )

        categories = await db_manager.get_categories_for_result(
            db_session, scrape_result.id
        )
        assert len(categories) == 1
        assert categories[0].id == food_category.id

    @pytest.mark.asyncio
    async def test_assign_multiple_categories(
        self,
        db_session: AsyncSession,
        db_manager: DatabaseManager,
        scrape_result: ScrapeResult,
        food_category: Category,
        tech_category: Category,
    ) -> None:
        """Multiple categories can be assigned to one scrape result."""
        await db_manager.assign_categories_to_result(
            session=db_session,
            scrape_result_id=scrape_result.id,
            category_ids=[food_category.id, tech_category.id],
        )

        categories = await db_manager.get_categories_for_result(
            db_session, scrape_result.id
        )
        category_names = {c.name for c in categories}
        assert "Food" in category_names
        assert "Technology" in category_names

    @pytest.mark.asyncio
    async def test_assign_empty_list_clears_assignments(
        self,
        db_session: AsyncSession,
        db_manager: DatabaseManager,
        scrape_result: ScrapeResult,
        food_category: Category,
    ) -> None:
        """Assigning an empty list removes all existing assignments."""
        await db_manager.assign_categories_to_result(
            db_session, scrape_result.id, [food_category.id]
        )
        await db_manager.assign_categories_to_result(
            db_session, scrape_result.id, []
        )

        categories = await db_manager.get_categories_for_result(
            db_session, scrape_result.id
        )
        assert categories == []

    @pytest.mark.asyncio
    async def test_reassign_replaces_existing(
        self,
        db_session: AsyncSession,
        db_manager: DatabaseManager,
        scrape_result: ScrapeResult,
        food_category: Category,
        tech_category: Category,
    ) -> None:
        """Calling assign_categories_to_result replaces the previous assignment."""
        await db_manager.assign_categories_to_result(
            db_session, scrape_result.id, [food_category.id]
        )
        await db_manager.assign_categories_to_result(
            db_session, scrape_result.id, [tech_category.id]
        )

        categories = await db_manager.get_categories_for_result(
            db_session, scrape_result.id
        )
        assert len(categories) == 1
        assert categories[0].id == tech_category.id

    @pytest.mark.asyncio
    async def test_get_categories_for_unassigned_result(
        self,
        db_session: AsyncSession,
        db_manager: DatabaseManager,
        scrape_result: ScrapeResult,
    ) -> None:
        """A scrape result with no assignments returns an empty list."""
        categories = await db_manager.get_categories_for_result(
            db_session, scrape_result.id
        )
        assert categories == []

    @pytest.mark.asyncio
    async def test_get_categories_for_nonexistent_result(
        self,
        db_session: AsyncSession,
        db_manager: DatabaseManager,
    ) -> None:
        """Querying a non-existent result ID returns an empty list."""
        categories = await db_manager.get_categories_for_result(
            db_session, uuid.uuid4()
        )
        assert categories == []

    @pytest.mark.asyncio
    async def test_results_sorted_alphabetically(
        self,
        db_session: AsyncSession,
        db_manager: DatabaseManager,
        scrape_result: ScrapeResult,
        food_category: Category,
        tech_category: Category,
    ) -> None:
        """get_categories_for_result returns categories sorted by name."""
        await db_manager.assign_categories_to_result(
            db_session,
            scrape_result.id,
            [tech_category.id, food_category.id],
        )

        categories = await db_manager.get_categories_for_result(
            db_session, scrape_result.id
        )
        names = [c.name for c in categories]
        assert names == sorted(names)


#----------------------------------------------------------------------------------------------------
# delete_category — enforcement of "prevent deletion if used"
class TestDeleteCategoryInUse:

    @pytest.mark.asyncio
    async def test_delete_unused_category_succeeds(
        self,
        db_session: AsyncSession,
        db_manager: DatabaseManager,
        food_category: Category,
    ) -> None:
        """An unused category can be deleted without error."""
        deleted = await db_manager.delete_category(db_session, food_category.id)
        assert deleted is True

        fetched = await db_manager.get_category(db_session, food_category.id)
        assert fetched is None

    @pytest.mark.asyncio
    async def test_delete_used_category_raises(
        self,
        db_session: AsyncSession,
        db_manager: DatabaseManager,
        scrape_result: ScrapeResult,
        food_category: Category,
    ) -> None:
        """Deleting a category assigned to a result raises CategoryInUseError."""
        await db_manager.assign_categories_to_result(
            db_session, scrape_result.id, [food_category.id]
        )

        with pytest.raises(CategoryInUseError) as exc_info:
            await db_manager.delete_category(db_session, food_category.id)

        assert exc_info.value.category_id == food_category.id
        assert exc_info.value.usage_count == 1

    @pytest.mark.asyncio
    async def test_category_in_use_error_message(
        self,
        db_session: AsyncSession,
        db_manager: DatabaseManager,
        scrape_result: ScrapeResult,
        food_category: Category,
    ) -> None:
        """CategoryInUseError message contains the category ID and count."""
        await db_manager.assign_categories_to_result(
            db_session, scrape_result.id, [food_category.id]
        )

        with pytest.raises(CategoryInUseError) as exc_info:
            await db_manager.delete_category(db_session, food_category.id)

        error_message = str(exc_info.value)
        assert str(food_category.id) in error_message
        assert "1" in error_message

    @pytest.mark.asyncio
    async def test_delete_nonexistent_category_returns_false(
        self,
        db_session: AsyncSession,
        db_manager: DatabaseManager,
    ) -> None:
        """Deleting a non-existent category returns False, not an error."""
        deleted = await db_manager.delete_category(db_session, uuid.uuid4())
        assert deleted is False

    @pytest.mark.asyncio
    async def test_delete_succeeds_after_assignments_cleared(
        self,
        db_session: AsyncSession,
        db_manager: DatabaseManager,
        scrape_result: ScrapeResult,
        food_category: Category,
    ) -> None:
        """Once assignments are cleared, the category can be deleted."""
        await db_manager.assign_categories_to_result(
            db_session, scrape_result.id, [food_category.id]
        )
        await db_manager.assign_categories_to_result(
            db_session, scrape_result.id, []
        )

        deleted = await db_manager.delete_category(db_session, food_category.id)
        assert deleted is True


#----------------------------------------------------------------------------------------------------
# Rename cascade (automatic via FK)

class TestCategoryRename:

    @pytest.mark.asyncio
    async def test_rename_is_reflected_in_assignment(
        self,
        db_session: AsyncSession,
        db_manager: DatabaseManager,
        scrape_result: ScrapeResult,
        food_category: Category,
    ) -> None:
        """
        Renaming a category is automatically reflected in all scrape result
        associations because the join table stores the category ID (FK),
        not a copied name string.
        """
        await db_manager.assign_categories_to_result(
            db_session, scrape_result.id, [food_category.id]
        )

        await db_manager.update_category(
            db_session, food_category.id, name="Cuisine"
        )

        categories = await db_manager.get_categories_for_result(
            db_session, scrape_result.id
        )
        assert len(categories) == 1
        assert categories[0].name == "Cuisine"
        assert categories[0].id == food_category.id
