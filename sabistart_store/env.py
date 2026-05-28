from __future__ import annotations

import os
import sys
from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def ensure_project_root_on_path() -> None:
    """
    Ensure sibling top-level apps like ``public`` and ``dashboard`` are importable.

    Some hosts import the WSGI/ASGI entrypoint by absolute file path instead of
    executing from the repository root. In that case, Django can still import
    ``sabistart_store`` but fail to resolve sibling app packages unless the
    project root is added to ``sys.path`` explicitly.
    """

    base_dir = project_root()
    base_dir_str = str(base_dir)
    if base_dir_str not in sys.path:
        sys.path.insert(0, base_dir_str)


def load_environment() -> None:
    """
    Load local env files when present.

    Order:
    1. SABISTART_ENV_FILE (when explicitly provided)
    2. .env
    3. .env.local (overrides .env)

    This keeps local development predictable while still letting real hosting
    environments override values with true process-level environment variables.
    """

    try:
        from dotenv import load_dotenv
    except Exception:
        return

    base_dir = project_root()
    explicit_env_file = os.getenv("SABISTART_ENV_FILE", "").strip()
    explicit_override = os.getenv("SABISTART_ENV_OVERRIDE", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    env_file = base_dir / ".env"
    env_local_file = base_dir / ".env.local"

    if explicit_env_file:
        candidate = Path(explicit_env_file).expanduser()
        if candidate.exists():
            load_dotenv(candidate, override=explicit_override)

    if env_file.exists():
        load_dotenv(env_file, override=False)

    if env_local_file.exists():
        load_dotenv(env_local_file, override=True)
