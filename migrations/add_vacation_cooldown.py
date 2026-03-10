"""Add vacation_disabled_at column to users table.

Run from project root:
    python3 -c "from run import app; from migrations.add_vacation_cooldown import migrate; migrate(app)"
"""
from sqlalchemy import text


def migrate(app):
    from app import db
    with app.app_context():
        db.session.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS vacation_disabled_at TIMESTAMPTZ"
        ))
        db.session.commit()
        print("Migration complete: added users.vacation_disabled_at column.")
