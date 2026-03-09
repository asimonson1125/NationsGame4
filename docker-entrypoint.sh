#!/bin/sh
set -e

# Initialize database tables on first boot
echo "Running database initialization..."
python3 -c "
from app import create_app, db
app = create_app('production')
with app.app_context():
    db.create_all()
    print('Database tables ready.')
"

exec "$@"
