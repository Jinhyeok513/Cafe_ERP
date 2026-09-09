"""Vercel Services entrypoint for the Cafe ERP FastAPI application."""

from __future__ import annotations

import sys
from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from cafe_stock_manage.api import app  # noqa: E402, F401
