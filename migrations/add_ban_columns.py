from sqlalchemy import text


def migrate(app):
    from app import db
    with app.app_context():
        db.session.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS banned_until TIMESTAMP WITH TIME ZONE"
        ))
        db.session.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS ban_message VARCHAR(500)"
        ))
        db.session.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS login_version INTEGER NOT NULL DEFAULT 1"
        ))
        db.session.commit()
