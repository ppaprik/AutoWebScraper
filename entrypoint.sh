#!/bin/bash
#======================================================================================================
# Orders which service to start based on the SERVICE_ROLE env var.
# Roles: api (default), celery-worker, celery-beat
#======================================================================================================


set -euo pipefail


#----------------------------------------------------------------------------------------------------
# Defaults
SERVICE_ROLE="${SERVICE_ROLE:-api}"
API_HOST="${API_HOST:-0.0.0.0}"
API_PORT="${API_PORT:-8000}"
API_LOG_LEVEL="${API_LOG_LEVEL:-info}"
CELERY_WORKER_CONCURRENCY="${CELERY_WORKER_CONCURRENCY:-4}"


#----------------------------------------------------------------------------------------------------
# Wait for PostgreSQL to be ready
wait_for_postgres() {
    echo "[entrypoint] Waiting for PostgreSQL at ${POSTGRES_HOST}:${POSTGRES_PORT}..."
    local retries=30
    local count=0
    while [ $count -lt $retries ]; do
        if python -c "
import socket, sys
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(2)
try:
    s.connect(('${POSTGRES_HOST}', ${POSTGRES_PORT}))
    s.close()
    sys.exit(0)
except Exception:
    sys.exit(1)
" 2>/dev/null; then
            echo "[entrypoint] PostgreSQL is ready."
            return 0
        fi
        count=$((count + 1))
        echo "[entrypoint] PostgreSQL not ready yet (attempt ${count}/${retries})..."
        sleep 2
    done
    echo "[entrypoint] ERROR: PostgreSQL did not become ready in time."
    exit 1
}


#----------------------------------------------------------------------------------------------------
# Wait for Redis to be ready
wait_for_redis() {
    echo "[entrypoint] Waiting for Redis at ${REDIS_HOST}:${REDIS_PORT}..."
    local retries=20
    local count=0
    while [ $count -lt $retries ]; do
        if python -c "
import socket, sys
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(2)
try:
    s.connect(('${REDIS_HOST}', ${REDIS_PORT}))
    s.close()
    sys.exit(0)
except Exception:
    sys.exit(1)
" 2>/dev/null; then
            echo "[entrypoint] Redis is ready."
            return 0
        fi
        count=$((count + 1))
        echo "[entrypoint] Redis not ready yet (attempt ${count}/${retries})..."
        sleep 2
    done
    echo "[entrypoint] ERROR: Redis did not become ready in time."
    exit 1
}


#----------------------------------------------------------------------------------------------------
# Run database migrations
run_migrations() {
    echo "[entrypoint] Running Alembic database migrations..."
    cd /WebScraper/backend/database
    python -m alembic upgrade head
    cd /WebScraper
    echo "[entrypoint] Migrations complete."
}


#----------------------------------------------------------------------------------------------------
# Main
echo "[entrypoint] Starting WebScraper — role: ${SERVICE_ROLE}"


#---------------------------------------------------------------------------
# celery-beat only needs Redis, not PostgreSQL
if [ "${SERVICE_ROLE}" != "celery-beat" ]; then
    wait_for_postgres
fi
wait_for_redis

case "${SERVICE_ROLE}" in
    api)
        run_migrations
        echo "[entrypoint] Launching FastAPI on ${API_HOST}:${API_PORT}..."
        exec python -m uvicorn WebScraper:app \
            --host "${API_HOST}" \
            --port "${API_PORT}" \
            --log-level "${API_LOG_LEVEL}" \
            --ws websockets
        ;;

    celery-worker)
        echo "[entrypoint] Launching Celery worker (concurrency=${CELERY_WORKER_CONCURRENCY})..."
        exec python -m celery \
            -A backend.tasks.celery_app worker \
            --loglevel=info \
            --concurrency="${CELERY_WORKER_CONCURRENCY}" \
            --pool=prefork \
            -n "worker@%h"
        ;;

    celery-beat)
        echo "[entrypoint] Launching Celery Beat scheduler..."
        exec python -m celery \
            -A backend.tasks.celery_app beat \
            --loglevel=info
        ;;

    *)
        echo "[entrypoint] ERROR: Unknown SERVICE_ROLE '${SERVICE_ROLE}'."
        echo "  Valid roles: api, celery-worker, celery-beat"
        exit 1
        ;;
esac
