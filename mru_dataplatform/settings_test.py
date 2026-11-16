"""Settings for the test suite: SQLite, debug key, no external services."""
import os

os.environ["DEBUG"] = "True"
os.environ.pop("DB_NAME", None)
os.environ.setdefault("SQLITE_PATH", ":memory:")

from .settings import *  # noqa: E402,F401,F403
