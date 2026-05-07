from __future__ import annotations

from pathlib import Path


def load_environment() -> None:
    """
    Load local env files when present.

    Order:
    1. .env
    2. .env.local (overrides .env)

    This keeps local development predictable while still letting real hosting
    environments override values with true process-level environment variables.
    """

    try:
        from dotenv import load_dotenv
    except Exception:
        return

    base_dir = Path(__file__).resolve().parent.parent
    env_file = base_dir / ".env"
    env_local_file = base_dir / ".env.local"

    if env_file.exists():
        load_dotenv(env_file, override=False)

    if env_local_file.exists():
        load_dotenv(env_local_file, override=True)
