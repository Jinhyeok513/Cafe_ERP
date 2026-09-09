"""Vercel Services entrypoint for the Cafe ERP FastAPI application."""

from __future__ import annotations

import sys
from pathlib import Path


ENTRYPOINT_DIR = Path(__file__).resolve().parent
SOURCE_ROOT = next(
    path
    for path in (ENTRYPOINT_DIR / "src", ENTRYPOINT_DIR.parent / "src")
    if path.is_dir()
)
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from cafe_stock_manage.api import app  # noqa: E402, F401
