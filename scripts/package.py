"""Package reproducible explorer code and public data, excluding local secrets."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED


def main():
    root = Path(__file__).resolve().parents[1]
    output = root / 'Fieldnote-Source.zip'
    directories = ['warehouse', 'tests', 'scripts', 'sql', 'docs', 'portfolio', 'data/synthetic', 'data/real', '.github']
    files = ['README.md', 'requirements.txt', 'compose.yaml', '.env.example', '.gitignore', '.gitattributes', '.vercelignore', 'vercel.json']
    candidates = [root / name for name in files]
    excluded = {'case-study.md','linkedin-posts.md','synthetic-dashboard.html','evidence.json','deployment-verification.json'}
    for directory in directories:
        candidates.extend(p for p in (root / directory).rglob('*') if p.is_file()
                          and '__pycache__' not in p.parts and p.suffix != '.pyc'
                          and p.name not in excluded
                          and p.name != 'observations-2017.csv')
    with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
        for path in sorted(candidates):
            archive.write(path, Path('Fieldnote') / path.relative_to(root))
    print(f'Created {output.name}: {len(candidates)} source, documentation and data files. No runtime databases or .env included.')


if __name__ == '__main__':
    main()
