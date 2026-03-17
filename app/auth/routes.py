import json
import secrets
from flask import render_template, redirect, url_for, flash, request, current_app, get_flashed_messages
from flask_login import login_user, logout_user, login_required, current_user
from datetime import date, datetime, timezone, timedelta
from .. import db, limiter
from flask_limiter.util import get_remote_address
from ..models import User, Nation, Unit, Division, NationEvent
from ..game.constants import CONTINENTS
from ..game.discovery import LAND_WEIGHTS, _weighted_distribute
from ..game.population import compute_population_gp
from ..email import send_verification_email, send_password_reset_email, send_email_change_email
from . import auth

VALID_CONTINENTS = set(CONTINENTS)


@auth.route('/login', methods=['GET', 'POST'])
@limiter.limit("10 per minute; 50 per hour", key_func=get_remote_address)
def login():
    if current_user.is_authenticated:
        get_flashed_messages()  # discard any stale flashes from pre-login flows
        return redirect(url_for('main.home'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        remember = 'remember' in request.form
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            if user.is_banned:
                msg = user.ban_message or 'Your account has been temporarily suspended.'
                until = user.banned_until.strftime('%Y-%m-%d %H:%M UTC')
                flash(f'Account suspended until {until}: {msg}', 'error')
                return render_template('auth/login.html')
            from flask import session
            session.permanent = remember
            login_user(user, remember=remember)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('main.home'))
        flash('Invalid username or password.', 'error')
    return render_template('auth/login.html')


@auth.route('/register', methods=['GET', 'POST'])
@limiter.limit("5 per minute; 20 per hour", key_func=get_remote_address)
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.home'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        nation_name = request.form.get('nation_name', '').strip()
        demonym = request.form.get('demonym', '').strip()
        continent = request.form.get('continent', '').strip()
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')
        error = None
        if not username:
            error = 'Username is required.'
        elif not email or '@' not in email:
            error = 'A valid email address is required.'
        elif len(password) < 8:
            error = 'Password must be at least 8 characters.'
        elif password != confirm:
            error = 'Passwords do not match.'
        elif not nation_name or not demonym:
            error = 'Nation name and demonym are required.'
        elif continent not in VALID_CONTINENTS:
            error = 'Please select a valid continent.'
        elif User.query.filter_by(username=username).first():
            error = 'Username already taken.'
        elif User.query.filter_by(email=email).first():
            error = 'Email already in use.'
        if error:
            flash(error, 'error')
        else:
            user = User(username=username, email=email)
            user.set_password(password)
            db.session.add(user)
            db.session.flush()

            # Distribute 500 uncleared land tiles by continent weights (excluding cleared_land)
            weights = {k: v for k, v in LAND_WEIGHTS[continent].items() if k != 'cleared_land'}
            starting_land = _weighted_distribute(weights, 500)

            nation = Nation(
                user_id=user.id,
                name=nation_name,
                demonym=demonym,
                leader=username,
                founded_date=date.today(),
                continent=continent,
                population=50_000,
                urban_areas=50,
                cleared_land=20,
                total_land=570,  # 50 urban + 20 cleared + 500 uncleared
                **starting_land,
            )
            db.session.add(nation)
            db.session.flush()
            from ..helpers import grant_factories
            from ..game.factories import FACTORY_DEFS
            from ..models import NationBuilding
            from ..game.buildings import BUILDING_DEFS
            starter = [('farm', 5), ('windmill', 5), ('quarry', 3)]
            grant_factories(nation, starter, production_capacity=6)
            nation.used_land = (nation.used_land or 0) + sum(
                qty * sum(FACTORY_DEFS[key].land_required.values())
                for key, qty in starter if key in FACTORY_DEFS
            )

            # Seed 6 infantry — 4 in "Division 1", 2 in reserve
            div = Division(nation_id=nation.id, name='Division 1')
            db.session.add(div)
            db.session.flush()
            for i in range(6):
                unit = Unit.create_from_def(nation.id, 'infantry',
                                            division_id=div.id if i < 4 else None)
                db.session.add(unit)
            nation.military_gp = (nation.military_gp or 0) + 6  # 1 GP per infantry

            # Seed Barracks at level 1 (free starting building)
            barracks = NationBuilding(nation_id=nation.id, building_key='barracks', level=1)
            db.session.add(barracks)
            nation.building_gp = BUILDING_DEFS['barracks'].gp_per_level[0]

            nation.land_gp = (nation.total_land or 0) // 10
            nation.population_gp = compute_population_gp(nation.population)

            db.session.add(NationEvent(
                nation_id=nation.id,
                event_type='founded',
                description=f'{nation.name} was founded by {username}.',
            ))
            user.email_verify_token = secrets.token_urlsafe(32)
            user.email_verify_expires_at = datetime.now(timezone.utc) + timedelta(hours=72)
            db.session.commit()
            link = url_for('auth.verify_email', token=user.email_verify_token, _external=True)
            send_verification_email(user, link)
            login_user(user)
            return redirect(url_for('auth.verify_email_sent'))
    return render_template('auth/register.html')


@auth.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('main.index'))


@auth.route('/update-email', methods=['POST'])
@login_required
def update_email():
    new_email = request.form.get('new_email', '').strip()
    if not new_email or '@' not in new_email:
        resp = current_app.response_class(status=422)
        resp.headers['HX-Trigger'] = json.dumps(
            {'showMessage': {'message': 'Invalid email address.', 'type': 'error'}}
        )
        return resp
    if User.query.filter(User.email == new_email, User.id != current_user.id).first():
        resp = current_app.response_class(status=422)
        resp.headers['HX-Trigger'] = json.dumps(
            {'showMessage': {'message': 'Email already in use.', 'type': 'error'}}
        )
        return resp
    current_user.pending_email = new_email
    current_user.pending_email_token = secrets.token_urlsafe(32)
    current_user.pending_email_expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
    db.session.commit()
    link = url_for('auth.confirm_email_change', token=current_user.pending_email_token, _external=True)
    send_email_change_email(current_user, new_email, link)
    resp = current_app.response_class(status=204)
    resp.headers['HX-Trigger'] = json.dumps(
        {'showMessage': {'message': 'Check your new inbox to confirm the change.', 'type': 'success'}}
    )
    return resp


@auth.route('/update-notifications', methods=['POST'])
@login_required
def update_notifications():
    current_user.notifications_enabled = 'notifications_enabled' in request.form
    db.session.commit()
    resp = current_app.response_class(status=204)
    resp.headers['HX-Trigger'] = json.dumps(
        {'showMessage': {'message': 'Notification settings saved.', 'type': 'success'}}
    )
    return resp


@auth.route('/toggle-vacation', methods=['POST'])
@login_required
def toggle_vacation():
    wants_on = 'vacation_mode' in request.form
    now = datetime.now(timezone.utc)

    if wants_on and not current_user.vacation_mode:
        # Enforce 48h cooldown after last disable
        if current_user.vacation_disabled_at:
            cooldown_end = current_user.vacation_disabled_at + timedelta(hours=48)
            if now < cooldown_end:
                remaining = cooldown_end - now
                hours = int(remaining.total_seconds() // 3600)
                mins = int((remaining.total_seconds() % 3600) // 60)
                resp = current_app.response_class(status=204)
                resp.headers['HX-Trigger'] = json.dumps(
                    {'showMessage': {'message': f'Vacation cooldown active. Try again in {hours}h {mins}m.', 'type': 'error'}}
                )
                return resp
        current_user.vacation_mode = True
    elif not wants_on and current_user.vacation_mode:
        current_user.vacation_mode = False
        current_user.vacation_disabled_at = now

    db.session.commit()
    resp = current_app.response_class(status=204)
    resp.headers['HX-Trigger'] = json.dumps(
        {'showMessage': {'message': 'Vacation mode updated.', 'type': 'success'}}
    )
    return resp


# ── Email / password recovery routes ─────────────────────────────────────────

@auth.route('/verify-email-sent')
def verify_email_sent():
    return render_template('auth/verify_email_sent.html')


@auth.route('/verify-email/<token>')
@limiter.limit("20 per hour", key_func=get_remote_address)
def verify_email(token):
    user = User.query.filter_by(email_verify_token=token).first()
    if not user or not user.email_verify_expires_at or \
            datetime.now(timezone.utc) > user.email_verify_expires_at:
        flash('Verification link is invalid or has expired.', 'error')
        return redirect(url_for('auth.login'))
    user.email_verified = True
    user.email_verify_token = None
    user.email_verify_expires_at = None
    db.session.commit()
    return render_template('auth/email_verified.html')


@auth.route('/resend-verification')
@login_required
@limiter.limit("3 per hour", key_func=lambda: f"resend:{current_user.id}")
def resend_verification():
    if current_user.email_verified:
        return redirect(url_for('main.home'))
    current_user.email_verify_token = secrets.token_urlsafe(32)
    current_user.email_verify_expires_at = datetime.now(timezone.utc) + timedelta(hours=72)
    db.session.commit()
    link = url_for('auth.verify_email', token=current_user.email_verify_token, _external=True)
    send_verification_email(current_user, link)
    return redirect(url_for('auth.verify_email_sent'))


@auth.route('/forgot-password', methods=['GET', 'POST'])
@limiter.limit("5 per hour", key_func=get_remote_address)
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for('main.home'))
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        user = User.query.filter_by(email=email).first() if email else None
        if user:
            user.password_reset_token = secrets.token_urlsafe(32)
            user.password_reset_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
            db.session.commit()
            link = url_for('auth.reset_password', token=user.password_reset_token, _external=True)
            send_password_reset_email(user, link)
        # Always show the same page to prevent email enumeration
        flash('If that email is registered, a reset link has been sent.', 'info')
        return render_template('auth/forgot_password.html')
    return render_template('auth/forgot_password.html')


@auth.route('/reset-password/<token>', methods=['GET', 'POST'])
@limiter.limit("10 per hour", key_func=get_remote_address)
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for('main.home'))
    user = User.query.filter_by(password_reset_token=token).first()
    if not user or user.password_reset_expired:
        flash('Reset link is invalid or has expired.', 'error')
        return redirect(url_for('auth.forgot_password'))
    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')
        if len(password) < 8:
            flash('Password must be at least 8 characters.', 'error')
            return render_template('auth/reset_password.html', token=token)
        if password != confirm:
            flash('Passwords do not match.', 'error')
            return render_template('auth/reset_password.html', token=token)
        user.set_password(password)
        user.login_version = (user.login_version or 1) + 1
        user.password_reset_token = None
        user.password_reset_expires_at = None
        db.session.commit()
        flash('Password updated. You can now log in.', 'info')
        return redirect(url_for('auth.login'))
    return render_template('auth/reset_password.html', token=token)


@auth.route('/confirm-email-change/<token>')
@limiter.limit("20 per hour", key_func=get_remote_address)
def confirm_email_change(token):
    user = User.query.filter_by(pending_email_token=token).first()
    if not user or user.pending_email_expired:
        flash('Email change link is invalid or has expired.', 'error')
        return redirect(url_for('main.account'))
    new_email = user.pending_email
    if User.query.filter(User.email == new_email, User.id != user.id).first():
        flash('That email address is already in use.', 'error')
    else:
        user.email = new_email
        user.email_verified = True
    user.pending_email = None
    user.pending_email_token = None
    user.pending_email_expires_at = None
    db.session.commit()
    return redirect(url_for('main.account'))


@auth.route('/cancel-email-change', methods=['POST'])
@login_required
def cancel_email_change():
    current_user.pending_email = None
    current_user.pending_email_token = None
    current_user.pending_email_expires_at = None
    db.session.commit()
    resp = current_app.response_class(status=204)
    resp.headers['HX-Trigger'] = json.dumps(
        {'showMessage': {'message': 'Email change cancelled.', 'type': 'success'}}
    )
    return resp


@auth.route('/change-password', methods=['POST'])
@login_required
@limiter.limit("5 per minute", key_func=lambda: f"chpw:{current_user.id}")
def change_password():
    current_pw = request.form.get('current_password', '')
    new_pw = request.form.get('new_password', '')
    confirm_pw = request.form.get('confirm_password', '')
    if not current_user.check_password(current_pw):
        resp = current_app.response_class(status=422)
        resp.headers['HX-Trigger'] = json.dumps(
            {'showMessage': {'message': 'Current password is incorrect.', 'type': 'error'}}
        )
        return resp
    if len(new_pw) < 8:
        resp = current_app.response_class(status=422)
        resp.headers['HX-Trigger'] = json.dumps(
            {'showMessage': {'message': 'New password must be at least 8 characters.', 'type': 'error'}}
        )
        return resp
    if new_pw != confirm_pw:
        resp = current_app.response_class(status=422)
        resp.headers['HX-Trigger'] = json.dumps(
            {'showMessage': {'message': 'Passwords do not match.', 'type': 'error'}}
        )
        return resp
    current_user.set_password(new_pw)
    current_user.login_version = (current_user.login_version or 1) + 1
    db.session.commit()
    resp = current_app.response_class(status=204)
    resp.headers['HX-Trigger'] = json.dumps(
        {'showMessage': {'message': 'Password updated. Please log in again.', 'type': 'success'}}
    )
    return resp
