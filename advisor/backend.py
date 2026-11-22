"""API-only entry point for local development and frontend integration."""
import os
from pathlib import Path

from advisor import create_app


app = create_app(Path(os.environ.get('ADVISOR_DB', 'advisor-backend.sqlite3')), include_wallet=False)
