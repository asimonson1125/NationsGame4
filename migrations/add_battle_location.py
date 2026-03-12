"""Add location column to battles table.

Run from project root:
    python3 -c "from run import app; from migrations.add_battle_location import migrate; migrate(app)"
"""
from sqlalchemy import text


def migrate(app):
    from app import db
    with app.app_context():
        db.session.execute(text(
            "ALTER TABLE battles ADD COLUMN IF NOT EXISTS location VARCHAR(50)"
        ))
        db.session.commit()
        print("Migration complete: added battles.location column.")
