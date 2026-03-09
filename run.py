import os
import sys
from sqlalchemy import text
from app import create_app, db

app = create_app(os.environ.get('FLASK_ENV', 'default'))

PARTITIONED_TABLES = [
    'natural_resources', 'nation_factories', 'divisions', 'units',
    'recruitment_queue', 'factory_build_queue', 'equipment',
    'trade_orders', 'messages', 'battles', 'combat_reports',
    'trade_executions'
]
# Fewer partitions in tests to speed up suite
NUM_PARTITIONS = int(os.environ.get('DB_PARTITIONS', 16))

def create_partitions():
    """Create hash partitions for the PostgreSQL database."""
    # Only run on PostgreSQL
    if 'postgresql' not in str(db.engine.url):
        print("Skipping partition creation (non-PostgreSQL dialect).")
        return

    print(f"Ensuring {NUM_PARTITIONS} hash partitions for each table...")
    for table in PARTITIONED_TABLES:
        for i in range(NUM_PARTITIONS):
            partition_name = f"{table}_p{i}"
            sql = f"CREATE TABLE IF NOT EXISTS {partition_name} PARTITION OF {table} FOR VALUES WITH (MODULUS {NUM_PARTITIONS}, REMAINDER {i});"
            try:
                db.session.execute(text(sql))
            except Exception as e:
                print(f"Failed to create partition {partition_name}: {e}")
                db.session.rollback()
                continue
        db.session.commit()
    print("Partitioning check complete.")

@app.cli.command('init-db')
def init_db():
    """Initialize the database and create partitions."""
    db.create_all()
    create_partitions()
    print('Database initialized.')

@app.cli.command('create-partitions')
def create_partitions_command():
    """Manually trigger partition creation."""
    create_partitions()
    print('Partitions created.')


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        create_partitions()
    app.run(debug=True)
