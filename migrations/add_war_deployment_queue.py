from sqlalchemy import text


def migrate(app):
    from app import db
    with app.app_context():
        db.session.execute(text("""
            CREATE TABLE IF NOT EXISTS war_deployment_queue (
                id SERIAL PRIMARY KEY,
                war_id INTEGER NOT NULL REFERENCES wars(id),
                deploying_nation_id INTEGER NOT NULL REFERENCES nations(id),
                division_id INTEGER NOT NULL,
                arrives_at TIMESTAMP WITH TIME ZONE NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'traveling'
            )
        """))
        db.session.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_war_deploy_war ON war_deployment_queue (war_id)"
        ))
        db.session.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_war_deploy_nation ON war_deployment_queue (deploying_nation_id)"
        ))
        db.session.commit()
