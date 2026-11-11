"""Run the full SQLite portfolio scenario and write an evidence receipt."""
import json
from pathlib import Path
from warehouse.db import Database, initialise
from warehouse.generate import generate
from warehouse.pipeline import load
from warehouse.operations import backup_sqlite, restore_sqlite, fingerprint
from warehouse.report import export


def main():
    # Refuse to overwrite previous evidence or databases.
    directory = Path('runtime/demo')
    if directory.exists():
        raise SystemExit('runtime/demo already exists. Archive it or use the individual CLI commands; no data was overwritten.')
    directory.mkdir(parents=True)
    receipt = {'source': 'Synthetic fixtures only; no actual environmental observations',
               'fixtures': generate('data/synthetic')}
    db = Database(directory / 'warehouse.sqlite')
    try:
        initialise(db)
        receipt['initial_load'] = load(db, 'data/synthetic/observations.csv')
        receipt['repeated_load'] = load(db, 'data/synthetic/observations.csv')
        receipt['correction'] = load(db, 'data/synthetic/corrections.csv')
        before = db.rows('SELECT * FROM fact_observation ORDER BY station_id,parameter_code,observed_at')
        try:
            load(db, 'data/synthetic/failure_fixture.csv', fail_after=1)
            raise AssertionError('Expected failure did not happen')
        except RuntimeError:
            after = db.rows('SELECT * FROM fact_observation ORDER BY station_id,parameter_code,observed_at')
            assert before == after
            receipt['injected_failure'] = {'status': 'failed as intended', 'facts_unchanged': True}
        receipt['recovery'] = load(db, 'data/synthetic/failure_fixture.csv')
        try:
            load(db, 'data/synthetic/schema_drift.csv')
            raise AssertionError('Expected schema failure did not happen')
        except ValueError:
            receipt['schema_drift'] = 'rejected and logged'
        receipt['backup'] = backup_sqlite(db, directory / 'backup.sqlite')
        receipt['restore'] = restore_sqlite(directory / 'backup.sqlite', directory / 'restored.sqlite')
        copy = Database(directory / 'restored.sqlite')
        try:
            assert fingerprint(copy) == fingerprint(db)
            receipt['restore_matches_live_database'] = True
        finally:
            copy.close()
        receipt['report'] = export(db, 'portfolio/synthetic-dashboard.html')
        Path('portfolio/evidence.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
        print(json.dumps(receipt, indent=2))
    finally:
        db.close()


if __name__ == '__main__':
    main()
