from sqlalchemy import text


def migrate(app):
    from app import db
    with app.app_context():
        db.session.execute(text("""
            CREATE TABLE IF NOT EXISTS wars (
                id SERIAL PRIMARY KEY,
                attacker_nation_id INTEGER NOT NULL REFERENCES nations(id),
                defender_nation_id INTEGER NOT NULL REFERENCES nations(id),
                name VARCHAR(200) NOT NULL,
                casus_belli TEXT NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'active',
                attacker_victories INTEGER NOT NULL DEFAULT 0,
                defender_victories INTEGER NOT NULL DEFAULT 0,
                declared_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
                ended_at TIMESTAMP WITH TIME ZONE,
                peace_offered_by INTEGER
            )
        """))
        db.session.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_wars_attacker ON wars (attacker_nation_id)"
        ))
        db.session.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_wars_defender ON wars (defender_nation_id)"
        ))
        db.session.commit()
