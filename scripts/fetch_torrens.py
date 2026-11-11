"""Fetch the City of Adelaide's openly licensed Torrens Lake archive."""
import hashlib
import json
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

CATALOGUE = 'https://data.sa.gov.au/data/api/3/action/package_show?id=torrens-lake-meterological-data'


def fetch():
    directory = Path('data/real')
    directory.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(CATALOGUE, headers={'User-Agent': 'Fieldnote-Environmental-Portfolio/1.0'})
    with urllib.request.urlopen(request, timeout=60) as response:
        metadata = json.load(response)
    if not metadata.get('success'):
        raise ValueError('Catalogue request failed')
    package = metadata['result']
    if package['license_id'] != 'cc-by':
        raise ValueError('Dataset licence changed; review before reuse')
    resource = next(r for r in package['resources'] if r['id'] == 'bde0f295-35a2-4642-964b-31843cbaf1e2')
    request = urllib.request.Request(resource['url'], headers={'User-Agent': 'Fieldnote-Environmental-Portfolio/1.0'})
    with urllib.request.urlopen(request, timeout=90) as response:
        content = response.read(100 * 1024 * 1024 + 1)
        headers = dict(response.headers)
    if len(content) > 100 * 1024 * 1024:
        raise ValueError('Archive exceeds expected download limit')
    path = directory / 'TorrensWaterData.zip'
    path.write_bytes(content)
    receipt = {'publisher': package['organization']['title'], 'title': package['title'],
               'catalogue_url': 'https://data.sa.gov.au/data/dataset/torrens-lake-meterological-data',
               'download_url': resource['url'], 'licence': package['license_title'],
               'licence_url': package['license_url'], 'fetched_at': datetime.now(timezone.utc).isoformat(),
               'last_modified_http': headers.get('Last-Modified'),
               'sha256': hashlib.sha256(content).hexdigest(), 'bytes': len(content)}
    (directory / 'catalogue.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    (directory / 'source.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    print(json.dumps(receipt, indent=2))
    with zipfile.ZipFile(path) as archive:
        print(json.dumps({'archive_members': len(archive.infolist()),
                          'uncompressed_bytes': sum(i.file_size for i in archive.infolist())}))


if __name__ == '__main__':
    fetch()
