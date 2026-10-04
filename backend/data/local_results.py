"""Local fixture snapshots only. Not deployment/shared database storage."""
import os
from contextlib import contextmanager
import sqlite3
from pathlib import Path
from models.comparison import Comparison


@contextmanager
def connect():
    path = Path(os.getenv('BUYWISE_FIXTURE_DB', str(Path(__file__).resolve().parents[2] / '.local/fixture-results.sqlite3')))
    path.parent.mkdir(parents=True,exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute('CREATE TABLE IF NOT EXISTS comparisons (id TEXT PRIMARY KEY, request_id TEXT NOT NULL, body TEXT NOT NULL)')
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def save(comparison):
    with connect() as connection:
        connection.execute('INSERT OR REPLACE INTO comparisons VALUES (?,?,?)',(comparison.id,comparison.request_id,comparison.model_dump_json()))
        connection.execute('DELETE FROM comparisons WHERE rowid NOT IN (SELECT rowid FROM comparisons ORDER BY rowid DESC LIMIT 100)')


def load(identifier, by_request=False):
    with connect() as connection:
        row = connection.execute(f'SELECT body FROM comparisons WHERE {"request_id" if by_request else "id"}=? ORDER BY rowid DESC LIMIT 1',(identifier,)).fetchone()
    return Comparison.model_validate_json(row[0]) if row else None
