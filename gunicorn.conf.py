"""Gunicorn configuration for production deployment."""

import os

bind = '0.0.0.0:8000'
workers = int(os.environ.get('WEB_CONCURRENCY', 4))
worker_class = 'gthread'
threads = 2
timeout = 120
accesslog = '-'
errorlog = '-'
loglevel = 'info'

# Load the app once in the master process before forking workers.
# APScheduler starts threads in the master; threads are not inherited by
# forked workers, so the scheduler runs in exactly one process.
preload_app = True


def post_fork(server, worker):
    """Reset SQLAlchemy connection pool after fork to avoid shared connections."""
    from app import db
    db.engine.dispose()
