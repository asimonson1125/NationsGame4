"""Add mission_offers, mission_records tables; add mission columns to battles.

Run from project root:
    python3 -c "from run import app; from migrations.add_missions import migrate; migrate(app)"
"""
from sqlalchemy import text


def migrate(app):
    from app import db
    with app.app_context():
        # Widen battle_type to accommodate 'pve_mission'
        db.session.execute(text(
            "ALTER TABLE battles ALTER COLUMN battle_type TYPE VARCHAR(20)"
        ))

        # Add mission_offer_id to battles (plain integer — no FK due to partitioning)
        db.session.execute(text(
            "ALTER TABLE battles ADD COLUMN IF NOT EXISTS mission_offer_id INTEGER"
        ))

        # Create mission_offers table
        db.session.execute(text("""
            CREATE TABLE IF NOT EXISTS mission_offers (
                id           SERIAL PRIMARY KEY,
                nation_id    INTEGER NOT NULL REFERENCES nations(id),
                slot         INTEGER NOT NULL,
                mission_key  VARCHAR(80) NOT NULL,
                offered_at   TIMESTAMP NOT NULL DEFAULT now(),
                status       VARCHAR(20) NOT NULL DEFAULT 'available',
                battle_id    INTEGER,
                completed_at TIMESTAMP,
                CONSTRAINT uq_mission_offer_nation_slot UNIQUE (nation_id, slot)
            )
        """))
        db.session.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_mission_offers_nation_id ON mission_offers (nation_id)"
        ))

        # Create mission_records table
        db.session.execute(text("""
            CREATE TABLE IF NOT EXISTS mission_records (
                id           SERIAL PRIMARY KEY,
                nation_id    INTEGER NOT NULL REFERENCES nations(id),
                mission_key  VARCHAR(80) NOT NULL,
                completed_at TIMESTAMP NOT NULL,
                CONSTRAINT uq_mission_record_nation_key UNIQUE (nation_id, mission_key)
            )
        """))
        db.session.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_mission_records_nation_id ON mission_records (nation_id)"
        ))

        db.session.commit()
        print("Migration complete: missions tables and battle columns added.")
