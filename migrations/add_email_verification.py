from sqlalchemy import text


def migrate(app):
    from app import db
    with app.app_context():
        db.session.execute(text("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified BOOLEAN NOT NULL DEFAULT FALSE;
            ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verify_token VARCHAR(64);
            ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verify_expires_at TIMESTAMP WITH TIME ZONE;
            ALTER TABLE users ADD COLUMN IF NOT EXISTS pending_email VARCHAR(120);
            ALTER TABLE users ADD COLUMN IF NOT EXISTS pending_email_token VARCHAR(64);
            ALTER TABLE users ADD COLUMN IF NOT EXISTS pending_email_expires_at TIMESTAMP WITH TIME ZONE;
            ALTER TABLE users ADD COLUMN IF NOT EXISTS password_reset_token VARCHAR(64);
            ALTER TABLE users ADD COLUMN IF NOT EXISTS password_reset_expires_at TIMESTAMP WITH TIME ZONE;
        """))

        db.session.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_users_email_verify_token
              ON users (email_verify_token) WHERE email_verify_token IS NOT NULL;
            CREATE UNIQUE INDEX IF NOT EXISTS uq_users_pending_email_token
              ON users (pending_email_token) WHERE pending_email_token IS NOT NULL;
            CREATE UNIQUE INDEX IF NOT EXISTS uq_users_password_reset_token
              ON users (password_reset_token) WHERE password_reset_token IS NOT NULL;
        """))

        # Backfill: existing accounts with email are grandfathered as verified
        db.session.execute(text("""
            UPDATE users SET email_verified = TRUE WHERE email IS NOT NULL;
        """))

        db.session.commit()
