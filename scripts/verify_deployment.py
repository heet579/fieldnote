"""Unauthenticated checks of the public Vercel portfolio and downloads."""
import csv
import io
import json
import urllib.request
from zipfile import ZipFile
from datetime import datetime, timezone
from pathlib import Path

BASE = 'https://fieldnote-torrens.vercel.app'


def request(path, method='GET'):
    req = urllib.request.Request(BASE + path, method=method,
                                 headers={'User-Agent': 'Fieldnote-Public-Verification/1.0'})
    with urllib.request.urlopen(req, timeout=45) as response:
        assert response.status == 200
        return response.read() if method == 'GET' else dict(response.headers)


def main():
    page = request('/').decode('utf-8')
    dataset = json.loads(page.split('<script id="dataset" type="application/json">')[1].split('</script>')[0])
    assert dataset['source']['real'] is True
    assert sum(r['sample_count'] for r in dataset['observations']) == 1012742
    assert len(dataset['observations']) == 10566
    assert b'1,012,742' in request('/about')
    with urllib.request.urlopen(BASE + '/case-study', timeout=45) as legacy:
        assert legacy.geturl().rstrip('/').endswith('/about')
    assert not any(term in page.split('<script')[0].lower() for term in ['portfolio','job role','dew affiliation'])
    assert dataset['source']['years'] == [2015,2016,2017,2018]
    manifest = json.loads(request('/source.json'))
    assert manifest['sha256'] == dataset['source']['sha256']
    evidence = json.loads(request('/real-evidence.json'))
    assert evidence['restore_matches_live_database'] is True
    verification = json.loads(request('/real-verification.json'))
    assert verification['source_values_matched'] == 1012742
    rows = list(csv.DictReader(io.StringIO(request('/daily-observations.csv').decode('utf-8'))))
    assert len(rows) == 10566
    assert sum(int(row['sample_count']) for row in rows) == 1012742
    headers = request('/Fieldnote-Source.zip', method='HEAD')
    # Git builds omit large raw inputs; validate the ZIP itself, not its size.
    archive = request('/Fieldnote-Source.zip')
    assert len(archive) == int(headers['Content-Length'])
    with ZipFile(io.BytesIO(archive)) as bundle:
        assert bundle.testzip() is None
        names = bundle.namelist()
        assert 'Fieldnote/warehouse/explorer.js' in names
        assert 'Fieldnote/portfolio/dashboard.html' in names
        assert not any('/runtime/' in name or name.endswith('/.env') for name in names)
    home_headers = request('/', method='HEAD')
    assert home_headers.get('X-Content-Type-Options') == 'nosniff'
    result = {'public_url': BASE, 'verified_at': datetime.now(timezone.utc).isoformat(),
              'unauthenticated_http_checks': 'passed', 'accepted_readings': 1012742,
              'daily_summary_rows': 10566, 'source_manifest_matches_report': True,
              'about_page_and_downloads': 'HTTP 200', 'source_package_bytes': int(headers['Content-Length'])}
    Path('portfolio/deployment-verification.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
