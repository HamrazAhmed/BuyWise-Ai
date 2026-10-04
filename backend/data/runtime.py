"""Durable runtime repository. DATABASE_URL fails closed; SQLite is local only."""
import json
import os
import sqlite3
import time
import threading
from contextlib import contextmanager
from pathlib import Path


def postgres():
    return bool(os.getenv('DATABASE_URL', '').strip())


_ready = set()
_migration_lock = threading.Lock()


def ensure():
    target = os.getenv('DATABASE_URL') or os.getenv('BUYWISE_DB') or os.getenv('BUYWISE_FIXTURE_DB') or 'local-runtime'
    with _migration_lock:
        if target not in _ready:
            migrate()
            _ready.add(target)


class Connection:
    def __init__(self, raw, pg):
        self.raw, self.pg = raw, pg

    def execute(self, sql, params=()):
        return self.raw.execute(sql.replace('?', '%s') if self.pg else sql, params)


@contextmanager
def connect(write=False):
    pg = postgres()
    if pg:
        import psycopg
        # Supabase transaction pooling cannot retain prepared statements.
        raw = psycopg.connect(os.environ['DATABASE_URL'], prepare_threshold=None, connect_timeout=5)
        raw.execute("SET statement_timeout = '10s'")
    else:
        path = Path(os.getenv('BUYWISE_DB', os.getenv('BUYWISE_FIXTURE_DB', str(Path(__file__).resolve().parents[2] / '.local/runtime.sqlite3'))))
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = sqlite3.connect(path, timeout=10)
        raw.execute('PRAGMA foreign_keys=ON')
        if write:
            raw.execute('BEGIN IMMEDIATE')
    try:
        with raw:
            yield Connection(raw, pg)
    finally:
        raw.close()


def migrate():
    sql = (Path(__file__).parent / 'migrations/001_runtime.sql').read_text()
    with connect(write=True) as db:
        if db.pg:
            db.execute('SELECT pg_advisory_xact_lock(824721)')
        for statement in sql.replace(' JSON ', ' JSONB ' if db.pg else ' TEXT ').split(';'):
            if statement.strip():
                db.execute(statement)
        if db.pg:
            db.execute('CREATE EXTENSION IF NOT EXISTS vector')
            db.execute('ALTER TABLE bw_chunks ADD COLUMN IF NOT EXISTS embedding vector(768)')
            # Server DB role owns these tables; browser anon/authenticated roles get no policy.
            for table in ('bw_migrations', 'bw_requests', 'bw_comparisons', 'bw_jobs', 'bw_events', 'bw_chunks', 'bw_limits'):
                db.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')


def decode(body):
    return json.loads(body) if isinstance(body, str) else body


def save_request(result):
    ensure()
    with connect(write=True) as db:
        db.execute('INSERT INTO bw_requests(id,body,saved_at) VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body,saved_at=excluded.saved_at', (result.request_id, result.model_dump_json(), time.time()))
        db.execute('DELETE FROM bw_requests WHERE id NOT IN (SELECT id FROM bw_requests ORDER BY saved_at DESC,id DESC LIMIT 100)')


def save_comparison(comparison, db=None):
    if db is None:
        with connect(write=True) as connection:
            save_comparison(comparison, connection)
        return
    db.execute('INSERT INTO bw_comparisons(id,request_id,body,saved_at) VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body,saved_at=excluded.saved_at',
               (comparison.id, comparison.request_id, comparison.model_dump_json(), time.time()))
    db.execute('DELETE FROM bw_comparisons WHERE id NOT IN (SELECT id FROM bw_comparisons ORDER BY saved_at DESC,id DESC LIMIT 100)')


def load_comparison(identifier, by_request=False):
    from models.comparison import Comparison
    with connect() as db:
        row = db.execute(f'SELECT body FROM bw_comparisons WHERE {"request_id" if by_request else "id"}=? ORDER BY saved_at DESC,id DESC LIMIT 1', (identifier,)).fetchone()
    return Comparison.model_validate(decode(row[0])) if row else None


def cleanup(db):
    now = time.time()
    db.execute("DELETE FROM bw_jobs WHERE status IN ('done','error') AND updated_at<?", (now - 86400,))
    db.execute('DELETE FROM bw_chunks WHERE saved_at<?', (now - 30*86400,))
    db.execute('DELETE FROM bw_limits WHERE expires<?', (now,))


def reserve(bucket, limit, expires):
    """Atomic shared counter; all API/worker instances use the same database."""
    with connect(write=True) as db:
        db.execute('DELETE FROM bw_limits WHERE expires<?', (time.time(),))
        row = db.execute('INSERT INTO bw_limits(bucket,count,expires) VALUES (?,1,?) ON CONFLICT(bucket) DO UPDATE SET count=bw_limits.count+1 WHERE bw_limits.count<? RETURNING count', (bucket, expires, limit)).fetchone()
    return row is not None


if __name__ == '__main__':
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[2] / '.env', override=False)
    migrate()
    print('Runtime migration 1 applied (' + ('PostgreSQL/pgvector' if postgres() else 'local SQLite') + ').')
