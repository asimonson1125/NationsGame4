"""Add mission_skips_today column to nations table.

Run from project root:
    python3 -c "from run import app; from migrations.add_mission_skips import migrate; migrate(app)"
"""
from sqlalchemy import text


def migrate(app):
    from app import db
    with app.app_context():
        db.session.execute(text(
            "ALTER TABLE nations ADD COLUMN IF NOT EXISTS mission_skips_today INTEGER NOT NULL DEFAULT 0"
        ))
        db.session.commit()
        print("Migration complete: added nations.mission_skips_today column.")
