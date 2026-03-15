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
    'add_missions',
    'add_mission_skips',
    'add_battle_nation_names',
    'add_vacation_cooldown',
    'add_buildings',
    'add_alliance_applications',
    'add_battle_location',
    'add_banner_url',
    'add_wars',
    'add_war_battles',
    'add_war_deployment_queue',
    'add_division_defensive',
    'add_ban_columns',
    'add_battle_name',
    'add_user_system_flag',
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
