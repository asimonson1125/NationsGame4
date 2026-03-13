from sqlalchemy import text


def migrate(app):
    from app import db
    with app.app_context():
        db.session.execute(text("""
            ALTER TABLE divisions
            ADD COLUMN IF NOT EXISTS is_defensive BOOLEAN NOT NULL DEFAULT FALSE
        """))
        db.session.commit()
