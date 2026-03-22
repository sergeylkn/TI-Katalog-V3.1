"""Compatibility module providing previous import path `database.db`.

This forwards to `core.database` to avoid ModuleNotFoundError in environments
which run `python -m uvicorn main:app` where main.py still imports
`from database.db import init_db`.
"""
from core.database import engine, AsyncSessionLocal, get_db, init_db

__all__ = ["engine", "AsyncSessionLocal", "get_db", "init_db"]
