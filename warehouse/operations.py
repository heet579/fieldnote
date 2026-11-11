"""SQLite backup/restore and cross-backend logical reconciliation."""
import hashlib
import json
import sqlite3
from pathlib import Path

TABLES = ['dim_station', 'dim_parameter', 'dim_date', 'etl_run',
          'stg_observation', 'data_quality_issue', 'fact_observation']


def fingerprint(db):
    result = {}
    for table in TABLES:
        rows = db.rows(f'SELECT * FROM {table}')
        encoded = sorted(json.dumps(r, sort_keys=True, allow_nan=False) for r in rows)
        result[table] = {'rows': len(rows), 'sha256': hashlib.sha256('\n'.join(encoded).encode()).hexdigest()}
    return result


def backup_sqlite(db, destination):
    if db.postgres:
        raise ValueError('Use pg_dump for PostgreSQL; see docs/runbook.md')
    path = Path(destination)
    if path.exists():
        raise ValueError('Backup destination exists; use a new filename')
    path.parent.mkdir(parents=True, exist_ok=True)
    target = sqlite3.connect(path)
    try:
        db.connection.backup(target)
        check = target.execute('PRAGMA integrity_check').fetchone()[0]
        if check != 'ok':
            raise RuntimeError(f'Backup integrity check failed: {check}')
    finally:
        target.close()
    from .db import Database
    snapshot = Database(path)
    try:
        tables = fingerprint(snapshot)
    finally:
        snapshot.close()
    manifest = {'database_sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'tables': tables}
    path.with_suffix(path.suffix + '.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return manifest


def restore_sqlite(source, destination):
    source, destination = Path(source), Path(destination)
    if destination.exists():
        raise ValueError('Restore target already exists; restore into a new database')
    manifest = json.loads(source.with_suffix(source.suffix + '.json').read_text(encoding='utf-8'))
    if hashlib.sha256(source.read_bytes()).hexdigest() != manifest['database_sha256']:
        raise ValueError('Backup checksum mismatch')
    from .db import Database
    original = sqlite3.connect(f'{source.resolve().as_uri()}?mode=ro', uri=True)
    destination.parent.mkdir(parents=True, exist_ok=True)
    restored = Database(destination)
    try:
        original.backup(restored.connection)
        if restored.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Restored database integrity check failed')
        if restored.rows('PRAGMA foreign_key_check'):
            raise ValueError('Restored foreign key check failed')
        actual = fingerprint(restored)
        if actual != manifest['tables']:
            raise ValueError('Restored logical table checksums differ')
        return {'status': 'verified', 'tables': actual}
    finally:
        original.close(); restored.close()
