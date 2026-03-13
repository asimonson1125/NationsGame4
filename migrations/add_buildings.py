"""Add nation_buildings and building_upgrade_queue tables; seed Barracks Lvl 1 for existing nations.

Run from project root:
    python3 -c "from run import app; from migrations.add_buildings import migrate; migrate(app)"
"""
from sqlalchemy import text


def migrate(app):
    from app import db
    with app.app_context():
        db.session.execute(text("""
            CREATE TABLE IF NOT EXISTS nation_buildings (
                id          SERIAL PRIMARY KEY,
                nation_id   INTEGER NOT NULL REFERENCES nations(id),
                building_key VARCHAR(64) NOT NULL,
                level       INTEGER NOT NULL DEFAULT 1,
                CONSTRAINT uq_nation_building UNIQUE (nation_id, building_key)
            )
        """))
        db.session.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_nation_buildings_nation_id ON nation_buildings (nation_id)"
        ))

        db.session.execute(text("""
            CREATE TABLE IF NOT EXISTS building_upgrade_queue (
                id           SERIAL PRIMARY KEY,
                nation_id    INTEGER NOT NULL REFERENCES nations(id),
                building_key VARCHAR(64) NOT NULL,
                target_level INTEGER NOT NULL,
                started_at   TIMESTAMP NOT NULL DEFAULT now(),
                completes_at TIMESTAMP NOT NULL,
                CONSTRAINT uq_building_upgrade UNIQUE (nation_id, building_key)
            )
        """))
        db.session.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_building_upgrade_queue_nation_id ON building_upgrade_queue (nation_id)"
        ))

        # Seed Barracks Lvl 1 for all existing nations that don't have one
        db.session.execute(text("""
            INSERT INTO nation_buildings (nation_id, building_key, level)
            SELECT id, 'barracks', 1 FROM nations
            ON CONFLICT (nation_id, building_key) DO NOTHING
        """))

        # Award building_gp = 5 (Barracks Lvl 1) for nations that currently have 0
        db.session.execute(text("""
            UPDATE nations SET building_gp = 5 WHERE building_gp = 0
        """))

        db.session.commit()
        print("Migration complete: buildings tables created, Barracks Lvl 1 seeded for existing nations.")
