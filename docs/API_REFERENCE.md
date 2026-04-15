# API Reference

Base URL: `http://localhost:8000/api`

All request and response bodies use JSON. UUIDs are formatted as standard hyphenated strings.

---

## Health

### GET /health

Returns service status including database and Redis connectivity.

**Response:**

```json
{
  "status": "healthy",
  "service": "webscraper",
  "database": "connected",
  "redis": "connected"
}
```

Status values: `healthy`, `degraded`, `error`.

---

## Jobs

### POST /jobs

Create a new scraping job. The job is immediately queued for execution.

**Request Body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | yes | Job display name (1-255 chars) |
| `start_url` | string | yes | URL to begin scraping |
| `crawl_mode` | string | no | `single` (default), `rule_based`, `infinite`, `category` |
| `url_rules` | array | no | URL filtering rules (see Scraping Rules doc) |
| `data_targets` | array | no | `["text"]` (default). Options: `text`, `headers`, `footers`, `ads` |
| `category_id` | UUID | no | Category to assign |
| `credential_id` | UUID | no | Credential for authenticated scraping |

**Example:**

```json
{
  "name": "Blog Scrape",
  "start_url": "https://example.com/blog",
  "crawl_mode": "rule_based",
  "url_rules": [
    {"type": "contains", "pattern": "/blog/"}
  ],
  "data_targets": ["text"]
}
```

**Response:** `201 Created` — returns the full job object.

### GET /jobs

List all jobs with optional filtering.

**Query Parameters:**

| Param | Type | Description |
|-------|------|-------------|
| `status` | string | Filter by status: `pending`, `running`, `paused`, `completed`, `failed`, `stopped` |
| `limit` | int | Max results (default 100, max 500) |
| `offset` | int | Pagination offset (default 0) |

**Response:**

```json
{
  "jobs": [ ...job objects... ],
  "total": 42
}
```

### GET /jobs/{job_id}

Get a single job by its UUID.

**Response:** `200 OK` — full job object, or `404` if not found.

### POST /jobs/{job_id}/action

Execute a control action on a running job.

**Request Body:**

```json
{
  "action": "pause"
}
```

Actions: `pause` (running → paused), `resume` (paused → running), `stop` (any active → stopped).

**Response:** `200 OK` with message, or `400` if the action is invalid for the current status.

### DELETE /jobs/{job_id}

Delete a job and all its scrape results, content versions, and log entries. Running jobs are stopped first.

**Response:** `200 OK` with message, or `404` if not found.

---

## Scrape Results

### GET /scrape/{job_id}/results

List scrape results for a specific job.

**Query Parameters:**

| Param | Type | Description |
|-------|------|-------------|
| `limit` | int | Max results (default 100, max 500) |
| `offset` | int | Pagination offset |

**Response:**

```json
{
  "results": [
    {
      "id": "uuid",
      "job_id": "uuid",
      "url": "https://example.com/page1",
      "http_status": 200,
      "content": [ ...content blocks... ],
      "content_hash": "sha256...",
      "page_title": "Page Title",
      "content_length": 1234,
      "error": null,
      "created_at": "2024-01-15T10:30:00Z"
    }
  ],
  "total": 15
}
```

### GET /scrape/versions

Get the content version history for a specific URL.

**Query Parameters:**

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `url` | string | yes | The URL to get version history for |

**Response:** Array of version objects:

```json
[
  {
    "id": "uuid",
    "version_number": 1,
    "content_hash": "sha256...",
    "is_snapshot": true,
    "full_content": [ ...blocks... ],
    "diff_content": null,
    "change_summary": "Initial snapshot",
    "blocks_changed": 0,
    "created_at": "2024-01-15T10:30:00Z"
  },
  {
    "id": "uuid",
    "version_number": 2,
    "is_snapshot": false,
    "full_content": null,
    "diff_content": {
      "added": [...],
      "removed": [...],
      "modified": [...]
    },
    "change_summary": "3 block(s) changed",
    "blocks_changed": 3
  }
]
```

---

## Categories

### POST /categories

Create a new category.

**Request Body:**

```json
{
  "name": "Technology",
  "description": "Tech news and articles",
  "keywords": ["software", "programming", "API", "cloud"],
  "url_patterns": [
    {"type": "domain", "pattern": "techcrunch.com"},
    {"type": "contains", "pattern": "/tech/"}
  ]
}
```

**Response:** `201 Created` — full category object.

### GET /categories

List all categories.

**Response:**

```json
{
  "categories": [ ...category objects... ]
}
```

### GET /categories/{category_id}

Get a single category.

### PUT /categories/{category_id}

Update a category. All fields are optional — only provided fields are changed.

```json
{
  "name": "Tech & Science",
  "keywords": ["software", "AI", "research"],
  "is_active": false
}
```

### DELETE /categories/{category_id}

Delete a category. Returns `404` if not found.

---

## Credentials

### POST /credentials

Store a new credential. The password is encrypted before storage and never returned in any response.

**Request Body:**

```json
{
  "domain": "example.com",
  "username": "myuser",
  "password": "mypassword123",
  "login_url": "https://example.com/login",
  "username_selector": "input[name=\"email\"]",
  "password_selector": "input[name=\"password\"]",
  "submit_selector": "button[type=\"submit\"]"
}
```

Only `domain`, `username`, and `password` are required. Selectors are optional hints for the auto-login system.

**Response:** `201 Created` — credential object (password omitted, `has_password: true` included).

### GET /credentials

List all credentials. Passwords are never included.

### GET /credentials/{credential_id}

Get a single credential (password omitted).

### PUT /credentials/{credential_id}

Update a credential. If `password` is provided, it is re-encrypted. If omitted, the existing password is kept.

### DELETE /credentials/{credential_id}

Delete a credential.

---

## Logs

### GET /logs/{job_id}

Fetch stored log entries for a job.

**Query Parameters:**

| Param | Type | Description |
|-------|------|-------------|
| `level` | string | Filter by level: `debug`, `info`, `warning`, `error`, `critical` |
| `limit` | int | Max entries (default 200, max 1000) |
| `offset` | int | Pagination offset |

**Response:**

```json
{
  "entries": [
    {
      "id": "uuid",
      "job_id": "uuid",
      "level": "info",
      "message": "Scraping: https://example.com/page1",
      "source_url": "https://example.com/page1",
      "component": "scraper",
      "created_at": "2024-01-15T10:30:05Z"
    }
  ],
  "total": 150
}
```

### WebSocket /logs/ws/{job_id}

Connect for real-time log streaming. Messages are JSON objects of two types:

**Log entry:**

```json
{
  "id": "uuid",
  "level": "info",
  "message": "Scraped successfully: 5 blocks extracted",
  "source_url": "https://example.com/page1",
  "component": "scraper",
  "created_at": "2024-01-15T10:30:05Z"
}
```

**Status update (sent every second):**

```json
{
  "type": "status_update",
  "status": "running",
  "pages_scraped": 42,
  "pages_failed": 1,
  "total_pages_discovered": 150,
  "pages_per_second": 2.3
}
```

**Job finished (final message):**

```json
{
  "type": "job_finished",
  "status": "completed"
}
```

The WebSocket closes automatically after the job finishes.

---

## Analytics

### GET /analytics/stats

Overall scraping statistics.

```json
{
  "total_jobs": 25,
  "total_pages_scraped": 1500,
  "total_content_versions": 1800,
  "total_errors": 42,
  "total_content_bytes": 5242880
}
```

### GET /analytics/volume

Daily scrape volume.

**Query Parameters:** `days` (int, default 30, max 365)

```json
[
  {"day": "2024-01-14", "count": 120},
  {"day": "2024-01-15", "count": 95}
]
```

### GET /analytics/categories

Job count per category.

```json
[
  {"category": "Technology", "job_count": 12},
  {"category": "Sports", "job_count": 5}
]
```

### GET /analytics/export/{job_id}

Download scrape results as a file.

**Query Parameters:** `format` — `json` (default) or `csv`

**Response:** File download with appropriate Content-Type and Content-Disposition headers.

---

## Error Responses

All errors return a JSON body:

```json
{
  "detail": "Job not found"
}
```

| Status | Meaning |
|--------|---------|
| `400` | Invalid request (bad action, invalid status filter) |
| `404` | Resource not found |
| `422` | Validation error (missing/invalid fields) |
| `500` | Internal server error |
