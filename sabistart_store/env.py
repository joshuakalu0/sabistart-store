from __future__ import annotations

import os
from pathlib import Path


def env_path(name: str, default: Path) -> Path:
    """
    Get a path from an environment variable, with fallback to a default.
    
    Note: Unlike the previous implementation, this function does NOT perform
    tilde expansion. In containerized deployment environments, relying on
    tilde expansion via the HOME environment variable can be problematic
    because the HOME variable may not be set correctly. For reliable behavior,
    use absolute paths in environment variables.
    
    Args:
        name: The name of the environment variable
        default: The default path to return if the environment variable is not set or empty
        
    Returns:
        Path object representing the configured path
    """
    raw_value = os.getenv(name)
    if not raw_value:
        return default
    return Path(raw_value)