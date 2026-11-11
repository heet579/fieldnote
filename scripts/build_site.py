"""Build the public lake explorer from an explicit file allowlist."""
import csv
import html
import json
import shutil
from pathlib import Path
from warehouse.report import write_report


def build():
    source = Path('portfolio/dashboard.html').read_text(encoding='utf-8')
    payload = json.loads(source.split('<script id="dataset" type="application/json">')[1].split('</script>')[0])
    if not payload.get('source', {}).get('real'):
        raise ValueError('Public build requires the genuine-data report.')
    site = Path('site'); site.mkdir(exist_ok=True)
    # Remove only known retired public artifacts; preserve Vercel's project link.
    for filename in ('case-study.html', 'Fieldnote-Portfolio.zip'):
        retired = (site / filename).resolve()
        retired.relative_to(site.resolve())
        if retired.is_file():
            retired.unlink()
    write_report(payload, site / 'index.html')
    for src, dst in [('data/real/manifest.json','source.json'),
                     ('portfolio/real-evidence.json','real-evidence.json'),
                     ('data/real/profile.json','raw-data-profile.json'),
                     ('portfolio/real-verification.json','real-verification.json')]:
        shutil.copyfile(src, site / dst)
    fields = ['station_id','station_name','parameter_code','parameter_name','canonical_unit',
              'date_key','sample_count','value','min_value','max_value']
    with (site / 'daily-observations.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore')
        writer.writeheader(); writer.writerows(payload['observations'])
    reference = Path('portfolio/monthly-reference.json')
    if reference.exists():
        shutil.copyfile(reference, site / reference.name)
    evidence = json.loads(Path('portfolio/real-evidence.json').read_text(encoding='utf-8'))
    n, rejects = evidence['initial_load']['inserted'], evidence['initial_load']['rejected']
    profile = json.loads(Path('data/real/profile.json').read_text(encoding='utf-8'))
    names = {r['station_id']: r['station_name'] for r in payload['observations']}
    station_rows = ''.join(f'<tr><td>{html.escape(names[station])}</td><td>{values["first"][:10]}</td><td>{values["last"][:10]}</td></tr>' for station,values in sorted(profile['stations'].items()))
    about = Path('warehouse/about.html').read_text(encoding='utf-8')
    for token,value in {'__COUNT__':f'{n:,}','__REJECTS__':str(rejects),
                        '__DAILY__':f'{len(payload["observations"]):,}',
                        '__STATION_ROWS__':station_rows,
                        '__HASH__':html.escape(payload['source']['sha256']),
                        '__SOURCE_URL__':html.escape(payload['source']['download_url'],quote=True)}.items():
        about = about.replace(token,value)
    (site / 'about.html').write_text(about, encoding='utf-8')
    config = {'version':2,'cleanUrls':True,'framework':None,
              'redirects':[{'source':'/case-study','destination':'/about','permanent':True},
                           {'source':'/Fieldnote-Portfolio.zip','destination':'/Fieldnote-Source.zip','permanent':True}],
              'headers':[{'source':'/(.*)','headers':[
                  {'key':'X-Content-Type-Options','value':'nosniff'},
                  {'key':'Referrer-Policy','value':'strict-origin-when-cross-origin'},
                  {'key':'X-Frame-Options','value':'DENY'}]}]}
    (site / 'vercel.json').write_text(json.dumps(config,indent=2),encoding='utf-8')
    archive = Path('Fieldnote-Source.zip')
    if archive.exists():
        shutil.copyfile(archive, site / archive.name)
    for page in ('index.html','about.html'):
        visible = (site/page).read_text(encoding='utf-8').split('<script')[0].lower()
        if any(term in visible for term in ['portfolio','job reference','job role','dew affiliation','recruitment','application instructions']):
            raise ValueError(f'Retired branding remains in {page}')
    print(json.dumps({'directory':str(site),'readings':n,'daily_summaries':len(payload['observations']),'years':payload['source']['years']}))


if __name__ == '__main__':
    build()
