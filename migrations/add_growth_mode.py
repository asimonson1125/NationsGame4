"""Add growth_mode column to nations table.

Run from project root:
    python3 -c "from run import app; from migrations.add_growth_mode import migrate; migrate(app)"
"""
from sqlalchemy import text


def migrate(app):
    from app import db
    with app.app_context():
        # Add the column if it doesn't exist
        db.session.execute(text(
            "ALTER TABLE nations ADD COLUMN IF NOT EXISTS growth_mode VARCHAR(10) DEFAULT 'auto'"
        ))
        db.session.commit()
        print("Migration complete: growth_mode column added to nations.")
