#!/bin/sh
set -e

# Initialize database tables and partitions on first boot
echo "Running database and partition initialization..."
python3 -c "
import os
from app import create_app, db
from run import create_partitions
app = create_app('production')
with app.app_context():
    db.create_all()
    create_partitions()
    print('Database and partitions ready.')
"

exec "$@"
