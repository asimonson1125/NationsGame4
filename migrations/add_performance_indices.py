"""Add performance indices to nations, trade_orders, trade_executions, and messages.

Run from project root:
    python3 -c "from run import app; from migrations.add_performance_indices import migrate; migrate(app)"
"""
from sqlalchemy import text

def migrate(app):
    from app import db
    with app.app_context():
        # Nations name index
        db.session.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_nation_name ON nations (name)"
        ))

        # Trade orders compound index (partitioned table)
        db.session.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_trade_orders_resource_status_type ON trade_orders (resource_key, status, order_type, price_per_unit)"
        ))

        # Trade executions index (partitioned table)
        db.session.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_trade_executions_resource_date ON trade_executions (resource_key, executed_at)"
        ))

        # Messages unread index (partitioned table)
        db.session.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_messages_recipient_unread ON messages (recipient_id, is_read)"
        ))

        db.session.commit()
        print("Migration complete: performance indices added.")
