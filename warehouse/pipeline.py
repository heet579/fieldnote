"""Auditable, transactional snapshot ingestion with explicit corrections."""
import csv
import hashlib
import io
import json
import math
import uuid
from datetime import datetime, timezone
from pathlib import Path
from .generate import FIELDS


def now():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds')


def load(db, source, fail_after=None, timestamp_basis='utc'):
    if timestamp_basis not in ('utc', 'source_unspecified'):
        raise ValueError('Unsupported timestamp basis')
    # Read once: bytes hashed, archived and parsed are identical.
    content = Path(source).read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    archive = Path('runtime/raw') / f'{digest}.csv'
    archive.parent.mkdir(parents=True, exist_ok=True)
    if archive.exists() and archive.read_bytes() != content:
        raise RuntimeError('Raw archive hash collision or corruption')
    archive.write_bytes(content)
    run = str(uuid.uuid4())
    counts = dict(received=0, accepted=0, rejected=0, inserted=0, updated=0, unchanged=0)
    db.execute('INSERT INTO etl_run(run_id,started_at,status,source_file,source_sha256) VALUES (?,?,?,?,?)',
               (run, now(), 'running', Path(source).name, digest))
    db.commit()  # Run identity survives a rolled-back load.
    try:
        # Serialise writers to preserve count accuracy and prevent concurrent corrections.
        if db.postgres:
            db.execute('LOCK TABLE fact_observation IN SHARE ROW EXCLUSIVE MODE')
        else:
            db.execute('BEGIN IMMEDIATE')
        reader = csv.DictReader(io.StringIO(content.decode('utf-8-sig'), newline=''))
        if reader.fieldnames != FIELDS:
            raise ValueError(f'Schema drift: expected columns {FIELDS}; received {reader.fieldnames}')
        stations = {r['station_id'] for r in db.rows('SELECT station_id FROM dim_station')}
        parameters = {r['parameter_code']: r['canonical_unit'] for r in db.rows('SELECT * FROM dim_parameter')}
        seen = set()
        for number, row in enumerate(reader, start=2):
            counts['received'] += 1
            raw = json.dumps(row, sort_keys=True)
            db.execute('INSERT INTO stg_observation VALUES (?,?,?)', (run, number, raw))
            reason = None
            key = None
            try:
                if None in row or any(v is None for v in row.values()):
                    raise ValueError('malformed_csv_row')
                if row['station_id'] not in stations:
                    raise ValueError('unknown_station')
                if row['parameter_code'] not in parameters:
                    raise ValueError('unknown_parameter')
                if row['unit'] != parameters[row['parameter_code']]:
                    raise ValueError('unexpected_unit')
                try:
                    timestamp = datetime.fromisoformat(row['observed_at'].replace('Z', '+00:00'))
                    if timestamp_basis == 'source_unspecified':
                        # Opt-in for a separately documented source database. Do not
                        # fabricate offsets for timestamps whose timezone is unknown.
                        if timestamp.tzinfo is not None:
                            raise ValueError()
                    else:
                        if timestamp.tzinfo is None:
                            raise ValueError()
                        timestamp = timestamp.astimezone(timezone.utc)
                    if timestamp.microsecond:
                        raise ValueError()
                except ValueError:
                    raise ValueError('invalid_timestamp_or_timezone') from None
                try:
                    value = float(row['value'])
                    if not math.isfinite(value):
                        raise ValueError()
                except ValueError:
                    raise ValueError('invalid_numeric_value') from None
                # Physical plausibility only; these are NOT water safety standards.
                if row['parameter_code'] == 'PH' and not 0 <= value <= 14:
                    raise ValueError('ph_outside_physical_range')
                if row['parameter_code'] == 'EC' and value < 0:
                    raise ValueError('negative_conductivity')
                if row['parameter_code'] == 'DO' and value < 0:
                    raise ValueError('negative_dissolved_oxygen')
                observed = timestamp.isoformat(timespec='seconds')
                key = (row['station_id'], row['parameter_code'], observed)
                if key in seen:
                    raise ValueError('duplicate_key_in_file')
            except ValueError as exc:
                reason = str(exc)
            if reason:
                counts['rejected'] += 1
                db.execute('INSERT INTO data_quality_issue VALUES (?,?,?,?)', (run, number, reason, raw))
                continue
            seen.add(key)
            counts['accepted'] += 1
            day = timestamp.date()
            season = ['Summer', 'Summer', 'Autumn', 'Autumn', 'Autumn', 'Winter',
                      'Winter', 'Winter', 'Spring', 'Spring', 'Spring', 'Summer'][day.month - 1]
            db.execute('INSERT INTO dim_date VALUES (?,?,?,?,?) ON CONFLICT(date_key) DO NOTHING',
                       (day.isoformat(), day.year, day.month, (day.month - 1) // 3 + 1, season))
            previous = db.rows('SELECT value FROM fact_observation WHERE station_id=? AND parameter_code=? AND observed_at=?', key)
            if not previous:
                db.execute('INSERT INTO fact_observation VALUES (?,?,?,?,?,?)',
                           (*key, day.isoformat(), value, run))
                counts['inserted'] += 1
            elif previous[0]['value'] != value:
                db.execute('UPDATE fact_observation SET value=?,last_run_id=? WHERE station_id=? AND parameter_code=? AND observed_at=?',
                           (value, run, *key))
                counts['updated'] += 1
            else:
                counts['unchanged'] += 1
            if fail_after is not None and counts['accepted'] >= fail_after:
                raise RuntimeError('Injected failure after accepted row; testing transaction rollback')
        assert counts['received'] == counts['accepted'] + counts['rejected']
        assert counts['accepted'] == counts['inserted'] + counts['updated'] + counts['unchanged']
        db.execute('UPDATE etl_run SET finished_at=?,status=?,received=?,accepted=?,rejected=?,inserted=?,updated=?,unchanged=? WHERE run_id=?',
                   (now(), 'succeeded', *counts.values(), run))
        db.commit()
        return {'run_id': run, 'status': 'succeeded', **counts}
    except Exception as exc:
        db.rollback()
        # Failed runs have zero committed counts; attempted work was rolled back.
        # Do not persist exception text: driver errors can contain connection secrets.
        message = str(exc) if isinstance(exc, (ValueError, RuntimeError)) else type(exc).__name__
        db.execute('UPDATE etl_run SET finished_at=?,status=?,error=? WHERE run_id=?',
                   (now(), 'failed', message, run))
        db.commit()
        raise
