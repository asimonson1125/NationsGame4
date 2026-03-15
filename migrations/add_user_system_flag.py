"""Add is_system column to users table.

Run from project root:
    python3 -c "from run import app; from migrations.add_user_system_flag import migrate; migrate(app)"
"""
from sqlalchemy import text


def migrate(app):
    from app import db
    with app.app_context():
        # Add is_system column to users table
        db.session.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_system BOOLEAN DEFAULT FALSE"
        ))
        db.session.commit()
        print("Migration complete: is_system column added to users table.")
