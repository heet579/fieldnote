"""Reconcile accepted facts against raw ZIP members, not the report aggregates."""
import csv
import io
import json
import math
import sqlite3
import zipfile
from collections import Counter
from pathlib import Path


def verify():
    connection = sqlite3.connect('runtime/real-v2/warehouse.sqlite')
    connection.row_factory = sqlite3.Row
    facts = {(r['station_id'],r['parameter_code'],r['observed_at']):r['value']
             for r in connection.execute('SELECT * FROM fact_observation')}
    seen = set(); invalid = 0; members = 0
    with zipfile.ZipFile('data/real/TorrensWaterData.zip') as archive:
        for name in archive.namelist():
            if not (name.startswith('torrens/A') and any(name.endswith(f'_{year}.csv') for year in (2015,2016,2017,2018))):
                continue
            members += 1
            records = [r for r in csv.reader(io.StringIO(archive.read(name).decode('cp1252'))) if r]
            header = records[1]
            station = name.split('/')[-1][:8]
            for row in records[4:]:
                if not row or not row[0]:
                    continue
                for field, code in [('WTemp','TEMP'),('E_Cond','EC'),('O2_mg','DO')]:
                    text = row[header.index(field)]
                    try:
                        value = float(text)
                        assert math.isfinite(value)
                    except (ValueError, AssertionError):
                        invalid += 1; continue
                    key = (station, code, row[0].replace(' ', 'T'))
                    assert key not in seen, f'Duplicate raw key: {key}'
                    assert facts[key] == value, f'Source value mismatch: {key}'
                    seen.add(key)
    assert set(facts) == seen
    assert len(facts) == 1012742 and invalid == 31 and members == 120
    assert connection.execute('PRAGMA foreign_key_check').fetchall() == []
    monthly = [dict(r) for r in connection.execute('''SELECT station_id,parameter_code,
       substr(date_key,1,7) AS month,COUNT(*) AS n,AVG(value) AS mean,
       MIN(value) AS min,MAX(value) AS max FROM fact_observation
       GROUP BY station_id,parameter_code,substr(date_key,1,7)
       ORDER BY station_id,parameter_code,month''')]
    Path('portfolio/monthly-reference.json').write_text(json.dumps(monthly, indent=2), encoding='utf-8')
    result = {'raw_archive_members_checked': members, 'source_values_matched': len(seen),
              'invalid_values_excluded': invalid, 'orphan_facts': 0,
              'monthly_reference': 'monthly-reference.json', 'method': 'Exact comparison of every accepted fact key and value against the selected raw ZIP members; independent SQL aggregation for frontend checks.'}
    Path('portfolio/real-verification.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))
    connection.close()


if __name__ == '__main__':
    verify()
