"""Inspect the selected full calendar year's raw fields without modifying data."""
import csv
import io
import json
import math
import zipfile
from collections import Counter, defaultdict


def rows_for(archive, name):
    # Source files use CP1252 and sometimes doubled CR delimiters.
    rows = [r for r in csv.reader(io.StringIO(archive.read(name).decode('cp1252'))) if r]
    return rows[0], rows[1], rows[2], rows[4:]


def main():
    stats = defaultdict(Counter)
    values = defaultdict(list)
    timestamps = defaultdict(list)
    with zipfile.ZipFile('data/real/TorrensWaterData.zip') as archive:
        names = [n for n in archive.namelist() if n.startswith('torrens/A')
                 and any(n.endswith(f'_{year}.csv') for year in (2015,2016,2017,2018))]
        for name in names:
            friendly, header, units, rows = rows_for(archive, name)
            station = name.split('/')[-1][:8]
            fields = {field: header.index(field) for field in ['WTemp', 'E_Cond', 'O2_mg']}
            for row in rows:
                if not row or not row[0]:
                    continue
                timestamps[station].append(row[0])
                for field, i in fields.items():
                    key = station + '/' + field
                    stats[key]['rows'] += 1
                    try:
                        value = float(row[i])
                        stats[key]['zero'] += int(value == 0)
                        stats[key]['negative'] += int(value < 0)
                        if not math.isfinite(value):
                            stats[key]['nonfinite'] += 1
                        else:
                            values[key].append(value)
                    except (ValueError, IndexError):
                        stats[key]['missing_or_invalid'] += 1
        result = {'files': len(names), 'fields': {
            k: {**v, 'min': min(values[k]) if values[k] else None,
                'max': max(values[k]) if values[k] else None} for k, v in stats.items()},
            'stations': {k: {'first': min(v), 'last': max(v), 'records': len(v),
                             'unique_timestamps': len(set(v))} for k, v in timestamps.items()}}
        print(json.dumps(result, indent=2))
        return result


if __name__ == '__main__':
    main()
