"""Deterministic synthetic fixtures. No actual environmental observations."""
import csv
import math
import random
from datetime import date, timedelta
from pathlib import Path

FIELDS = ['station_id', 'parameter_code', 'observed_at', 'value', 'unit']


def write_csv(path, rows, fields=FIELDS):
    with Path(path).open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def generate(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    rng = random.Random(863567)
    rows = []
    for day in range(365):
        observed = date(2025, 1, 1) + timedelta(days=day)
        for station in range(1, 5):
            # Deterministic missing observations; expected cadence is daily.
            if (day + station * 11) % 23 == 0:
                continue
            wave = math.cos(2 * math.pi * day / 365)
            for parameter, value, unit in [
                ('TEMP', 18 + 7 * wave + station * .4 + rng.uniform(-1, 1), 'degC'),
                ('PH', 7.2 + station * .1 + rng.uniform(-.3, .3), 'pH'),
                ('EC', 350 + station * 95 + 80 * wave + rng.uniform(-20, 20), 'uS/cm'),
            ]:
                rows.append(dict(zip(FIELDS, [f'DEMO0{station}', parameter,
                    f'{observed.isoformat()}T09:00:00Z', f'{value:.3f}', unit])))
    clean_count = len(rows)
    rows += [dict(rows[i]) for i in range(5)]
    bad = [('station_id', 'UNKNOWN'), ('parameter_code', 'UNKNOWN'),
           ('observed_at', '2025-99-01'), ('value', 'NaN'), ('unit', 'wrong-unit'),
           ('value', ''), ('value', 'Infinity'), ('value', 'not-a-number')]
    for index, (field, value) in enumerate(bad):
        item = dict(rows[index + 10]); item[field] = value; rows.append(item)
    write_csv(directory / 'observations.csv', rows)
    correction = dict(rows[0]); correction['value'] = f"{float(correction['value']) + .5:.3f}"
    write_csv(directory / 'corrections.csv', [correction])
    failure_rows = [dict(rows[1]), dict(rows[2])]
    for row in failure_rows:
        row['value'] = f"{float(row['value']) + 1:.3f}"
    write_csv(directory / 'failure_fixture.csv', failure_rows)
    write_csv(directory / 'schema_drift.csv', [{'station_id': 'DEMO01', 'reading': '7'}],
              ['station_id', 'reading'])
    return {'unique_observations': clean_count, 'input_rows': len(rows),
            'deliberately_invalid_or_duplicate_rows': len(rows) - clean_count}
