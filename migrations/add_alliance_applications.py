from sqlalchemy import text


def migrate(app):
    from app import db
    with app.app_context():
        db.session.execute(text("""
            CREATE TABLE IF NOT EXISTS alliance_applications (
                id SERIAL PRIMARY KEY,
                alliance_id INTEGER NOT NULL REFERENCES alliances(id) ON DELETE CASCADE,
                nation_id INTEGER NOT NULL REFERENCES nations(id) ON DELETE CASCADE,
                status VARCHAR(20) NOT NULL DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT now(),
                UNIQUE (alliance_id, nation_id)
            )
        """))
        db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_alliance_applications_alliance_id ON alliance_applications(alliance_id)"))
        db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_alliance_applications_nation_id ON alliance_applications(nation_id)"))
        db.session.commit()
