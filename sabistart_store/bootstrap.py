from __future__ import annotations

import os
import sys
from pathlib import Path


def bootstrap_paths(base_dir: str | Path) -> Path:
    """
    Prepend project and runtime-vendored package paths to sys.path.

    Vercel can install Python dependencies using a different interpreter than
    the one that later executes build commands or the deployed function. To keep
    compiled dependencies consistent, the build script can vendor packages into
    a temporary directory using the actual runtime Python. When that location is
    exposed through ``SABISTART_RUNTIME_PACKAGES_DIR``, it should win import
    precedence too.
    """

    project_root = Path(base_dir).resolve()
    project_root_str = str(project_root)
    bundled_apps_dir = project_root / "sabistart_store" / "_runtime_apps"
    bundled_apps_dir_str = str(bundled_apps_dir)

    if bundled_apps_dir.exists() and bundled_apps_dir_str not in sys.path:
        sys.path.insert(0, bundled_apps_dir_str)
    if project_root_str not in sys.path:
        sys.path.insert(0, project_root_str)

    runtime_packages_env = os.getenv("SABISTART_RUNTIME_PACKAGES_DIR", "").strip()
    if runtime_packages_env:
        runtime_packages = Path(runtime_packages_env).resolve()
        runtime_packages_str = str(runtime_packages)
        if runtime_packages.exists() and runtime_packages_str not in sys.path:
            sys.path.insert(0, runtime_packages_str)

    return project_root
