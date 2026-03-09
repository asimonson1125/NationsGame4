from datetime import datetime, timezone, timedelta
from app import db
from app.models import Nation, RecruitmentQueue, Unit


def _make_target(name='TargetNation'):
    """Create a non-admin nation to be the target of admin actions."""
    from app.models import User
    u = User(username=f'user_{name}', email=f'{name}@test.com')
    u.set_password('password')
    db.session.add(u)
    db.session.flush()
    n = Nation(user_id=u.id, name=name, continent='Westberg', money=5000, food=1000)
    db.session.add(n)
    db.session.commit()
    return n


# ── Resource editing ───────────────────────────────────────────────────

def test_set_resource(app, admin_client):
    with app.app_context():
        target = _make_target()
        resp = admin_client.post(f'/admin/nation/{target.id}/resource',
                                 data={'resource': 'money', 'mode': 'set', 'value': '99999'})
        assert resp.status_code == 200
        db.session.refresh(target)
        assert target.money == 99999.0


def test_add_resource(app, admin_client):
    with app.app_context():
        target = _make_target()
        original = target.money
        resp = admin_client.post(f'/admin/nation/{target.id}/resource',
                                 data={'resource': 'money', 'mode': 'add', 'value': '500'})
        assert resp.status_code == 200
        db.session.refresh(target)
        assert target.money == original + 500


def test_subtract_resource(app, admin_client):
    with app.app_context():
        target = _make_target()
        original = target.money
        resp = admin_client.post(f'/admin/nation/{target.id}/resource',
                                 data={'resource': 'money', 'mode': 'subtract', 'value': '100'})
        assert resp.status_code == 200
        db.session.refresh(target)
        assert target.money == original - 100


# ── Authorization ──────────────────────────────────────────────────────

def test_non_admin_gets_403(app, auth_client):
    """A logged-in non-admin user should get 403 on admin routes."""
    with app.app_context():
        resp = auth_client.post('/admin/nation/1/resource',
                                data={'resource': 'money', 'mode': 'set', 'value': '1'})
        assert resp.status_code == 403


# ── Validation ─────────────────────────────────────────────────────────

def test_invalid_resource_rejected(app, admin_client):
    with app.app_context():
        target = _make_target()
        resp = admin_client.post(f'/admin/nation/{target.id}/resource',
                                 data={'resource': 'not_a_column', 'mode': 'set', 'value': '1'})
        assert resp.status_code == 422


# ── Queue completion ───────────────────────────────────────────────────

def test_complete_queue_entry(app, admin_client):
    with app.app_context():
        target = _make_target()
        entry = RecruitmentQueue(
            nation_id=target.id,
            unit_key='infantry',
            completes_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        db.session.add(entry)
        db.session.commit()
        entry_id = entry.id
        old_gp = target.military_gp or 0

        resp = admin_client.post(f'/admin/nation/{target.id}/complete-queue/{entry_id}')
        assert resp.status_code == 200

        # Entry should be gone
        assert db.session.get(RecruitmentQueue, entry_id) is None
        # Unit should exist
        unit = Unit.query.filter_by(nation_id=target.id, unit_key='infantry').first()
        assert unit is not None
        assert unit.firepower == 3  # infantry fp from UNIT_DEFS
        # GP should have incremented
        db.session.refresh(target)
        assert target.military_gp == old_gp + 1


def test_complete_nonexistent_entry(app, admin_client):
    with app.app_context():
        target = _make_target()
        resp = admin_client.post(f'/admin/nation/{target.id}/complete-queue/99999')
        assert resp.status_code == 422
