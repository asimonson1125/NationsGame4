from flask import Flask, request, make_response, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from markupsafe import Markup
from config import config

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()


def format_resource(value):
    """Jinja2 filter: formats large numbers with tooltip showing exact value."""
    if value is None:
        return '0'
    raw = f'{value:,.0f}'
    if value >= 1_000_000_000:
        short = f'{value / 1_000_000_000:.1f}b'
    elif value >= 1_000_000:
        short = f'{value / 1_000_000:.1f}m'
    elif value >= 1_000:
        short = f'{value / 1_000:.1f}k'
    else:
        return raw
    return Markup(f'<span class="rv" data-raw="{raw}">{short}</span>')


def cost_class(cost, stockpile):
    """Returns CSS class based on whether stockpile can afford cost."""
    if (stockpile or 0) < (cost or 0):
        return 'text-red-500 font-semibold'
    return 'text-slate-400'


def create_app(config_name='default'):
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'info'

    @login_manager.unauthorized_handler
    def handle_needs_login():
        if request.headers.get('HX-Request'):
            resp = make_response('', 200)
            resp.headers['HX-Redirect'] = url_for('auth.login')
            return resp
        return redirect(url_for('auth.login'))

    app.jinja_env.filters['format_resource'] = format_resource
    app.jinja_env.filters['cost_class'] = cost_class

    from .game.changelog import CHANGELOG

    @app.context_processor
    def inject_changelog():
        return dict(changelog=CHANGELOG, latest_update=CHANGELOG[0] if CHANGELOG else None)

    from .auth import auth as auth_blueprint
    app.register_blueprint(auth_blueprint)

    from .main import main as main_blueprint
    app.register_blueprint(main_blueprint)

    from .economy import economy as economy_blueprint
    app.register_blueprint(economy_blueprint)

    from .military import military as military_blueprint
    app.register_blueprint(military_blueprint)

    from .equipment import equipment as equipment_blueprint
    app.register_blueprint(equipment_blueprint)

    from .trade import trade as trade_blueprint
    app.register_blueprint(trade_blueprint)

    from .mail import mail as mail_blueprint
    app.register_blueprint(mail_blueprint)

    @app.context_processor
    def inject_unread_count():
        from flask_login import current_user
        count = 0
        if current_user.is_authenticated and current_user.nation:
            from .models import Message
            count = Message.query.filter_by(
                recipient_id=current_user.nation.id, is_read=False
            ).count()
        return dict(unread_mail_count=count)

    import os
    if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        from .tasks import register_tasks
        register_tasks(app)

    return app
