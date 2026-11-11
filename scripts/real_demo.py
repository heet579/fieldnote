"""Import genuine Torrens readings and build a provenance-backed public report.

The reliability exercises use the same original values. No measurements are
modified or fabricated. Synthetic correction scenarios stay in their own DB.
"""
import argparse
import csv
import hashlib
import json
import zipfile
from pathlib import Path
from warehouse.db import Database, initialise
from warehouse.generate import FIELDS
from warehouse.pipeline import load
from warehouse.operations import backup_sqlite, restore_sqlite, fingerprint
from warehouse.report import export
from .profile_torrens import rows_for, main as profile

STATIONS = [('A5041054', 'Adelaide Zoo footbridge', 'Torrens Lake · Adelaide'),
            ('A5041055', 'Adelaide University footbridge', 'Torrens Lake · Adelaide'),
            ('A5041056', 'Torrens Weir', 'Torrens Lake · Adelaide')]
PARAMETERS = [('TEMP', 'Water temperature', 'degC'),
              ('EC', 'Electrical conductivity (in situ)', 'uS/cm'),
              ('DO', 'Dissolved oxygen', 'mg/L')]
MAPPING = {'WTemp': ('TEMP', 'degC', {'C', '°C'}),
           'E_Cond': ('EC', 'uS/cm', {'uS/cm'}),
           'O2_mg': ('DO', 'mg/L', {'mg/L'})}


def normalise(years=(2015, 2016, 2017, 2018)):
    source = json.loads(Path('data/real/source.json').read_text(encoding='utf-8'))
    archive_path = Path('data/real/TorrensWaterData.zip')
    if hashlib.sha256(archive_path.read_bytes()).hexdigest() != source['sha256']:
        raise ValueError('Source archive checksum does not match download receipt')
    destination = Path('data/real/observations.csv')
    members = []
    count = 0
    with zipfile.ZipFile(archive_path) as archive, destination.open('w', encoding='utf-8', newline='') as output:
        writer = csv.DictWriter(output, fieldnames=FIELDS)
        writer.writeheader()
        names = sorted(n for n in archive.namelist() if n.startswith('torrens/A')
                       and any(n.endswith(f'_{year}.csv') for year in years))
        expected_files = {2015: 21, 2016: 36, 2017: 36, 2018: 27}
        if len(names) != sum(expected_files[year] for year in years):
            raise ValueError('Unexpected monthly archive selection; review source changes')
        for name in names:
            friendly, header, units, rows = rows_for(archive, name)
            station = name.split('/')[-1][:8]
            if station not in {s[0] for s in STATIONS} or station not in friendly[0]:
                raise ValueError(f'Station metadata mismatch: {name}')
            positions = {}
            for field, (_, _, accepted_units) in MAPPING.items():
                if header.count(field) != 1:
                    raise ValueError(f'Unexpected field contract: {name}/{field}')
                index = header.index(field)
                if units[index] not in accepted_units:
                    raise ValueError(f'Unexpected measurement unit: {name}/{field}/{units[index]}')
                positions[field] = index
            member_count = 0
            for row in rows:
                if not row or not row[0]:
                    continue
                if len(row) != len(header):
                    raise ValueError(f'Malformed source row in {name}')
                if not any(row[0].startswith(f'{year}-') for year in years):
                    raise ValueError(f'Unexpected year in {name}')
                for field, index in positions.items():
                    parameter, unit, _ = MAPPING[field]
                    # Keep unparseable readings for the loader's quarantine, not zero-fill.
                    writer.writerow(dict(zip(FIELDS, [station, parameter,
                        row[0].replace(' ', 'T'), row[index], unit])))
                    count += 1; member_count += 1
            members.append({'member': name, 'normalised_rows': member_count,
                            'sha256': hashlib.sha256(archive.read(name)).hexdigest()})
    source.update(real=True, default_year='all', years=list(years), station_count=3,
                  source_timestamp_basis='Unspecified source clock; no UTC offset inferred',
                  selected_parameters=['WTemp', 'E_Cond', 'O2_mg'],
                  transformation=f'Selected {len(members)} non-overlapping monthly files for {min(years)}–{max(years)} under torrens/. Unpivoted three fields. No interpolation, unit conversion or timezone inference. Daily aggregates retain sample weights and extrema.',
                  normalised_rows=count, members=members)
    Path('data/real/manifest.json').write_text(json.dumps(source, indent=2), encoding='utf-8')
    return destination, source


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-dir', default='runtime/real-v2')
    args = parser.parse_args()
    run_dir = Path(args.run_dir)
    if run_dir.exists():
        raise SystemExit('Run directory exists; select a new --run-dir to preserve previous evidence.')
    run_dir.mkdir(parents=True)
    csv_path, metadata = normalise()
    raw_profile = profile()
    Path('data/real/profile.json').write_text(json.dumps(raw_profile, indent=2), encoding='utf-8')
    db = Database(run_dir / 'warehouse.sqlite')
    receipt = {'source': metadata, 'profile': raw_profile}
    try:
        initialise(db)
        # New, isolated real-data DB: remove only seeded demonstration reference rows.
        db.execute('DELETE FROM dim_station'); db.execute('DELETE FROM dim_parameter')
        for row in STATIONS:
            db.execute('INSERT INTO dim_station VALUES (?,?,?)', row)
        for row in PARAMETERS:
            db.execute('INSERT INTO dim_parameter VALUES (?,?,?)', row)
        db.commit()
        receipt['initial_load'] = load(db, csv_path, timestamp_basis='source_unspecified')
        receipt['repeated_load'] = load(db, csv_path, timestamp_basis='source_unspecified')
        before = fingerprint(db)['fact_observation']
        # Small, genuine slice for an explicitly labelled failure/recovery exercise.
        with csv_path.open(newline='', encoding='utf-8') as stream:
            sample = [next(csv.DictReader(stream))]
        fixture = run_dir / 'real-retry-sample.csv'
        with fixture.open('w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELDS); writer.writeheader(); writer.writerows(sample)
        try:
            load(db, fixture, fail_after=1, timestamp_basis='source_unspecified')
            raise AssertionError('Expected injected failure')
        except RuntimeError:
            assert fingerprint(db)['fact_observation'] == before
            receipt['rollback'] = {'injected_failure': True, 'facts_unchanged': True,
                                   'measurement_values_modified': False}
        receipt['recovery'] = load(db, fixture, timestamp_basis='source_unspecified')
        receipt['backup'] = backup_sqlite(db, run_dir / 'backup.sqlite')
        receipt['restore'] = restore_sqlite(run_dir / 'backup.sqlite', run_dir / 'restored.sqlite')
        restored = Database(run_dir / 'restored.sqlite')
        try:
            assert fingerprint(restored) == fingerprint(db)
            receipt['restore_matches_live_database'] = True
        finally:
            restored.close()
        receipt['accepted_profile'] = db.rows('''SELECT station_id,parameter_code,COUNT(*) AS samples,
            MIN(observed_at) AS first_timestamp,MAX(observed_at) AS last_timestamp,
            COUNT(DISTINCT date_key) AS observed_days,AVG(value) AS mean_value,
            MIN(value) AS min_value,MAX(value) AS max_value FROM fact_observation
            GROUP BY station_id,parameter_code ORDER BY station_id,parameter_code''')
        receipt['report'] = export(db, 'portfolio/dashboard.html', metadata=metadata, daily=True)
        Path('portfolio/real-evidence.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
        print(json.dumps({k:v for k,v in receipt.items() if k in ['initial_load','repeated_load','rollback','recovery','report']}, indent=2))
    finally:
        db.close()


if __name__ == '__main__':
    main()
