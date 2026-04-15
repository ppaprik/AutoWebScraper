#======================================================================================================
# Multi-stage build: dependencies first (cached), then application code.
#======================================================================================================


#----------------------------------------------------------------------------------------------------
# Stage 1: Base image with system dependencies

FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        libxml2-dev \
        libxslt1-dev \
        libpq-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*


#----------------------------------------------------------------------------------------------------
# Stage 2: Install Python dependencies (cached layer)
FROM base AS dependencies

WORKDIR /WebScraper

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Install Playwright system-level dependencies (needs root, uses apt-get).
# Done here in the dependencies stage so it is cached separately from code.
RUN playwright install-deps chromium


#----------------------------------------------------------------------------------------------------
# Stage 3: Final application image

FROM dependencies AS application

WORKDIR /WebScraper

COPY . .

RUN chmod +x /WebScraper/entrypoint.sh

# THIS WAS PAIN FOR SOME REASON :(
# Create non-root user. /model_cache is created with correct ownership so Docker's named-volume mount doesn't produce a root-owned directory.
# PLAYWRIGHT_BROWSERS_PATH is set so the browser lives in a known location that we can chown before switching users.
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/playwright-browsers

RUN groupadd --gid 1000 scraper && \
    useradd --uid 1000 --gid 1000 --create-home scraper && \
    mkdir -p /model_cache /opt/playwright-browsers && \
    chown -R scraper:scraper /WebScraper /model_cache /opt/playwright-browsers

    
# Switch to non-root user before installing the browser binary. playwright install chromium downloads ~130MB to PLAYWRIGHT_BROWSERS_PATH.
USER scraper

RUN playwright install chromium

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

ENTRYPOINT ["/WebScraper/entrypoint.sh"]
