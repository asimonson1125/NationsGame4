from sqlalchemy import text


def migrate(app):
    from app import db
    with app.app_context():
        db.session.execute(text(
            "ALTER TABLE battles ADD COLUMN IF NOT EXISTS name VARCHAR(300)"
        ))
        db.session.commit()
