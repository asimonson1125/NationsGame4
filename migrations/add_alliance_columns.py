"""Add flag_url, description, founder_id, created_at columns to alliances table.

Run from project root:
    python3 -c "from run import app; from migrations.add_alliance_columns import migrate; migrate(app)"
"""
from sqlalchemy import text


def migrate(app):
    from app import db
    with app.app_context():
        db.session.execute(text(
            "ALTER TABLE alliances ADD COLUMN IF NOT EXISTS flag_url VARCHAR(500) DEFAULT ''"
        ))
        db.session.execute(text(
            "ALTER TABLE alliances ADD COLUMN IF NOT EXISTS description TEXT DEFAULT ''"
        ))
        db.session.execute(text(
            "ALTER TABLE alliances ADD COLUMN IF NOT EXISTS founder_id INTEGER REFERENCES nations(id)"
        ))
        db.session.execute(text(
            "ALTER TABLE alliances ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT now()"
        ))
        db.session.commit()
        print("Migration complete: alliance columns added.")
