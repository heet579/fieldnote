"""Re-export the real DB without rerunning or altering its loads."""
import json
from pathlib import Path
from warehouse.db import Database
from warehouse.report import export

if __name__ == '__main__':
    db = Database('runtime/real-v2/warehouse.sqlite')
    try:
        metadata = json.loads(Path('data/real/manifest.json').read_text(encoding='utf-8'))
        print(json.dumps(export(db, 'portfolio/dashboard.html', metadata=metadata, daily=True)))
    finally:
        db.close()
