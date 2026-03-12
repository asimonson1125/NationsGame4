"""Add banner_url column to nations table.

Run from project root:
    python3 -c "from run import app; from migrations.add_banner_url import migrate; migrate(app)"
"""
from sqlalchemy import text


def migrate(app):
    from app import db
    with app.app_context():
        db.session.execute(text(
            "ALTER TABLE nations ADD COLUMN IF NOT EXISTS banner_url VARCHAR(500) DEFAULT ''"
        ))
        db.session.commit()
        print("Migration complete: added nations.banner_url column.")
