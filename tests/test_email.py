"""Tests for email verification, password reset, email change, and password change flows."""
import secrets
from datetime import datetime, timezone, timedelta
import pytest
from app import db
from app.models import User, Nation


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_user(username='emailtester', email='emailtester@test.com',
               verified=True, login_version=1):
    u = User(username=username, email=email,
             email_verified=verified, login_version=login_version)
    u.set_password('testpass1')
    db.session.add(u)
    db.session.flush()
    n = Nation(user_id=u.id, name=f'{username}Nation', continent='Westberg',
               money=100_000, food=10_000, power=10_000,
               building_materials=10_000, consumer_goods=10_000,
               metal=10_000, ammunition=10_000, fuel=10_000)
    db.session.add(n)
    db.session.commit()
    return u


def _login(client, user_id, login_version=1):
    with client.session_transaction() as sess:
        sess['_user_id'] = f'{user_id}:{login_version}'


# ── Registration sends verification email ────────────────────────────────────

def test_register_sets_verify_token(app, client):
    resp = client.post('/register', data={
        'username': 'newuser',
        'email': 'newuser@test.com',
        'nation_name': 'NewNation',
        'demonym': 'Newish',
        'continent': 'Westberg',
        'password': 'password123',
        'confirm_password': 'password123',
        'csrf_token': _get_csrf(client, '/register'),
    }, follow_redirects=False)
    # Should redirect to verify_email_sent (not home)
    assert resp.status_code == 302
    assert 'verify-email-sent' in resp.headers['Location']

    with app.app_context():
        u = User.query.filter_by(username='newuser').first()
        assert u is not None
        assert u.email_verify_token is not None
        assert not u.email_verified


def _get_csrf(client, path):
    from flask_wtf.csrf import generate_csrf
    with client.application.test_request_context():
        return generate_csrf()


# ── Email verification token ──────────────────────────────────────────────────

def test_verify_email_valid_token(app, client):
    with app.app_context():
        u = _make_user(verified=False)
        token = secrets.token_urlsafe(32)
        u.email_verify_token = token
        u.email_verify_expires_at = datetime.now(timezone.utc) + timedelta(hours=72)
        db.session.commit()
        uid = u.id

    resp = client.get(f'/verify-email/{token}', follow_redirects=False)
    assert resp.status_code == 200  # renders email_verified.html

    with app.app_context():
        u = db.session.get(User, uid)
        assert u.email_verified is True
        assert u.email_verify_token is None


def test_verify_email_expired_token(app, client):
    with app.app_context():
        u = _make_user(verified=False, username='expiredver', email='expiredver@test.com')
        token = secrets.token_urlsafe(32)
        u.email_verify_token = token
        u.email_verify_expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        db.session.commit()

    resp = client.get(f'/verify-email/{token}', follow_redirects=True)
    assert resp.status_code == 200
    assert b'invalid or has expired' in resp.data


def test_verify_email_invalid_token(app, client):
    resp = client.get('/verify-email/notarealtoken', follow_redirects=True)
    assert resp.status_code == 200
    assert b'invalid or has expired' in resp.data


# ── Forgot / reset password ───────────────────────────────────────────────────

def test_forgot_password_nonexistent_email_returns_200(app, client):
    """Must not reveal whether the email exists (enumeration-safe)."""
    resp = client.post('/forgot-password', data={
        'email': 'nobody@nowhere.com',
        'csrf_token': _get_csrf(client, '/forgot-password'),
    })
    assert resp.status_code == 200
    assert b'reset link has been sent' in resp.data


def test_forgot_password_valid_email_sets_token(app, client):
    with app.app_context():
        u = _make_user(username='resetme', email='resetme@test.com')
        uid = u.id

    client.post('/forgot-password', data={
        'email': 'resetme@test.com',
        'csrf_token': _get_csrf(client, '/forgot-password'),
    })

    with app.app_context():
        u = db.session.get(User, uid)
        assert u.password_reset_token is not None
        assert not u.password_reset_expired


def test_reset_password_valid_token(app, client):
    with app.app_context():
        u = _make_user(username='resetpw', email='resetpw@test.com')
        token = secrets.token_urlsafe(32)
        u.password_reset_token = token
        u.password_reset_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        old_version = u.login_version
        db.session.commit()
        uid = u.id

    resp = client.post(f'/reset-password/{token}', data={
        'password': 'newpassword1',
        'confirm_password': 'newpassword1',
        'csrf_token': _get_csrf(client, f'/reset-password/{token}'),
    }, follow_redirects=False)
    assert resp.status_code == 302
    assert 'login' in resp.headers['Location']

    with app.app_context():
        u = db.session.get(User, uid)
        assert u.check_password('newpassword1')
        assert u.login_version == old_version + 1
        assert u.password_reset_token is None


def test_reset_password_expired_token_redirects(app, client):
    with app.app_context():
        u = _make_user(username='expiredpw', email='expiredpw@test.com')
        token = secrets.token_urlsafe(32)
        u.password_reset_token = token
        u.password_reset_expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.session.commit()

    resp = client.get(f'/reset-password/{token}', follow_redirects=False)
    assert resp.status_code == 302
    assert 'forgot-password' in resp.headers['Location']


def test_reset_password_mismatch(app, client):
    with app.app_context():
        u = _make_user(username='mismatch', email='mismatch@test.com')
        token = secrets.token_urlsafe(32)
        u.password_reset_token = token
        u.password_reset_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        db.session.commit()

    resp = client.post(f'/reset-password/{token}', data={
        'password': 'newpassword1',
        'confirm_password': 'different!!',
        'csrf_token': _get_csrf(client, f'/reset-password/{token}'),
    })
    assert resp.status_code == 200
    assert b'do not match' in resp.data


# ── Email change ──────────────────────────────────────────────────────────────

def test_update_email_sets_pending(app, client):
    with app.app_context():
        u = _make_user(username='changeemail', email='changeemail@test.com')
        uid = u.id
    _login(client, uid)

    resp = client.post('/update-email', data={'new_email': 'newaddr@test.com'},
                       headers={'HX-Request': 'true'})
    assert resp.status_code == 204

    with app.app_context():
        u = db.session.get(User, uid)
        assert u.pending_email == 'newaddr@test.com'
        assert u.pending_email_token is not None
        assert u.email == 'changeemail@test.com'  # not changed yet


def test_confirm_email_change_swaps_email(app, client):
    with app.app_context():
        u = _make_user(username='confirmchange', email='confirmchange@test.com')
        token = secrets.token_urlsafe(32)
        u.pending_email = 'confirmed@test.com'
        u.pending_email_token = token
        u.pending_email_expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
        db.session.commit()
        uid = u.id

    resp = client.get(f'/confirm-email-change/{token}', follow_redirects=False)
    assert resp.status_code == 302

    with app.app_context():
        u = db.session.get(User, uid)
        assert u.email == 'confirmed@test.com'
        assert u.email_verified is True
        assert u.pending_email is None
        assert u.pending_email_token is None


def test_confirm_email_change_duplicate_email(app, client):
    """If the new email is already taken, email should not change."""
    with app.app_context():
        _make_user(username='existing', email='taken@test.com')
        u = _make_user(username='changer2', email='changer2@test.com')
        token = secrets.token_urlsafe(32)
        u.pending_email = 'taken@test.com'
        u.pending_email_token = token
        u.pending_email_expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
        db.session.commit()
        uid = u.id

    client.get(f'/confirm-email-change/{token}', follow_redirects=False)

    with app.app_context():
        u = db.session.get(User, uid)
        assert u.email == 'changer2@test.com'  # unchanged
        assert u.pending_email is None  # still cleared


def test_cancel_email_change(app, client):
    with app.app_context():
        u = _make_user(username='cancelemail', email='cancelemail@test.com')
        u.pending_email = 'cancel@test.com'
        u.pending_email_token = secrets.token_urlsafe(32)
        u.pending_email_expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
        db.session.commit()
        uid = u.id
    _login(client, uid)

    resp = client.post('/cancel-email-change', headers={'HX-Request': 'true'})
    assert resp.status_code == 204

    with app.app_context():
        u = db.session.get(User, uid)
        assert u.pending_email is None
        assert u.pending_email_token is None


def test_update_email_duplicate_rejected(app, client):
    with app.app_context():
        _make_user(username='dup1', email='dup@test.com')
        u2 = _make_user(username='dup2', email='dup2@test.com')
        uid = u2.id
    _login(client, uid)

    resp = client.post('/update-email', data={'new_email': 'dup@test.com'},
                       headers={'HX-Request': 'true'})
    assert resp.status_code == 422


# ── Password change (authenticated) ──────────────────────────────────────────

def test_change_password_success(app, client):
    with app.app_context():
        u = _make_user(username='changepw', email='changepw@test.com')
        old_version = u.login_version
        uid = u.id
    _login(client, uid, old_version)

    resp = client.post('/change-password', data={
        'current_password': 'testpass1',
        'new_password': 'newpassword9',
        'confirm_password': 'newpassword9',
    }, headers={'HX-Request': 'true'})
    assert resp.status_code == 204

    with app.app_context():
        u = db.session.get(User, uid)
        assert u.check_password('newpassword9')
        assert u.login_version == old_version + 1


def test_change_password_wrong_current(app, client):
    with app.app_context():
        u = _make_user(username='wrongpw', email='wrongpw@test.com')
        uid = u.id
    _login(client, uid)

    resp = client.post('/change-password', data={
        'current_password': 'wrongpassword',
        'new_password': 'newpassword9',
        'confirm_password': 'newpassword9',
    }, headers={'HX-Request': 'true'})
    assert resp.status_code == 422


def test_change_password_mismatch(app, client):
    with app.app_context():
        u = _make_user(username='mismatchwpw', email='mismatchwpw@test.com')
        uid = u.id
    _login(client, uid)

    resp = client.post('/change-password', data={
        'current_password': 'testpass1',
        'new_password': 'newpassword9',
        'confirm_password': 'different!!9',
    }, headers={'HX-Request': 'true'})
    assert resp.status_code == 422
