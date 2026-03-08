import json
from flask import render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, login_required, current_user
from datetime import date
from .. import db
from ..models import User, Nation
from . import auth


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
        nation_name = request.form.get('nation_name', '').strip()
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')
        error = None
        if not username or not nation_name:
            error = 'Username and nation name are required.'
        elif len(password) < 8:
            error = 'Password must be at least 8 characters.'
        elif password != confirm:
            error = 'Passwords do not match.'
        elif User.query.filter_by(username=username).first():
            error = 'Username already taken.'
        if error:
            flash(error, 'error')
        else:
            user = User(username=username)
            user.set_password(password)
            db.session.add(user)
            db.session.flush()
            nation = Nation(
                user_id=user.id,
                name=nation_name,
                leader=username,
                founded_date=date.today(),
            )
            db.session.add(nation)
            db.session.flush()
            from ..models import NationFactory
            starters = [('farm', 10), ('windmill', 5), ('quarry', 5)]
            for factory_key, count in starters:
                db.session.add(NationFactory(nation_id=nation.id, factory_key=factory_key, count=count, production_capacity=6))
            db.session.commit()
            login_user(user)
            return redirect(url_for('main.home'))
    return render_template('auth/register.html')


@auth.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))


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
    current_user.vacation_mode = 'vacation_mode' in request.form
    db.session.commit()
    resp = current_app.response_class(status=204)
    resp.headers['HX-Trigger'] = json.dumps(
        {'showMessage': {'message': 'Vacation mode updated.', 'type': 'success'}}
    )
    return resp
