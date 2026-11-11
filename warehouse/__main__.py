import argparse
import json
import sys
from .db import Database, default_target, initialise
from .generate import generate
from .pipeline import load
from .operations import backup_sqlite, restore_sqlite, fingerprint
from .report import export


def main():
    parser = argparse.ArgumentParser(description='Fieldnote environmental monitoring warehouse')
    parser.add_argument('--db', default=default_target(), help='SQLite path or PostgreSQL DSN; defaults to WAREHOUSE_DSN or runtime/warehouse.sqlite')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('init')
    item = commands.add_parser('generate'); item.add_argument('--output', default='data/synthetic')
    item = commands.add_parser('load'); item.add_argument('source'); item.add_argument('--fail-after', type=int)
    item.add_argument('--timestamp-basis', choices=['utc', 'source_unspecified'], default='utc')
    item = commands.add_parser('report'); item.add_argument('--output', default='portfolio/dashboard.html')
    item = commands.add_parser('backup'); item.add_argument('destination')
    item = commands.add_parser('restore'); item.add_argument('source'); item.add_argument('destination')
    commands.add_parser('fingerprint')
    args = parser.parse_args()
    if args.command == 'generate':
        return generate(args.output)
    if args.command == 'restore':
        return restore_sqlite(args.source, args.destination)
    db = Database(args.db)
    try:
        if args.command == 'init':
            initialise(db); return {'status': 'initialised'}
        if args.command == 'load':
            return load(db, args.source, args.fail_after, timestamp_basis=args.timestamp_basis)
        if args.command == 'report':
            return export(db, args.output)
        if args.command == 'backup':
            return backup_sqlite(db, args.destination)
        return fingerprint(db)
    finally:
        db.close()


if __name__ == '__main__':
    try:
        print(json.dumps(main(), indent=2))
    except Exception as exc:
        # Keep driver errors from printing connection details.
        message = str(exc) if isinstance(exc, (ValueError, RuntimeError, FileNotFoundError)) else type(exc).__name__
        print(json.dumps({'status': 'error', 'error': message}), file=sys.stderr)
        sys.exit(1)
