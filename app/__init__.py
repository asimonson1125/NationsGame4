from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from config import config

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()


def format_resource(value):
    """Jinja2 filter: formats large numbers to human-readable strings (e.g. 1.2m)."""
    if value is None:
        return '0'
    if value >= 1_000_000_000:
        return f'{value / 1_000_000_000:.1f}b'
    if value >= 1_000_000:
        return f'{value / 1_000_000:.1f}m'
    if value >= 1_000:
        return f'{value / 1_000:.1f}k'
    return f'{value:.0f}'


def create_app(config_name='default'):
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'info'

    app.jinja_env.filters['format_resource'] = format_resource

    from .auth import auth as auth_blueprint
    app.register_blueprint(auth_blueprint)

    from .main import main as main_blueprint
    app.register_blueprint(main_blueprint)

    from .economy import economy as economy_blueprint
    app.register_blueprint(economy_blueprint)

    import os
    if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        from .tasks import register_tasks
        register_tasks(app)

    return app
