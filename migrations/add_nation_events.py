from sqlalchemy import text


def migrate(app):
    from app import db
    with app.app_context():
        db.session.execute(text("""
            CREATE TABLE IF NOT EXISTS nation_events (
                id           SERIAL PRIMARY KEY,
                nation_id    INTEGER NOT NULL REFERENCES nations(id),
                event_type   VARCHAR(32) NOT NULL,
                description  VARCHAR(255) NOT NULL,
                reference_id INTEGER,
                occurred_at  TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """))
        db.session.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_nation_events_nation_id
            ON nation_events (nation_id)
        """))

        # Backfill 'founded' for all existing nations
        db.session.execute(text("""
            INSERT INTO nation_events (nation_id, event_type, description, occurred_at)
            SELECT id,
                   'founded',
                   name || ' was founded.',
                   COALESCE(founded_date::timestamptz, now())
            FROM nations
            ON CONFLICT DO NOTHING
        """))

        # Backfill war_declared / war_received from existing wars
        db.session.execute(text("""
            INSERT INTO nation_events (nation_id, event_type, description, reference_id, occurred_at)
            SELECT w.attacker_nation_id,
                   'war_declared',
                   'Declared war on ' || dn.name || '.',
                   w.id,
                   w.declared_at
            FROM wars w
            JOIN nations dn ON dn.id = w.defender_nation_id
            ON CONFLICT DO NOTHING
        """))
        db.session.execute(text("""
            INSERT INTO nation_events (nation_id, event_type, description, reference_id, occurred_at)
            SELECT w.defender_nation_id,
                   'war_received',
                   'War declared by ' || an.name || '.',
                   w.id,
                   w.declared_at
            FROM wars w
            JOIN nations an ON an.id = w.attacker_nation_id
            ON CONFLICT DO NOTHING
        """))

        # Backfill war_ended events for settled wars
        db.session.execute(text("""
            INSERT INTO nation_events (nation_id, event_type, description, reference_id, occurred_at)
            SELECT w.attacker_nation_id,
                   'war_ended',
                   CASE w.status
                       WHEN 'peace'       THEN 'White peace signed in ' || w.name || '.'
                       WHEN 'compensated' THEN w.name || ' ended by compensation.'
                       WHEN 'annexed'     THEN w.name || ' ended by annexation.'
                       ELSE w.name || ' ended.'
                   END,
                   w.id,
                   COALESCE(w.ended_at, now())
            FROM wars w
            WHERE w.status != 'active'
            ON CONFLICT DO NOTHING
        """))
        db.session.execute(text("""
            INSERT INTO nation_events (nation_id, event_type, description, reference_id, occurred_at)
            SELECT w.defender_nation_id,
                   'war_ended',
                   CASE w.status
                       WHEN 'peace'       THEN 'White peace signed in ' || w.name || '.'
                       WHEN 'compensated' THEN w.name || ' ended by compensation.'
                       WHEN 'annexed'     THEN w.name || ' ended by annexation.'
                       ELSE w.name || ' ended.'
                   END,
                   w.id,
                   COALESCE(w.ended_at, now())
            FROM wars w
            WHERE w.status != 'active'
            ON CONFLICT DO NOTHING
        """))

        db.session.commit()
