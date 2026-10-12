"""Resolve private artifacts for source checkouts and extracted releases."""
import os
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[2]
RELEASE = REPOSITORY.parent
DEFAULT_DATA = (RELEASE if (RELEASE / 'backend.env').is_file() else REPOSITORY) / 'data'
ROOT = Path(os.environ.get('POWERFUL_TS_DATA_DIR', DEFAULT_DATA)).resolve() / 'audio-lab'
