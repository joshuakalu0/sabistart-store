import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from sabistart_store.bootstrap import bootstrap_paths
from sabistart_store.env import ensure_project_root_on_path, load_environment


def _candidate_python_paths(base_dir: Path):
    return [
        base_dir / "venv" / "Scripts" / "python.exe",
        base_dir / ".venv" / "Scripts" / "python.exe",
        base_dir / "venv" / "bin" / "python",
        base_dir / ".venv" / "bin" / "python",
        Path.home() / "virtualenv" / base_dir.name / "3.14" / "bin" / "python",
        Path.home() / "virtualenv" / base_dir.name / "3.13" / "bin" / "python",
        Path.home() / "virtualenv" / base_dir.name / "3.12" / "bin" / "python",
        Path.home() / "virtualenv" / base_dir.name / "3.11" / "bin" / "python",
        Path.home() / "virtualenv" / base_dir.name / "3.10" / "bin" / "python",
    ]


for candidate in _candidate_python_paths(BASE_DIR):
    if candidate.exists():
        os.environ.setdefault("PYTHONHOME", str(candidate.parent.parent))
        break

bootstrap_paths(BASE_DIR)
ensure_project_root_on_path()
load_environment()
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sabistart_store.settings")

from sabistart_store.wsgi import application  # noqa: E402
