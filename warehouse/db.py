"""Small DB-API compatibility layer; values always use bound parameters."""
import os
import sqlite3
from pathlib import Path


class Database:
    def __init__(self, target):
        self.postgres = str(target).startswith(('postgresql://', 'postgres://'))
        if self.postgres:
            import psycopg
            from psycopg.rows import dict_row
            self.connection = psycopg.connect(target, row_factory=dict_row)
        else:
            Path(target).parent.mkdir(parents=True, exist_ok=True)
            self.connection = sqlite3.connect(target)
            self.connection.row_factory = sqlite3.Row
            self.connection.execute('PRAGMA foreign_keys=ON')
            self.connection.execute('PRAGMA busy_timeout=5000')

    def execute(self, sql, values=()):
        return self.connection.execute(sql.replace('?', '%s') if self.postgres else sql, values)

    def rows(self, sql, values=()):
        return [dict(r) for r in self.execute(sql, values).fetchall()]

    def commit(self):
        self.connection.commit()

    def rollback(self):
        self.connection.rollback()

    def close(self):
        self.connection.close()


def default_target():
    return os.getenv('WAREHOUSE_DSN', 'runtime/warehouse.sqlite')


def initialise(db):
    schema = Path(__file__).with_name('schema.sql').read_text(encoding='utf-8')
    for statement in schema.split(';'):
        if statement.strip():
            # PostgreSQL does not support CREATE VIEW IF NOT EXISTS.
            if db.postgres:
                statement = statement.replace('CREATE VIEW IF NOT EXISTS', 'CREATE OR REPLACE VIEW')
            db.execute(statement)
    stations = [
        ('DEMO01', 'River Reach A (fictional)', 'Demonstration North'),
        ('DEMO02', 'Wetland B (fictional)', 'Demonstration Central'),
        ('DEMO03', 'Reservoir C (fictional)', 'Demonstration South'),
        ('DEMO04', 'Creek D (fictional)', 'Demonstration Hills'),
    ]
    for row in stations:
        db.execute('INSERT INTO dim_station VALUES (?,?,?) ON CONFLICT(station_id) DO NOTHING', row)
    for row in [('TEMP', 'Water temperature', 'degC'), ('PH', 'pH', 'pH'),
                ('EC', 'Electrical conductivity', 'uS/cm')]:
        db.execute('INSERT INTO dim_parameter VALUES (?,?,?) ON CONFLICT(parameter_code) DO NOTHING', row)
    db.commit()
