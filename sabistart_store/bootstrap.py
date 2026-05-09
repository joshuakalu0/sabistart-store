from __future__ import annotations

import sys
from pathlib import Path


RUNTIME_PACKAGES_DIRNAME = "runtime_packages"


def bootstrap_paths(base_dir: str | Path) -> Path:
    """
    Prepend project and runtime-vendored package paths to sys.path.

    Vercel can install Python dependencies using a different interpreter than
    the one that later executes build commands or the deployed function. To keep
    compiled dependencies consistent, the build script vendors packages into a
    project-local directory using the actual runtime Python. This helper makes
    sure those vendored packages win import precedence everywhere.
    """

    project_root = Path(base_dir).resolve()
    runtime_packages = project_root / RUNTIME_PACKAGES_DIRNAME

    project_root_str = str(project_root)
    runtime_packages_str = str(runtime_packages)

    if project_root_str not in sys.path:
        sys.path.insert(0, project_root_str)
    if runtime_packages.exists() and runtime_packages_str not in sys.path:
        sys.path.insert(0, runtime_packages_str)

    return project_root
