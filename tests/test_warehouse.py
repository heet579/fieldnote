import csv
import json
import os
import tempfile
import unittest
from pathlib import Path
from warehouse.db import Database, initialise
from warehouse.generate import generate, write_csv
from warehouse.pipeline import load
from warehouse.operations import backup_sqlite, restore_sqlite, fingerprint
from warehouse.report import export


class WarehouseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.previous = Path.cwd()
        os.chdir(self.temp.name)
        self.db = Database('test.sqlite')
        initialise(self.db)
        self.fixture = generate('input')

    def tearDown(self):
        self.db.close()
        os.chdir(self.previous)
        self.temp.cleanup()

    def initial(self):
        return load(self.db, 'input/observations.csv')

    def facts(self):
        return self.db.rows('SELECT * FROM fact_observation ORDER BY station_id,parameter_code,observed_at')

    def test_reconciliation_and_idempotence(self):
        first = self.initial()
        self.assertEqual(first['received'], self.fixture['input_rows'])
        self.assertEqual(first['rejected'], 13)
        self.assertEqual(first['inserted'], self.fixture['unique_observations'])
        self.assertEqual(first['received'], first['accepted'] + first['rejected'])
        self.assertEqual(first['accepted'], first['inserted'] + first['updated'] + first['unchanged'])
        before = self.facts()
        second = self.initial()
        self.assertEqual(second['inserted'], 0)
        self.assertEqual(second['updated'], 0)
        self.assertEqual(second['unchanged'], first['accepted'])
        self.assertEqual(before, self.facts())
        self.assertEqual(len(self.db.rows('SELECT * FROM stg_observation')), first['received'] * 2)

    def test_correction_changes_one_observation_and_preserves_lineage(self):
        self.initial()
        before = self.facts()
        result = load(self.db, 'input/corrections.csv')
        self.assertEqual(result['updated'], 1)
        changes = [(a,b) for a,b in zip(before,self.facts()) if a != b]
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0][1]['last_run_id'], result['run_id'])
        self.assertNotEqual(changes[0][0]['value'], changes[0][1]['value'])
        self.assertEqual(len(list(Path('runtime/raw').glob('*.csv'))), 2)

    def test_failure_rolls_back_facts_staging_and_quality_then_recovers(self):
        self.initial()
        before = self.facts()
        staged = len(self.db.rows('SELECT * FROM stg_observation'))
        with self.assertRaisesRegex(RuntimeError, 'Injected failure'):
            load(self.db, 'input/failure_fixture.csv', fail_after=1)
        self.assertEqual(before, self.facts())
        self.assertEqual(staged, len(self.db.rows('SELECT * FROM stg_observation')))
        failed = self.db.rows("SELECT * FROM etl_run WHERE status='failed'")[0]
        self.assertEqual(failed['received'], 0)
        self.assertIn('Injected failure', failed['error'])
        recovered = load(self.db, 'input/failure_fixture.csv')
        self.assertEqual(recovered['updated'], 2)

    def test_schema_drift_is_logged_before_any_fact_change(self):
        self.initial()
        before = self.facts()
        with self.assertRaisesRegex(ValueError, 'Schema drift'):
            load(self.db, 'input/schema_drift.csv')
        self.assertEqual(before, self.facts())
        self.assertEqual(len(self.db.rows("SELECT * FROM etl_run WHERE status='failed'")), 1)

    def test_timestamp_normalisation_duplicate_and_numeric_rules(self):
        rows = [dict(station_id='DEMO01',parameter_code='PH',observed_at='2025-01-01T09:00:00Z',value='7',unit='pH')]
        for timestamp,value in [('2025-01-01T19:30:00+10:30','7'),
                                ('2025-01-02T09:00:00','7'),
                                ('2025-01-02T09:00:00Z','15'),
                                ('2025-01-03T09:00:00Z','-Infinity')]:
            rows.append({**rows[0], 'observed_at': timestamp, 'value': value})
        write_csv('edge.csv', rows)
        result = load(self.db, 'edge.csv')
        self.assertEqual(result['inserted'], 1)
        self.assertEqual(result['rejected'], 4)
        reasons = {r['reason'] for r in self.db.rows('SELECT reason FROM data_quality_issue')}
        self.assertIn('duplicate_key_in_file', reasons)
        self.assertIn('invalid_timestamp_or_timezone', reasons)

    def test_backup_restores_every_table_and_refuses_overwrite_or_tampering(self):
        self.initial()
        backup_sqlite(self.db, 'backup.sqlite')
        restored = restore_sqlite('backup.sqlite', 'restored.sqlite')
        self.assertEqual(restored['status'], 'verified')
        copy = Database('restored.sqlite')
        try:
            self.assertEqual(fingerprint(self.db), fingerprint(copy))
        finally:
            copy.close()
        with self.assertRaisesRegex(ValueError, 'exists'):
            restore_sqlite('backup.sqlite', 'restored.sqlite')
        with Path('backup.sqlite').open('ab') as stream:
            stream.write(b'corruption')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            restore_sqlite('backup.sqlite', 'tampered.sqlite')

    def test_report_has_committed_data_and_safe_json(self):
        self.initial()
        self.db.execute('UPDATE dim_station SET station_name=? WHERE station_id=?', ('</script><script>alert(1)</script>', 'DEMO01'))
        self.db.commit()
        export(self.db, 'report.html')
        report = Path('report.html').read_text(encoding='utf-8')
        embedded = report.split('<script id="dataset" type="application/json">')[1].split('</script>')[0]
        payload = json.loads(embedded)
        self.assertEqual(len(payload['observations']), self.fixture['unique_observations'])
        self.assertNotIn('</script>', embedded)
        self.assertIn('SYNTHETIC DATA', report)

    def test_database_rejects_orphan_fact(self):
        with self.assertRaises(Exception):
            self.db.execute('INSERT INTO fact_observation VALUES (?,?,?,?,?,?)',
                            ('missing','PH','2025-01-01T09:00:00+00:00','2025-01-01',7,'missing'))
        self.db.rollback()

    def test_unspecified_source_clock_is_opt_in_and_preserved(self):
        row = dict(station_id='DEMO01', parameter_code='TEMP',
                   observed_at='2017-01-01T00:00:00', value='20', unit='degC')
        write_csv('clock.csv', [row])
        rejected = load(self.db, 'clock.csv')
        self.assertEqual(rejected['rejected'], 1)
        accepted = load(self.db, 'clock.csv', timestamp_basis='source_unspecified')
        self.assertEqual(accepted['inserted'], 1)
        fact = self.facts()[0]
        self.assertEqual(fact['observed_at'], '2017-01-01T00:00:00')
        self.assertEqual(fact['date_key'], '2017-01-01')

    def test_daily_export_retains_weights_and_extrema(self):
        rows = [dict(station_id='DEMO01', parameter_code='TEMP',
                     observed_at=timestamp, value=value, unit='degC')
                for timestamp, value in [('2017-01-01T00:00:00','10'),
                                         ('2017-01-01T00:15:00','20'),
                                         ('2017-01-02T00:00:00','30')]]
        write_csv('weighted.csv', rows)
        load(self.db, 'weighted.csv', timestamp_basis='source_unspecified')
        export(self.db, 'daily.html', metadata={'real': True}, daily=True)
        embedded = Path('daily.html').read_text(encoding='utf-8').split('<script id="dataset" type="application/json">')[1].split('</script>')[0]
        payload = json.loads(embedded)
        days = payload['observations']
        self.assertEqual(len(days), 2)
        self.assertEqual([r['sample_count'] for r in days], [2,1])
        self.assertEqual(days[0]['min_value'], 10)
        self.assertEqual(days[0]['max_value'], 20)
        self.assertEqual(sum(r['value']*r['sample_count'] for r in days)/3, 20)


if __name__ == '__main__':
    unittest.main()
