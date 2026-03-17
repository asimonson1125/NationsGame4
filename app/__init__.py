import os
import hashlib
from flask import Flask, request, make_response, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_caching import Cache
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import current_user
from flask_mail import Mail as _Mail
from markupsafe import Markup
from config import config


def _rate_limit_key():
    if current_user.is_authenticated:
        return f"user:{current_user.id}"
    return get_remote_address()


db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()
cache = Cache()
limiter = Limiter(key_func=_rate_limit_key)
mailer = _Mail()


def format_resource(value):
    """Jinja2 filter: formats large numbers with tooltip showing exact value."""
    if value is None:
        return '0'
    value = round(value)
    raw = f'{value:,}'
    if value >= 1_000_000_000_000_000 or round(value / 1_000_000_000_000, 1) >= 1000:
        short = f'{value / 1_000_000_000_000_000:.1f}q'
    elif value >= 1_000_000_000_000 or round(value / 1_000_000_000, 1) >= 1000:
        short = f'{value / 1_000_000_000_000:.1f}t'
    elif value >= 1_000_000_000 or round(value / 1_000_000, 1) >= 1000:
        short = f'{value / 1_000_000_000:.1f}b'
    elif value >= 1_000_000 or round(value / 1_000, 1) >= 1000:
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
    cache.init_app(app)
    limiter.init_app(app)
    mailer.init_app(app)

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

    _hash_cache = {}

    def static_url(filename):
        if filename not in _hash_cache:
            path = os.path.join(app.static_folder, filename)
            try:
                h = hashlib.md5(str(os.path.getmtime(path)).encode()).hexdigest()[:8]
            except OSError:
                h = '0'
            _hash_cache[filename] = h
        return url_for('static', filename=filename, v=_hash_cache[filename])

    app.jinja_env.globals['static_url'] = static_url

    from .game.changelog import CHANGELOG
    from .game.levels import xp_for_next_level

    app.jinja_env.globals['xp_for_next_level'] = xp_for_next_level

    @app.context_processor
    def inject_globals():
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

    from .alliance import alliance as alliance_blueprint
    app.register_blueprint(alliance_blueprint)

    from .mail import mail as mail_blueprint
    app.register_blueprint(mail_blueprint)

    from .war import war as war_blueprint
    app.register_blueprint(war_blueprint)

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

    from flask import render_template

    @app.errorhandler(404)
    def page_not_found(e):
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def internal_server_error(e):
        return render_template('errors/500.html'), 500

    @app.errorhandler(429)
    def ratelimit_handler(e):
        if request.headers.get('HX-Request'):
            from .helpers import error_response
            return error_response("Too many requests — slow down.")
        return render_template('errors/429.html'), 429

    return app
