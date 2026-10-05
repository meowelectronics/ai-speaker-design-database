"""Shared workspace paths for scripts launched from any current directory."""

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
CATALOG_DIR = DATA_DIR / "catalogs"
RESULTS_DIR = DATA_DIR / "results"
DRIVER_3D_DIR = ROOT / "cad" / "drivers3d"


def catalog_path(filename):
    return CATALOG_DIR / filename