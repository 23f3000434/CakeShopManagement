"""Vercel's Flask entrypoint; local development still uses backend/run.py."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))
# A deployment must never silently use the local SQLite database.
os.environ.setdefault("APP_ENV", "production")

from app import create_app

app = create_app()
