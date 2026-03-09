import os
import sys
from sqlalchemy import text

# Add parent directory to path so we can import app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app, db

PARTITIONED_TABLES = [
    'natural_resources',
    'nation_factories',
    'divisions',
    'units',
    'recruitment_queue',
    'factory_build_queue',
    'equipment',
    'trade_orders',
    'messages',
    'battles',
    'combat_reports',
    'trade_executions'
]

NUM_PARTITIONS = 16

def create_partitions():
    app = create_app()
    with app.app_context():
        print(f"Creating {NUM_PARTITIONS} hash partitions for each partitioned table...")
        
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
            
            print(f"✅ Created partitions for {table}")
            db.session.commit()

if __name__ == '__main__':
    create_partitions()
    print("Done.")
