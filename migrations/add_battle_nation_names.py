"""Add attacker_nation_name and defender_nation_name snapshot columns to battles.

Run from project root:
    python3 -c "from run import app; from migrations.add_battle_nation_names import migrate; migrate(app)"
"""
from sqlalchemy import text


def migrate(app):
    from app import db
    with app.app_context():
        db.session.execute(text(
            "ALTER TABLE battles ADD COLUMN IF NOT EXISTS attacker_nation_name VARCHAR(120)"
        ))
        db.session.execute(text(
            "ALTER TABLE battles ADD COLUMN IF NOT EXISTS defender_nation_name VARCHAR(120)"
        ))
        db.session.commit()
        print("Migration complete: added battles.attacker_nation_name and battles.defender_nation_name columns.")
