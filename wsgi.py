"""Production WSGI entry point."""

from app import create_app
from app.tasks import register_tasks

app = create_app('production')
register_tasks(app)
