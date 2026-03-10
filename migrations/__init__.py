"""Lightweight migration runner.

Each migration module must define a `migrate(app)` function.
A `_migrations_applied` table tracks which migrations have already run.
"""
from importlib import import_module
from sqlalchemy import text

# Ordered list of migration module names (add new migrations at the end)
MIGRATIONS = [
    'add_growth_mode',
    'add_alliance_columns',
]


def _ensure_tracking_table(db):
    db.session.execute(text(
        "CREATE TABLE IF NOT EXISTS _migrations_applied ("
        "  name VARCHAR(200) PRIMARY KEY,"
        "  applied_at TIMESTAMP DEFAULT now()"
        ")"
    ))
    db.session.commit()


def run_all(app):
    from app import db
    with app.app_context():
        _ensure_tracking_table(db)
        applied = {
            row[0] for row in
            db.session.execute(text("SELECT name FROM _migrations_applied")).fetchall()
        }
        for name in MIGRATIONS:
            if name in applied:
                continue
            mod = import_module(f'migrations.{name}')
            mod.migrate(app)
            db.session.execute(
                text("INSERT INTO _migrations_applied (name) VALUES (:name)"),
                {'name': name},
            )
            db.session.commit()
            print(f"  Applied migration: {name}")
        print("Migrations up to date.")
