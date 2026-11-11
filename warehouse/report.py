"""Generate a portable, offline HTML report from committed warehouse data."""
import json
from pathlib import Path
from .pipeline import now


def export(db, destination, metadata=None, daily=False):
    if daily:
        observations = db.rows('''SELECT f.station_id,f.parameter_code,f.date_key,
            AVG(f.value) AS value, COUNT(*) AS sample_count, MIN(f.value) AS min_value,
            MAX(f.value) AS max_value,s.station_name,s.region,p.parameter_name,p.canonical_unit
            FROM fact_observation f JOIN dim_station s ON s.station_id=f.station_id
            JOIN dim_parameter p ON p.parameter_code=f.parameter_code
            GROUP BY f.station_id,f.parameter_code,f.date_key,s.station_name,s.region,
            p.parameter_name,p.canonical_unit ORDER BY f.date_key,f.station_id,f.parameter_code''')
    else:
        observations = db.rows('SELECT f.*,s.station_name,s.region,p.parameter_name,p.canonical_unit FROM fact_observation f JOIN dim_station s ON s.station_id=f.station_id JOIN dim_parameter p ON p.parameter_code=f.parameter_code ORDER BY observed_at,station_id,parameter_code')
    runs = db.rows('SELECT * FROM etl_run ORDER BY started_at,run_id')
    issues = db.rows('SELECT reason,COUNT(*) AS count FROM data_quality_issue GROUP BY reason ORDER BY count DESC,reason')
    payload = {'observations': observations, 'runs': runs, 'issues': issues, 'exported_at': now(),
               'source': metadata, 'aggregation': 'daily' if daily else 'raw'}
    return write_report(payload, destination)


def write_report(payload, destination):
    """Render a recorded snapshot without requiring a running database."""
    template = Path(__file__).with_name('report.html').read_text(encoding='utf-8')
    script = Path(__file__).with_name('explorer.js').read_text(encoding='utf-8')
    # Prevent source strings from closing the embedded JSON script element.
    encoded = json.dumps(payload, allow_nan=False).replace('<', '\\u003c').replace('&', '\\u0026')
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    metadata = payload.get('source')
    label = 'HISTORICAL PUBLIC DATA' if metadata and metadata.get('real') else 'SYNTHETIC DATA'
    destination.write_text(template.replace('__PAYLOAD__', encoded)
                           .replace('__EXPLORER_SCRIPT__', script)
                           .replace('__SOURCE_LABEL__', label), encoding='utf-8')
    return {'file': str(destination), 'observations': sum(r.get('sample_count', 1) for r in payload['observations']),
            'display_rows': len(payload['observations']), 'runs': len(payload['runs'])}
