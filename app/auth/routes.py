import json
from flask import render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, login_required, current_user
from datetime import date, datetime, timezone, timedelta
from .. import db
from ..models import User, Nation, Unit, Division
from ..game.constants import CONTINENTS
from ..game.discovery import LAND_WEIGHTS, _weighted_distribute
from ..game.population import compute_population_gp
from . import auth

VALID_CONTINENTS = set(CONTINENTS)


@auth.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.home'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('main.home'))
        flash('Invalid username or password.', 'error')
    return render_template('auth/login.html')


@auth.route('/register', methods=['GET', 'POST'])
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
            grant_factories(nation, [('farm', 5), ('windmill', 5), ('quarry', 3)], production_capacity=6)

            # Seed 6 infantry — 4 in "Division 1", 2 in reserve
            div = Division(nation_id=nation.id, name='Division 1')
            db.session.add(div)
            db.session.flush()
            for i in range(6):
                unit = Unit.create_from_def(nation.id, 'infantry',
                                            division_id=div.id if i < 4 else None)
                db.session.add(unit)
            nation.military_gp = (nation.military_gp or 0) + 6  # 1 GP per infantry

            nation.land_gp = (nation.total_land or 0) // 10
            nation.population_gp = compute_population_gp(nation.population)
            db.session.commit()
            login_user(user)
            return redirect(url_for('main.home'))
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
    current_user.email = new_email
    db.session.commit()
    resp = current_app.response_class(status=204)
    resp.headers['HX-Trigger'] = json.dumps(
        {'showMessage': {'message': 'Email updated successfully.', 'type': 'success'}}
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
