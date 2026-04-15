#======================================================================================================
# Settings service
#======================================================================================================

from __future__ import annotations

import configparser
import os
import threading
from pathlib import Path
from typing import Dict, List, Set, Tuple

from backend.logging_config import get_logger

logger = get_logger("settings_service")


# File paths — must match compose.yaml volume mounts
CONFIG_PATH: Path = Path("/WebScraper/.config")
ENV_PATH: Path = Path("/WebScraper/.env")

# Single write lock prevents concurrent requests from corrupting files
_write_lock: threading.Lock = threading.Lock()

# .env keys that must never be edited via the UI
PROTECTED_ENV_KEYS: Set[str] = {
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_DB",
    "POSTGRES_HOST",
    "POSTGRES_PORT",
    "REDIS_HOST",
    "REDIS_PORT",
    "REDIS_DB",
    "ENCRYPTION_KEY",
    "API_HOST",
    "API_PORT",
    "CELERY_BROKER_URL",
    "CELERY_RESULT_BACKEND",
}

# .env keys that ARE editable — the full allowed set
MUTABLE_ENV_KEYS: Set[str] = {
    "API_LOG_LEVEL",
    "CELERY_WORKER_CONCURRENCY",
    "SCRAPER_DEFAULT_TIMEOUT",
    "SCRAPER_MAX_RETRIES",
    "SCRAPER_RETRY_DELAY",
    "SCRAPER_USER_AGENT",
    "SCRAPER_MAX_CONCURRENT_REQUESTS",
    "SCRAPER_RESPECT_ROBOTS_TXT",
    "SCRAPER_DEFAULT_DELAY_BETWEEN_REQUESTS",
}


#----------------------------------------------------------------------------------------------------
# Low-level file readers
def _read_config_file() -> Dict[str, Dict[str, str]]:
    """
    Parse the .config file and return a dict of {section: {key: value}}
    """
    parser = configparser.RawConfigParser()

    if CONFIG_PATH.exists():
        parser.read(CONFIG_PATH)

    result: Dict[str, Dict[str, str]] = {}

    for section in parser.sections():
        result[section] = dict(parser.items(section))

    return result


def _read_env_file() -> Dict[str, str]:
    """
    Parse the .env file and return a dict of {key: value}
    """
    env_values: Dict[str, str] = {}

    if not ENV_PATH.exists():
        return env_values

    for raw_line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()

        if not line or line.startswith("#"):
            continue

        if "=" not in line:
            continue

        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()

        # Strip surrounding single or double quotes
        if (value.startswith('"') and value.endswith('"')) or \
           (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]

        env_values[key] = value

    return env_values


#----------------------------------------------------------------------------------------------------
# Low-level file writers
def _write_config_file(sections: Dict[str, Dict[str, str]]) -> None:
    """
    Write all config sections to the .config file.
    Writes directly to the file (no temp+rename) — same reason as above.
    """
    lines: List[str] = []

    for section_name, keys in sections.items():
        lines.append(f"[{section_name}]")

        for key, value in keys.items():
            lines.append(f"{key} = {value}")

        lines.append("")  # blank line between sections

    content = "\n".join(lines)
    CONFIG_PATH.write_text(content, encoding="utf-8")


def _write_env_file(env_values: Dict[str, str]) -> None:
    """
    Write all env values to the .env file.
    Writes directly to the file (no temp+rename) — same reason as above.
    """
    comment_lines: List[str] = []

    if ENV_PATH.exists():
        for raw_line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            stripped = raw_line.strip()
            if stripped.startswith("#") or stripped == "":
                comment_lines.append(raw_line)

    lines: List[str] = list(comment_lines)
    lines.append("")

    for key, value in sorted(env_values.items()):
        lines.append(f"{key}={value}")

    content = "\n".join(lines) + "\n"
    ENV_PATH.write_text(content, encoding="utf-8")


#----------------------------------------------------------------------------------------------------
# Cache invalidation
def _invalidate_app_config_cache() -> None:
    """
    Clear the app_config cache
    """
    try:
        from backend.config import get_app_config
        get_app_config.cache_clear()
        logger.info("app_config_cache_cleared")
    except Exception as exc:
        logger.warning("cache_clear_failed", error=str(exc))


#----------------------------------------------------------------------------------------------------
# Public API
def get_all_settings() -> Dict:
    """
    Return all current settings
    """
    config_data = _read_config_file()

    env_data: Dict[str, str] = {}
    for key in sorted(MUTABLE_ENV_KEYS):
        env_data[key] = os.environ.get(key, "")

    return {
        "config": config_data,
        "env": env_data,
        "requires_restart": False,
    }


def apply_settings(
    config_updates: Dict[str, Dict[str, str]] | None,
    env_updates: Dict[str, str] | None,
) -> Tuple[bool, List[str]]:
    """
    Update settings and return a tuple of (requires_restart, changed_keys)
    """
    requires_restart: bool = False
    changed_keys: List[str] = []

    with _write_lock:
        #---------------------------------------------------------------------------
        # Apply .config changes (hot-reloadable)
        if config_updates:
            current_config = _read_config_file()

            for section_name, section_values in config_updates.items():
                if section_name not in current_config:
                    current_config[section_name] = {}

                for key, value in section_values.items():
                    old_value = current_config[section_name].get(key)

                    if str(old_value) != str(value):
                        current_config[section_name][key] = str(value)
                        changed_keys.append(f"config.{section_name}.{key}")
                        logger.info(
                            "config_key_updated",
                            section=section_name,
                            key=key,
                            old=old_value,
                            new=value,
                        )

            if any(k.startswith("config.") for k in changed_keys):
                _write_config_file(current_config)
                _invalidate_app_config_cache()

        #---------------------------------------------------------------------------
        # Apply .env changes (requires restart)
        if env_updates:
            # Validate all keys before writing anything
            for key in env_updates:
                if key in PROTECTED_ENV_KEYS:
                    raise ValueError(
                        f"'{key}' is a protected setting and cannot be changed "
                        f"from the UI. Edit .env manually and restart."
                    )
                if key not in MUTABLE_ENV_KEYS:
                    raise ValueError(
                        f"'{key}' is not a recognised mutable setting. "
                        f"Allowed keys: {sorted(MUTABLE_ENV_KEYS)}"
                    )

            current_env = _read_env_file()
            env_changed: List[str] = []

            for key, new_value in env_updates.items():
                old_value = current_env.get(key, "")

                if old_value != str(new_value):
                    current_env[key] = str(new_value)
                    env_changed.append(key)
                    changed_keys.append(f"env.{key}")
                    logger.info("env_key_updated", key=key)

            if env_changed:
                _write_env_file(current_env)
                requires_restart = True

    return requires_restart, changed_keys
