# WebScraper

A scalable, async web scraping system running inside Docker, controlled via a browser-based frontend. Built with FastAPI, Celery, PostgreSQL, Redis, and plain HTML/JS.

---

## Architecture

The system uses a layered concurrency model:

- **Celery + Redis** distributes scraping jobs across CPU cores via a prefork multiprocessing pool
- **asyncio + aiohttp** handles concurrent HTTP requests within each worker process
- **PostgreSQL** stores all scraped content with git-like versioning (diffs, not full duplicates)
- **FastAPI** serves the REST API and static frontend
- **WebSocket** streams job logs to the browser in real-time

### Services

| Container            | Role                                      |
|----------------------|-------------------------------------------|
| `webscraper-api`     | FastAPI app + static frontend             |
| `webscraper-celery-worker` | Executes scrape jobs (prefork pool) |
| `webscraper-celery-beat`   | Periodic task scheduler             |
| `webscraper-postgres`      | PostgreSQL 16 database              |
| `webscraper-redis`         | Redis 7 message broker              |

---

## Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/your-org/WebScraper.git
cd WebScraper
```

### 2. Configure environment

Copy the example files and fill in your values:

```bash
cp .env.example .env
cp .config.example .config
```

Generate an encryption key for credential storage:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Paste the output into `.env` as the `ENCRYPTION_KEY` value.

### 3. Build and start

```bash
docker compose build
docker compose up -d
```

### 4. Access the frontend

Open your browser to:

```
http://localhost:8000
```

### 5. Verify health

```bash
curl http://localhost:8000/api/health
```

Expected response:

```json
{
  "status": "healthy",
  "service": "webscraper",
  "database": "connected",
  "redis": "connected"
}
```

---

## Configuration

### Environment Variables (`.env`)

All secrets and infrastructure connection details live here.

| Variable | Description | Default |
|----------|-------------|---------|
| `POSTGRES_USER` | Database username | `webscraper` |
| `POSTGRES_PASSWORD` | Database password | *(required)* |
| `POSTGRES_DB` | Database name | `webscraper` |
| `POSTGRES_HOST` | Database hostname | `postgres` |
| `POSTGRES_PORT` | Database port | `5432` |
| `REDIS_HOST` | Redis hostname | `redis` |
| `REDIS_PORT` | Redis port | `6379` |
| `ENCRYPTION_KEY` | Fernet key for credential encryption | *(required)* |
| `API_PORT` | FastAPI listening port | `8000` |
| `API_LOG_LEVEL` | Logging verbosity | `info` |
| `CELERY_WORKER_CONCURRENCY` | Worker processes per container | `4` |
| `SCRAPER_DEFAULT_TIMEOUT` | HTTP request timeout (seconds) | `30` |
| `SCRAPER_MAX_RETRIES` | Retry count for failed requests | `3` |
| `SCRAPER_MAX_CONCURRENT_REQUESTS` | Max parallel requests per worker | `10` |
| `SCRAPER_RESPECT_ROBOTS_TXT` | Honor robots.txt | `true` |
| `SCRAPER_DEFAULT_DELAY_BETWEEN_REQUESTS` | Polite delay between requests (seconds) | `1.0` |

### Application Config (`.config`)

Non-secret tuning parameters for scraper behavior, content extraction, code detection, and category definitions. See `.config.example` for the full reference with comments.

Key sections:

- **`[scraper]`** — `max_pages_per_job`, `max_crawl_depth`, `blocked_domains`, `skip_extensions`
- **`[extraction]`** — `min_text_density`, `min_block_words`, `strip_tags`, `strip_classes`
- **`[code_detection]`** — `min_symbol_density`, `code_symbols`
- **`[categories]`** — Default category keyword lists (can also be managed via the frontend)
- **`[logging]`** — `log_retention_days`, `max_log_entries_per_job`

---

## Usage

### Creating a Scrape Job

1. Open the frontend at `http://localhost:8000`
2. Click **New Job** in the sidebar
3. Enter a name and start URL
4. Select a crawl mode:
   - **Single** — scrape one page
   - **Rule-Based** — follow links matching your URL rules
   - **Infinite** — follow all same-domain links (up to configured limits)
   - **Category** — follow links matching a category's URL patterns
5. Optionally add URL rules, select data targets, assign a category or credential
6. Click **Create Job**

The job is queued immediately. Switch to the **Dashboard** to monitor progress.

### Monitoring Jobs

The Dashboard shows all jobs with live status badges, page counts, and speed metrics. Click any job row to open the real-time log stream panel. Use the action buttons to pause, resume, or stop running jobs.

### Exporting Data

Go to **Analytics**, select a job from the export dropdown, and click **Export JSON** or **Export CSV** to download the scraped content.

### Managing Credentials

The **Credentials** view lets you store login credentials for authenticated scraping. Passwords are encrypted at rest using Fernet (AES-128-CBC + HMAC-SHA256). When a job targets a domain with stored credentials, the scraper automatically logs in and persists the session cookies in Redis for reuse.

### Managing Categories

The **Categories** view lets you create classification categories with keyword lists and URL patterns. Categories are used by the rule-based classifier to automatically tag scraped content, and by the Category crawl mode to filter which links to follow.

---

## Content Extraction Pipeline

The extraction engine runs a multi-stage pipeline on every scraped page:

1. **Readability algorithm** — isolates the main content area
2. **DOM filtering** — strips nav, ads, scripts, styles, hidden elements
3. **Code block detection** — finds code via HTML tags, CSS classes, and symbol density analysis. Code is never removed as noise.
4. **Text density scoring** — filters low-quality blocks by text-to-tag ratio
5. **Post-processing** — merges fragments, deduplicates, cleans whitespace
6. **Interleaving** — combines text and code blocks in document order

Output is structured JSON:

```json
[
  {"type": "heading", "level": 1, "content": "Page Title"},
  {"type": "paragraph", "content": "Article text..."},
  {"type": "code_block", "language": "python", "content": "def hello():\n    print('hi')"}
]
```

---

## Content Versioning

Scraped content uses git-like versioning:

- **First scrape** of a URL stores a full snapshot
- **Subsequent scrapes** compare against the previous version using SHA-256 hashes
- If content changed, only the structured diff is stored (added/removed/modified blocks)
- Unchanged content is never duplicated
- Any version can be reconstructed by walking the version chain from the nearest snapshot

---

## Running Tests

Install test dependencies and run:

```bash
pip install -r requirements.txt
pytest tests/ -v
```

Tests use an in-memory SQLite database and don't require Docker, PostgreSQL, or Redis.

---

## Development Workflow

The `compose.yaml` mounts your local source code into the containers via volume mounts, so you don't need to rebuild the Docker image for every code change.

### When to do what

| What changed | What to do |
|---|---|
| Frontend files (HTML, CSS, JS) | Just refresh the browser |
| Backend Python files | `docker compose restart api celery-worker` |
| `.config` | `docker compose restart api celery-worker` |
| `requirements.txt` | `docker compose down && docker compose build --no-cache && docker compose up` |
| `Dockerfile` or `entrypoint.sh` | `docker compose down && docker compose build --no-cache && docker compose up` |
| `compose.yaml` | `docker compose down && docker compose up` |
| Database migration files | `docker compose restart api` (migrations run on API startup) |

### Mounted directories

These local paths are mounted into the `api` and `celery-worker` containers:

```
./backend       → /WebScraper/backend
./frontend      → /WebScraper/frontend  (api only)
./WebScraper.py → /WebScraper/WebScraper.py
./.config       → /WebScraper/.config (read-only)
```

Changes to files in these directories are immediately visible inside the containers.

---

## Project Structure

```
WebScraper/
├── WebScraper.py              # FastAPI app entry point
├── Dockerfile                 # Multi-stage Docker build
├── compose.yaml               # Docker Compose orchestration
├── entrypoint.sh              # Container startup script
├── requirements.txt           # Python dependencies
├── .env.example               # Environment variables template
├── .config.example            # Application config template
├── backend/
│   ├── config.py              # Settings + app config loader
│   ├── logging_config.py      # Structured logging setup
│   ├── api/
│   │   ├── router.py          # API route aggregation
│   │   ├── schemas.py         # Pydantic request/response models
│   │   ├── dependencies.py    # Injectable session + manager
│   │   └── endpoints/         # REST endpoints (7 modules)
│   ├── database/
│   │   ├── connection.py      # Async engine + session factory
│   │   └── migrations/        # Alembic migration scripts
│   ├── src/
│   │   ├── managers/          # Business logic layer (5 managers)
│   │   ├── services/          # Utility services (6 services)
│   │   └── models/            # SQLAlchemy ORM models (6 models)
│   ├── tasks/
│   │   ├── celery_app.py      # Celery configuration
│   │   ├── scrape_tasks.py    # Task definitions
│   │   └── task_manager.py    # Task queue interface
│   └── workers/
│       └── scrape_worker.py   # Worker lifecycle hooks
├── frontend/
│   ├── index.html             # SPA shell
│   ├── css/                   # Stylesheets (7 files)
│   └── js/                    # JavaScript modules (8 files)
├── tests/                     # Test suite (12 files, 80+ tests)
└── docs/                      # Documentation
```

---

## License

This project is provided as-is for personal and educational use.
