from sqlalchemy import text


def migrate(app):
    from app import db
    with app.app_context():
        db.session.execute(text("""
            CREATE TABLE IF NOT EXISTS war_battles (
                id SERIAL PRIMARY KEY,
                war_id INTEGER NOT NULL REFERENCES wars(id),
                battle_id INTEGER NOT NULL,
                attacker_nation_id INTEGER NOT NULL,
                side VARCHAR(20) NOT NULL
            )
        """))
        db.session.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_war_battles_war ON war_battles (war_id)"
        ))
        db.session.commit()
