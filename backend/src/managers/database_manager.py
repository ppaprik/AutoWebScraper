#======================================================================================================
# Manages database operations behind a clean async interface.
#======================================================================================================

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import and_, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.src.models import (
    Category,
    ContentVersion,
    Credential,
    CrawlMode,
    Job,
    JobStatus,
    LogEntry,
    LogLevel,
    ScrapeResult,
    scrape_result_categories,
)


#----------------------------------------------------------------------------------------------------
# Constants
# The "Uncategorized" category is a real protected DB row. It is created on startup and cannot be deleted or renamed.
UNCATEGORIZED_NAME: str = "Uncategorized"


#----------------------------------------------------------------------------------------------------
# Custom exceptions
class CategoryInUseError(Exception):
    """
    Raised when attempting to delete a category that is still assigned
    to one or more scrape results. Callers should surface this as HTTP 409.
    """
    def __init__(self, category_id: uuid.UUID, usage_count: int) -> None:
        self.category_id = category_id
        self.usage_count = usage_count
        super().__init__(
            f"Category {category_id} is assigned to {usage_count} scrape result(s) "
            f"and cannot be deleted. Remove all assignments first."
        )


class ProtectedCategoryError(Exception):
    """
    Raised when attempting to delete or rename a protected system category
    such as 'Uncategorized'. Callers should surface this as HTTP 400.
    """
    def __init__(self, name: str, operation: str) -> None:
        self.name = name
        self.operation = operation
        super().__init__(
            f"Category '{name}' is protected and cannot be {operation}."
        )


#----------------------------------------------------------------------------------------------------
# DatabaseManager
class DatabaseManager:
    """
    Manages database operations behind a clean async interface.
    """
    #---------------------------------------------------------------------------
    # STARTUP UTILITIES
    async def ensure_uncategorized_exists(
        self,
        session: AsyncSession,
    ) -> Category:
        """
        Create the "Uncategorized" category if it doesn't already exist.
        """
        existing = await self.get_category_by_name(session, UNCATEGORIZED_NAME)

        if existing is not None:
            return existing

        uncategorized = Category(
            name=UNCATEGORIZED_NAME,
            description="Pages that could not be classified into any known category.",
            keywords=None,
            url_patterns=None,
            is_active=True,
        )
        session.add(uncategorized)
        await session.flush()
        return uncategorized


    #---------------------------------------------------------------------------
    # JOBS
    async def create_job(
        self,
        session: AsyncSession,
        name: str,
        start_url: str,
        crawl_mode: CrawlMode,
        url_rules: Optional[List[Dict]] = None,
        data_targets: Optional[List[str]] = None,
        category_id: Optional[uuid.UUID] = None,
        filter_category_ids: Optional[List[str]] = None,
        credential_id: Optional[uuid.UUID] = None,
        js_mode: str = "auto",
    ) -> Job:
        """
        Create a new job.
        """
        job = Job(
            name=name,
            start_url=start_url,
            crawl_mode=crawl_mode,
            url_rules=url_rules,
            data_targets=data_targets,
            category_id=category_id,
            filter_category_ids=filter_category_ids or None,
            credential_id=credential_id,
            js_mode=js_mode,
            status=JobStatus.PENDING,
        )
        session.add(job)
        await session.flush()
        return job

    async def get_job(
        self,
        session: AsyncSession,
        job_id: uuid.UUID,
    ) -> Optional[Job]:
        """Fetch a single job by ID."""
        result = await session.execute(
            select(Job).where(Job.id == job_id)
        )
        return result.scalar_one_or_none()

    async def list_jobs(
        self,
        session: AsyncSession,
        status: Optional[JobStatus] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[Job]:
        """List jobs, optionally filtered by status, newest first."""
        query = select(Job).order_by(Job.created_at.desc()).limit(limit).offset(offset)
        if status is not None:
            query = query.where(Job.status == status)
        result = await session.execute(query)
        return result.scalars().all()

    async def update_job_status(
        self,
        session: AsyncSession,
        job_id: uuid.UUID,
        status: JobStatus,
        error: Optional[str] = None,
        celery_task_id: Optional[str] = None,
    ) -> Optional[Job]:
        """Update a job's status, optionally setting a last_error or celery_task_id."""
        values: Dict[str, Any] = {"status": status}
        if error is not None:
            values["last_error"] = error
        if celery_task_id is not None:
            values["celery_task_id"] = celery_task_id
        await session.execute(
            update(Job).where(Job.id == job_id).values(**values)
        )
        await session.flush()
        return await self.get_job(session, job_id)

    async def update_job_progress(
        self,
        session: AsyncSession,
        job_id: uuid.UUID,
        pages_scraped: Optional[int] = None,
        pages_failed: Optional[int] = None,
        pages_discovered: Optional[int] = None,
        scrape_speed: Optional[float] = None,
    ) -> None:
        """Update live progress metrics for a running job."""
        values: Dict[str, Any] = {}
        if pages_scraped is not None:
            values["pages_scraped"] = pages_scraped
        if pages_failed is not None:
            values["pages_failed"] = pages_failed
        if pages_discovered is not None:
            values["total_pages_discovered"] = pages_discovered
        if scrape_speed is not None:
            values["pages_per_second"] = scrape_speed
        if values:
            await session.execute(
                update(Job).where(Job.id == job_id).values(**values)
            )
            await session.flush()

    async def delete_job(
        self,
        session: AsyncSession,
        job_id: uuid.UUID,
    ) -> bool:
        """Delete a job and all cascade-linked data."""
        result = await session.execute(
            delete(Job).where(Job.id == job_id)
        )
        await session.flush()
        return result.rowcount > 0

    async def count_jobs(
        self,
        session: AsyncSession,
        status: Optional[JobStatus] = None,
    ) -> int:
        """Count jobs, optionally by status."""
        query = select(func.count(Job.id))
        if status is not None:
            query = query.where(Job.status == status)
        result = await session.execute(query)
        return result.scalar_one()


    #---------------------------------------------------------------------------
    # SCRAPE RESULTS
    @staticmethod
    def _compute_content_hash(content: Any) -> str:
        """Produce a SHA-256 hash of serialized content for diff detection."""
        serialized = json.dumps(content, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    async def store_scrape_result(
        self,
        session: AsyncSession,
        job_id: uuid.UUID,
        url: str,
        content: Optional[Dict],
        http_status: Optional[int] = None,
        page_title: Optional[str] = None,
        error: Optional[str] = None,
    ) -> ScrapeResult:
        """
        Store a new scrape result.
        """
        content_hash = self._compute_content_hash(content) if content else None
        content_length = len(json.dumps(content)) if content else 0

        scrape_result = ScrapeResult(
            job_id=job_id,
            url=url,
            http_status=http_status,
            content=content,
            content_hash=content_hash,
            page_title=page_title,
            content_length=content_length,
            error=error,
        )
        session.add(scrape_result)
        await session.flush()

        # Create a content version only if we have actual content with a hash.
        # [] is falsy in Python, so both checks must pass.
        if content and content_hash:
            await self._create_content_version(
                session=session,
                scrape_result=scrape_result,
                content=content,
                content_hash=content_hash,
            )

        return scrape_result

    async def _create_content_version(
        self,
        session: AsyncSession,
        scrape_result: ScrapeResult,
        content: Dict,
        content_hash: str,
    ) -> ContentVersion:
        """
        Internal: create a content version entry.
        Checks for the most recent previous version of the same URL.
        If one exists and content differs, stores only the diff.
        If none exists, stores a full snapshot.
        """
        prev_version_query = (
            select(ContentVersion)
            .join(ScrapeResult, ContentVersion.scrape_result_id == ScrapeResult.id)
            .where(ScrapeResult.url == scrape_result.url)
            .order_by(ContentVersion.version_number.desc())
            .limit(1)
        )
        prev_result = await session.execute(prev_version_query)
        prev_version: Optional[ContentVersion] = prev_result.scalar_one_or_none()

        if prev_version is None:
            version = ContentVersion(
                scrape_result_id=scrape_result.id,
                version_number=1,
                content_hash=content_hash,
                is_snapshot=True,
                full_content=content,
                diff_content=None,
                change_summary="Initial snapshot",
                blocks_changed=len(content) if isinstance(content, list) else 0,
            )
            session.add(version)
            await session.flush()
            return version

        if prev_version.content_hash == content_hash:
            return prev_version

        prev_content = prev_version.full_content or []
        diff = self._compute_diff(prev_content, content)
        blocks_changed = (
            len(diff.get("added", []))
            + len(diff.get("removed", []))
            + len(diff.get("modified", []))
        )

        version = ContentVersion(
            scrape_result_id=scrape_result.id,
            version_number=prev_version.version_number + 1,
            content_hash=content_hash,
            is_snapshot=False,
            full_content=None,
            diff_content=diff,
            change_summary=f"{blocks_changed} block(s) changed",
            blocks_changed=blocks_changed,
        )
        session.add(version)
        await session.flush()
        return version

    @staticmethod
    def _compute_diff(
        old_content: List[Dict],
        new_content: List[Dict],
    ) -> Dict:
        """Produce a structured diff between two content block lists."""
        old_by_index = {i: block for i, block in enumerate(old_content)}
        new_by_index = {i: block for i, block in enumerate(new_content)}

        added: List[Dict] = []
        removed: List[Dict] = []
        modified: List[Dict] = []

        for idx, new_block in new_by_index.items():
            if idx not in old_by_index:
                added.append(new_block)
            elif old_by_index[idx] != new_block:
                modified.append({"index": idx, "old": old_by_index[idx], "new": new_block})

        for idx, old_block in old_by_index.items():
            if idx not in new_by_index:
                removed.append(old_block)

        return {"added": added, "removed": removed, "modified": modified}

    @staticmethod
    def _apply_diff(content: Any, diff: Dict) -> List[Dict]:
        """Reconstruct content by applying a diff. Inverse of _compute_diff."""
        blocks = list(content) if isinstance(content, list) else [content]

        for mod in diff.get("modified", []):
            idx = mod.get("index", 0)
            if idx < len(blocks):
                blocks[idx] = mod["new"]

        removed_texts = {
            block.get("content", "") for block in diff.get("removed", [])
            if isinstance(block, dict)
        }
        blocks = [
            b for b in blocks
            if not (isinstance(b, dict) and b.get("content", "") in removed_texts)
        ]

        for block in diff.get("added", []):
            blocks.append(block)

        return blocks

    async def get_scrape_results(
        self,
        session: AsyncSession,
        job_id: uuid.UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[ScrapeResult]:
        """List scrape results for a job, newest first."""
        query = (
            select(ScrapeResult)
            .where(ScrapeResult.job_id == job_id)
            .order_by(ScrapeResult.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await session.execute(query)
        return result.scalars().all()

    async def get_content_versions(
        self,
        session: AsyncSession,
        url: str,
    ) -> Sequence[ContentVersion]:
        """Get all content versions for a URL, ordered by version number."""
        query = (
            select(ContentVersion)
            .join(ScrapeResult, ContentVersion.scrape_result_id == ScrapeResult.id)
            .where(ScrapeResult.url == url)
            .order_by(ContentVersion.version_number.asc())
        )
        result = await session.execute(query)
        return result.scalars().all()


    #---------------------------------------------------------------------------
    # CATEGORIES
    async def create_category(
        self,
        session: AsyncSession,
        name: str,
        description: Optional[str] = None,
        keywords: Optional[List[str]] = None,
        url_patterns: Optional[List[Dict]] = None,
    ) -> Category:
        """Create a new category."""
        category = Category(
            name=name,
            description=description,
            keywords=keywords,
            url_patterns=url_patterns,
        )
        session.add(category)
        await session.flush()
        return category

    async def get_category(
        self,
        session: AsyncSession,
        category_id: uuid.UUID,
    ) -> Optional[Category]:
        """Fetch a category by ID."""
        result = await session.execute(
            select(Category).where(Category.id == category_id)
        )
        return result.scalar_one_or_none()

    async def get_category_by_name(
        self,
        session: AsyncSession,
        name: str,
    ) -> Optional[Category]:
        """
        Fetch a category by its exact name (case-insensitive).
        Returns None if no category with that name exists.
        """
        result = await session.execute(
            select(Category).where(func.lower(Category.name) == name.lower())
        )
        return result.scalar_one_or_none()

    async def get_or_create_category_by_name(
        self,
        session: AsyncSession,
        name: str,
    ) -> tuple[Category, bool]:
        """
        Return the category with the given name, creating it if it doesn't exist.

        Returns:
            (category, created) created is True if a new row was inserted.
        """
        existing = await self.get_category_by_name(session, name)
        if existing is not None:
            return existing, False

        new_category = Category(
            name=name,
            description="Auto-created by AI classifier",
            keywords=None,
            url_patterns=None,
            is_active=True,
        )
        session.add(new_category)
        await session.flush()
        return new_category, True

    async def list_categories(
        self,
        session: AsyncSession,
        active_only: bool = True,
    ) -> Sequence[Category]:
        """List all categories alphabetically, optionally filtering to active."""
        query = select(Category).order_by(Category.name)
        if active_only:
            query = query.where(Category.is_active == True)
        result = await session.execute(query)
        return result.scalars().all()

    async def update_category(
        self,
        session: AsyncSession,
        category_id: uuid.UUID,
        name: Optional[str] = None,
        description: Optional[str] = None,
        keywords: Optional[List[str]] = None,
        url_patterns: Optional[List[Dict]] = None,
        is_active: Optional[bool] = None,
    ) -> Optional[Category]:
        """
        Update a category.
        """
        # Guard: never rename Uncategorized
        if name is not None:
            current = await self.get_category(session, category_id)
            if current is not None and current.name == UNCATEGORIZED_NAME:
                raise ProtectedCategoryError(UNCATEGORIZED_NAME, "renamed")

        values: Dict[str, Any] = {}
        if name is not None:
            values["name"] = name
        if description is not None:
            values["description"] = description
        if keywords is not None:
            values["keywords"] = keywords
        if url_patterns is not None:
            values["url_patterns"] = url_patterns
        if is_active is not None:
            values["is_active"] = is_active

        if values:
            await session.execute(
                update(Category).where(Category.id == category_id).values(**values)
            )
            await session.flush()

        return await self.get_category(session, category_id)

    async def delete_category(
        self,
        session: AsyncSession,
        category_id: uuid.UUID,
    ) -> bool:
        """
        Delete a category and all cascade-linked data.
        """
        # Guard: never delete Uncategorized
        category = await self.get_category(session, category_id)
        if category is not None and category.name == UNCATEGORIZED_NAME:
            raise ProtectedCategoryError(UNCATEGORIZED_NAME, "deleted")

        # Guard: never delete if still in use
        usage_count_result = await session.execute(
            select(func.count())
            .select_from(scrape_result_categories)
            .where(scrape_result_categories.c.category_id == category_id)
        )
        usage_count: int = usage_count_result.scalar_one()

        if usage_count > 0:
            raise CategoryInUseError(category_id=category_id, usage_count=usage_count)

        result = await session.execute(
            delete(Category).where(Category.id == category_id)
        )
        await session.flush()
        return result.rowcount > 0

    async def assign_categories_to_result(
        self,
        session: AsyncSession,
        scrape_result_id: uuid.UUID,
        category_ids: List[uuid.UUID],
    ) -> None:
        """
        Assign categories to a specific scrape result.
        """
        await session.execute(
            delete(scrape_result_categories).where(
                scrape_result_categories.c.scrape_result_id == scrape_result_id
            )
        )

        if not category_ids:
            await session.flush()
            return

        rows = [
            {"scrape_result_id": scrape_result_id, "category_id": cid}
            for cid in category_ids
        ]
        await session.execute(scrape_result_categories.insert(), rows)
        await session.flush()

    async def get_categories_for_result(
        self,
        session: AsyncSession,
        scrape_result_id: uuid.UUID,
    ) -> List[Category]:
        """
        Return all categories assigned to a specific scrape result,
        sorted alphabetically by name.
        """
        query = (
            select(Category)
            .join(
                scrape_result_categories,
                scrape_result_categories.c.category_id == Category.id,
            )
            .where(scrape_result_categories.c.scrape_result_id == scrape_result_id)
            .order_by(Category.name)
        )
        result = await session.execute(query)
        return list(result.scalars().all())


    #---------------------------------------------------------------------------
    # CREDENTIALS
    async def create_credential(
        self,
        session: AsyncSession,
        domain: str,
        username: str,
        encrypted_password: str,
        login_url: Optional[str] = None,
        username_selector: Optional[str] = None,
        password_selector: Optional[str] = None,
        submit_selector: Optional[str] = None,
    ) -> Credential:
        """Store a new credential (password must already be encrypted)."""
        credential = Credential(
            domain=domain,
            username=username,
            encrypted_password=encrypted_password,
            login_url=login_url,
            username_selector=username_selector,
            password_selector=password_selector,
            submit_selector=submit_selector,
        )
        session.add(credential)
        await session.flush()
        return credential

    async def get_credential(
        self,
        session: AsyncSession,
        credential_id: uuid.UUID,
    ) -> Optional[Credential]:
        """Fetch a credential by ID."""
        result = await session.execute(
            select(Credential).where(Credential.id == credential_id)
        )
        return result.scalar_one_or_none()

    async def get_credential_by_domain(
        self,
        session: AsyncSession,
        domain: str,
    ) -> Optional[Credential]:
        """Fetch the first credential stored for a given domain."""
        result = await session.execute(
            select(Credential).where(Credential.domain == domain).limit(1)
        )
        return result.scalar_one_or_none()

    async def list_credentials(
        self,
        session: AsyncSession,
    ) -> Sequence[Credential]:
        """List all credentials."""
        result = await session.execute(
            select(Credential).order_by(Credential.domain)
        )
        return result.scalars().all()

    async def update_credential(
        self,
        session: AsyncSession,
        credential_id: uuid.UUID,
        username: Optional[str] = None,
        encrypted_password: Optional[str] = None,
        login_url: Optional[str] = None,
        username_selector: Optional[str] = None,
        password_selector: Optional[str] = None,
        submit_selector: Optional[str] = None,
    ) -> Optional[Credential]:
        """Update a credential's fields."""
        values: Dict[str, Any] = {}
        if username is not None:
            values["username"] = username
        if encrypted_password is not None:
            values["encrypted_password"] = encrypted_password
        if login_url is not None:
            values["login_url"] = login_url
        if username_selector is not None:
            values["username_selector"] = username_selector
        if password_selector is not None:
            values["password_selector"] = password_selector
        if submit_selector is not None:
            values["submit_selector"] = submit_selector

        if values:
            await session.execute(
                update(Credential).where(Credential.id == credential_id).values(**values)
            )
            await session.flush()

        return await self.get_credential(session, credential_id)

    async def delete_credential(
        self,
        session: AsyncSession,
        credential_id: uuid.UUID,
    ) -> bool:
        """Delete a credential."""
        result = await session.execute(
            delete(Credential).where(Credential.id == credential_id)
        )
        await session.flush()
        return result.rowcount > 0


    #---------------------------------------------------------------------------
    # LOG ENTRIES
    async def create_log_entry(
        self,
        session: AsyncSession,
        job_id: uuid.UUID,
        message: str,
        level: LogLevel = LogLevel.INFO,
        source_url: Optional[str] = None,
        component: Optional[str] = None,
    ) -> LogEntry:
        """Create a log entry for a job."""
        entry = LogEntry(
            job_id=job_id,
            message=message,
            level=level,
            source_url=source_url,
            component=component,
        )
        session.add(entry)
        await session.flush()
        return entry

    async def get_log_entries(
        self,
        session: AsyncSession,
        job_id: uuid.UUID,
        limit: int = 200,
        offset: int = 0,
        level: Optional[LogLevel] = None,
    ) -> Sequence[LogEntry]:
        """Get log entries for a job, oldest first."""
        query = (
            select(LogEntry)
            .where(LogEntry.job_id == job_id)
            .order_by(LogEntry.created_at.asc())
            .limit(limit)
            .offset(offset)
        )
        if level is not None:
            query = query.where(LogEntry.level == level)
        result = await session.execute(query)
        return result.scalars().all()

    async def count_log_entries(
        self,
        session: AsyncSession,
        job_id: uuid.UUID,
    ) -> int:
        """Count log entries for a job."""
        result = await session.execute(
            select(func.count(LogEntry.id)).where(LogEntry.job_id == job_id)
        )
        return result.scalar_one()

    async def delete_old_log_entries(
        self,
        session: AsyncSession,
        older_than_days: int = 30,
    ) -> int:
        """Delete log entries older than the specified number of days."""
        from datetime import timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
        result = await session.execute(
            delete(LogEntry).where(LogEntry.created_at < cutoff)
        )
        await session.flush()
        return result.rowcount


    #---------------------------------------------------------------------------
    # ANALYTICS
    async def get_stats(
        self,
        session: AsyncSession,
    ) -> Dict[str, int]:
        """Return overall system statistics."""
        total_jobs = await self.count_jobs(session)
        running_jobs = await self.count_jobs(session, status=JobStatus.RUNNING)

        pages_result = await session.execute(select(func.sum(Job.pages_scraped)))
        total_pages: int = pages_result.scalar_one() or 0

        versions_result = await session.execute(select(func.count(ContentVersion.id)))
        total_versions: int = versions_result.scalar_one() or 0

        errors_result = await session.execute(select(func.sum(Job.pages_failed)))
        total_errors: int = errors_result.scalar_one() or 0

        return {
            "total_jobs": total_jobs,
            "running_jobs": running_jobs,
            "total_pages_scraped": total_pages,
            "total_content_versions": total_versions,
            "total_errors": total_errors,
        }

    async def get_scrape_volume(
        self,
        session: AsyncSession,
        days: int = 14,
    ) -> List[Dict]:
        """Return daily scrape counts for the past N days."""
        from sqlalchemy import text
        sql = text("""
            SELECT
                DATE(created_at) AS scrape_date,
                COUNT(*) AS page_count
            FROM scrape_results
            WHERE created_at >= NOW() - make_interval(days => :days)
            GROUP BY DATE(created_at)
            ORDER BY scrape_date ASC
        """)
        result = await session.execute(sql, {"days": days})
        return [
            {"date": str(row.scrape_date), "count": row.page_count}
            for row in result
        ]

    async def get_category_distribution(
        self,
        session: AsyncSession,
    ) -> List[Dict]:
        """Return count of scrape results per category via the join table."""
        query = (
            select(
                Category.name,
                func.count(scrape_result_categories.c.scrape_result_id).label("count"),
            )
            .join(
                scrape_result_categories,
                scrape_result_categories.c.category_id == Category.id,
            )
            .group_by(Category.name)
            .order_by(func.count(scrape_result_categories.c.scrape_result_id).desc())
        )
        result = await session.execute(query)
        return [{"category": row.name, "count": row.count} for row in result]
