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
