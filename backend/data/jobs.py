"""Leased research jobs with fenced writes and replayable, bounded events."""
import json
import time
import uuid
from . import runtime

LEASE_SECONDS = 30
MAX_ATTEMPTS = 2


def submit(identifier, body):
    runtime.ensure()
    now = time.time()
    with runtime.connect(write=True) as db:
        runtime.cleanup(db)
        # Lock the admission check across API instances, including PostgreSQL.
        if db.pg:
            db.execute('SELECT pg_advisory_xact_lock(824722)')
        expired = db.execute("SELECT id FROM bw_jobs WHERE created_at<? AND (status='queued' OR (status='running' AND lease_until<?))" + (' FOR UPDATE SKIP LOCKED' if db.pg else ''), (now - 3600, now)).fetchall()
        for (old_id,) in expired:
            db.execute("UPDATE bw_jobs SET status='error',owner=NULL,updated_at=? WHERE id=?", (now, old_id))
            _event(db, old_id, {'type': 'error', 'code': 'QUEUE_EXPIRED', 'message': 'Queued research expired; please submit a new run.'})
        if db.execute("SELECT count(*) FROM bw_jobs WHERE status IN ('queued','running')").fetchone()[0] >= 100:
            raise ValueError('Research queue is full; retry later.')
        db.execute("INSERT INTO bw_jobs(id,body,status,created_at,updated_at) VALUES (?,?,'queued',?,?)", (identifier, json.dumps(body), now, now))
        _event(db, identifier, {'type': 'status', 'step': 'queued', 'message': 'Research queued'})


def _event(db, identifier, event):
    seq = db.execute('SELECT COALESCE(MAX(seq),0)+1 FROM bw_events WHERE job_id=?', (identifier,)).fetchone()[0]
    if seq > 100:
        raise ValueError('Research event limit exceeded')
    db.execute('INSERT INTO bw_events(job_id,seq,body) VALUES (?,?,?)', (identifier, seq, json.dumps(event)))


def claim():
    runtime.ensure()
    now = time.time()
    with runtime.connect(write=True) as db:
        suffix = ' FOR UPDATE SKIP LOCKED' if db.pg else ''
        rows = db.execute("SELECT id,body,attempts FROM bw_jobs WHERE status='queued' OR (status='running' AND lease_until<?) ORDER BY created_at LIMIT 1" + suffix, (now,)).fetchone()
        if not rows:
            return None
        identifier, body, attempts = rows
        created = db.execute('SELECT created_at FROM bw_jobs WHERE id=?', (identifier,)).fetchone()[0]
        if created < now - 3600:
            db.execute("UPDATE bw_jobs SET status='error',owner=NULL,updated_at=? WHERE id=?", (now, identifier))
            _event(db, identifier, {'type': 'error', 'code': 'QUEUE_EXPIRED', 'message': 'Queued research expired; please submit a new run.'})
            return None
        if attempts >= MAX_ATTEMPTS:
            db.execute("UPDATE bw_jobs SET status='error',owner=NULL,updated_at=? WHERE id=?", (now, identifier))
            _event(db, identifier, {'type': 'error', 'code': 'WORKER_INTERRUPTED', 'message': 'Research was interrupted repeatedly; please retry.'})
            return None
        owner = str(uuid.uuid4())
        db.execute("UPDATE bw_jobs SET status='running',owner=?,lease_until=?,attempts=attempts+1,updated_at=? WHERE id=?", (owner, now + LEASE_SECONDS, now, identifier))
        _event(db, identifier, {'type': 'status', 'step': 'starting', 'message': 'Research started' if attempts == 0 else 'Resuming interrupted research'})
        return identifier, runtime.decode(body), owner


def _owned(db, identifier, owner):
    suffix = ' FOR UPDATE' if db.pg else ''
    row = db.execute('SELECT status,owner,lease_until FROM bw_jobs WHERE id=?' + suffix, (identifier,)).fetchone()
    if not row or row[0] != 'running' or row[1] != owner or row[2] <= time.time():
        raise RuntimeError('Research worker lease lost')


def heartbeat(identifier, owner):
    with runtime.connect(write=True) as db:
        _owned(db, identifier, owner)
        db.execute('UPDATE bw_jobs SET lease_until=?,updated_at=? WHERE id=?', (time.time() + LEASE_SECONDS, time.time(), identifier))


def progress(identifier, owner, event):
    with runtime.connect(write=True) as db:
        _owned(db, identifier, owner)
        if db.execute('SELECT count(*) FROM bw_events WHERE job_id=?', (identifier,)).fetchone()[0] >= 90:
            return  # Reserve terminal/recovery event capacity.
        _event(db, identifier, event)


def finish(identifier, owner, comparison=None, error=None):
    with runtime.connect(write=True) as db:
        _owned(db, identifier, owner)
        if comparison is not None:
            if comparison.id != identifier:
                raise ValueError('Result identity differs from job')
            runtime.save_comparison(comparison, db)
        event = error or {'type': 'done', 'comparison_id': identifier}
        _event(db, identifier, event)
        db.execute('UPDATE bw_jobs SET status=?,owner=NULL,lease_until=0,updated_at=? WHERE id=?', ('error' if error else 'done', time.time(), identifier))


def status(identifier):
    runtime.ensure()
    with runtime.connect() as db:
        row = db.execute('SELECT status,attempts,updated_at FROM bw_jobs WHERE id=?', (identifier,)).fetchone()
    return {'comparison_id': identifier, 'status': row[0], 'attempts': row[1], 'updated_at': row[2]} if row else None


def events(identifier, after=0):
    with runtime.connect() as db:
        rows = db.execute('SELECT seq,body FROM bw_events WHERE job_id=? AND seq>? ORDER BY seq', (identifier, after)).fetchall()
    return [(seq, runtime.decode(body)) for seq, body in rows]
