"""Tests for alliance creation, membership management, and application workflow."""
import json
import pytest
from app import db
from app.models import Alliance, AllianceApplication, Nation, User


def _trigger(resp):
    return json.loads(resp.headers.get('HX-Trigger', '{}'))


def _msg(resp):
    return _trigger(resp).get('showMessage', {})


def _make_nation(name):
    """Create and persist a user+nation. Returns the nation."""
    u = User(username=name, email=f'{name}@test.com', login_version=1)
    u.set_password('password')
    db.session.add(u)
    db.session.flush()
    n = Nation(user_id=u.id, name=name, continent='Westberg',
               money=500_000, food=50_000)
    db.session.add(n)
    db.session.commit()
    return n


def _client_for(app, user_id):
    """Return a new test client already logged in as user_id.

    Also clears Flask-Login's g._login_user cache so the shared AppContext
    (from setup_db fixture) doesn't return the previous user on the next request.
    """
    from flask import g
    g.pop('_login_user', None)
    c = app.test_client()
    with c.session_transaction() as sess:
        sess['_user_id'] = f'{user_id}:1'
    return c



def _make_alliance(name, founder):
    """Create and persist an alliance owned by founder."""
    ally = Alliance(name=name, founder_id=founder.id)
    db.session.add(ally)
    db.session.flush()
    founder.alliance_id = ally.id
    db.session.commit()
    return ally


class TestCreateAlliance:
    def test_creates_alliance(self, app, auth_client, nation):
        resp = auth_client.post('/alliance/create', data={'name': 'Iron Pact'})
        assert resp.status_code == 200
        assert Alliance.query.filter_by(name='Iron Pact').count() == 1

    def test_sets_nation_alliance_id(self, app, auth_client, nation):
        auth_client.post('/alliance/create', data={'name': 'Iron Pact'})
        db.session.refresh(nation)
        assert nation.alliance_id is not None

    def test_sets_founder(self, app, auth_client, nation):
        auth_client.post('/alliance/create', data={'name': 'Iron Pact'})
        ally = Alliance.query.filter_by(name='Iron Pact').first()
        assert ally.founder_id == nation.id

    def test_hx_redirect_on_success(self, app, auth_client, nation):
        resp = auth_client.post('/alliance/create', data={'name': 'Iron Pact'})
        assert 'HX-Redirect' in resp.headers

    def test_rejects_name_too_short(self, app, auth_client, nation):
        assert _msg(auth_client.post('/alliance/create', data={'name': 'X'})).get('type') == 'error'
        assert Alliance.query.count() == 0

    def test_rejects_name_too_long(self, app, auth_client, nation):
        assert _msg(auth_client.post('/alliance/create', data={'name': 'A' * 61})).get('type') == 'error'

    def test_rejects_duplicate_name(self, app, auth_client, nation):
        _make_alliance('Iron Pact', _make_nation('OtherFounder'))
        assert _msg(auth_client.post('/alliance/create', data={'name': 'Iron Pact'})).get('type') == 'error'

    def test_duplicate_check_case_insensitive(self, app, auth_client, nation):
        _make_alliance('Iron Pact', _make_nation('OtherFounder'))
        assert _msg(auth_client.post('/alliance/create', data={'name': 'iron pact'})).get('type') == 'error'

    def test_rejects_when_already_in_alliance(self, app, auth_client, nation):
        auth_client.post('/alliance/create', data={'name': 'First'})
        assert _msg(auth_client.post('/alliance/create', data={'name': 'Second'})).get('type') == 'error'


class TestApplyToAlliance:
    def test_creates_pending_application(self, app, auth_client, nation):
        n2 = _make_nation('Founder')
        ally = _make_alliance('The Guild', n2)

        resp = auth_client.post('/alliance/apply', data={'alliance_id': str(ally.id)})
        assert resp.status_code == 204
        entry = AllianceApplication.query.filter_by(alliance_id=ally.id, nation_id=nation.id).first()
        assert entry is not None
        assert entry.status == 'pending'

    def test_notifies_founder_on_apply(self, app, auth_client, nation):
        from app.models import Message
        n2 = _make_nation('Founder')
        ally = _make_alliance('The Guild', n2)
        auth_client.post('/alliance/apply', data={'alliance_id': str(ally.id)})
        msg = Message.query.filter_by(recipient_id=n2.id).first()
        assert msg is not None

    def test_rejects_when_already_in_alliance(self, app, auth_client, nation):
        # nation creates their own alliance first
        auth_client.post('/alliance/create', data={'name': 'OwnAlliance'})
        n2 = _make_nation('Founder')
        ally = _make_alliance('Other Guild', n2)
        assert _msg(auth_client.post('/alliance/apply', data={'alliance_id': str(ally.id)})).get('type') == 'error'

    def test_rejects_duplicate_pending(self, app, auth_client, nation):
        n2 = _make_nation('Founder')
        ally = _make_alliance('The Guild', n2)
        auth_client.post('/alliance/apply', data={'alliance_id': str(ally.id)})
        msg = _msg(auth_client.post('/alliance/apply', data={'alliance_id': str(ally.id)}))
        assert msg.get('type') == 'error'
        assert 'pending' in msg.get('message', '').lower()

    def test_reopens_rejected_application(self, app, auth_client, nation):
        n2 = _make_nation('Founder')
        ally = _make_alliance('The Guild', n2)
        auth_client.post('/alliance/apply', data={'alliance_id': str(ally.id)})
        # Manually reject
        entry = AllianceApplication.query.filter_by(alliance_id=ally.id, nation_id=nation.id).first()
        entry.status = 'rejected'
        db.session.commit()
        # Apply again
        resp = auth_client.post('/alliance/apply', data={'alliance_id': str(ally.id)})
        assert resp.status_code == 204
        db.session.refresh(entry)
        assert entry.status == 'pending'

    def test_rejects_nonexistent_alliance(self, app, auth_client, nation):
        assert _msg(auth_client.post('/alliance/apply', data={'alliance_id': '99999'})).get('type') == 'error'


class TestApproveApplication:
    def _setup(self, app, auth_client, nation, applicant_name='Applicant'):
        auth_client.post('/alliance/create', data={'name': 'Main Alliance'})
        db.session.refresh(nation)
        ally = Alliance.query.filter_by(name='Main Alliance').first()
        n2 = _make_nation(applicant_name)
        entry = AllianceApplication(alliance_id=ally.id, nation_id=n2.id)
        db.session.add(entry)
        db.session.commit()
        return n2, entry, ally

    def test_approves_and_joins_alliance(self, app, auth_client, nation):
        n2, entry, ally = self._setup(app, auth_client, nation)
        resp = auth_client.post(f'/alliance/application/{entry.id}/approve')
        assert resp.status_code == 204
        db.session.refresh(n2)
        db.session.refresh(entry)
        assert n2.alliance_id == ally.id
        assert entry.status == 'approved'

    def test_rejects_other_pending_apps_for_same_nation(self, app, auth_client, nation):
        n2, entry, ally = self._setup(app, auth_client, nation)
        # n2 also applied to a second alliance
        ally2 = _make_alliance('Other Alliance', _make_nation('Founder2'))
        entry2 = AllianceApplication(alliance_id=ally2.id, nation_id=n2.id)
        db.session.add(entry2)
        db.session.commit()
        # Approve n2 into main alliance
        auth_client.post(f'/alliance/application/{entry.id}/approve')
        db.session.refresh(entry2)
        assert entry2.status == 'rejected'

    def test_non_founder_cannot_approve(self, app, auth_client, nation):
        n2, entry, ally = self._setup(app, auth_client, nation)
        n3 = _make_nation('NonFounder')
        c3 = _client_for(app, n3.user_id)
        msg = _msg(c3.post(f'/alliance/application/{entry.id}/approve'))
        assert msg.get('type') == 'error'
        db.session.refresh(n2)
        assert n2.alliance_id is None

    def test_error_if_applicant_joined_elsewhere(self, app, auth_client, nation):
        n2, entry, ally = self._setup(app, auth_client, nation)
        # n2 joins another alliance first
        ally2 = _make_alliance('Other Alliance', _make_nation('Founder2'))
        n2.alliance_id = ally2.id
        db.session.commit()
        msg = _msg(auth_client.post(f'/alliance/application/{entry.id}/approve'))
        assert msg.get('type') == 'error'
        db.session.refresh(entry)
        assert entry.status == 'rejected'


class TestRejectApplication:
    def _setup(self, app, auth_client, nation):
        auth_client.post('/alliance/create', data={'name': 'Main Alliance'})
        db.session.refresh(nation)
        ally = Alliance.query.filter_by(name='Main Alliance').first()
        n2 = _make_nation('Applicant')
        entry = AllianceApplication(alliance_id=ally.id, nation_id=n2.id)
        db.session.add(entry)
        db.session.commit()
        return n2, entry

    def test_rejects_application(self, app, auth_client, nation):
        n2, entry = self._setup(app, auth_client, nation)
        resp = auth_client.post(f'/alliance/application/{entry.id}/reject')
        assert resp.status_code == 204
        db.session.refresh(entry)
        assert entry.status == 'rejected'
        db.session.refresh(n2)
        assert n2.alliance_id is None

    def test_non_founder_cannot_reject(self, app, auth_client, nation):
        n2, entry = self._setup(app, auth_client, nation)
        n3 = _make_nation('NonFounder')
        c3 = _client_for(app, n3.user_id)
        msg = _msg(c3.post(f'/alliance/application/{entry.id}/reject'))
        assert msg.get('type') == 'error'
        db.session.refresh(entry)
        assert entry.status == 'pending'


class TestKickMember:
    def _setup(self, app, auth_client, nation):
        auth_client.post('/alliance/create', data={'name': 'Main Alliance'})
        db.session.refresh(nation)
        ally = Alliance.query.filter_by(name='Main Alliance').first()
        n2 = _make_nation('Member')
        n2.alliance_id = ally.id
        db.session.commit()
        return n2, ally

    def test_kicks_member(self, app, auth_client, nation):
        n2, ally = self._setup(app, auth_client, nation)
        resp = auth_client.post(f'/alliance/kick/{n2.id}')
        assert resp.status_code == 204
        db.session.refresh(n2)
        assert n2.alliance_id is None

    def test_cannot_kick_self(self, app, auth_client, nation):
        self._setup(app, auth_client, nation)
        assert _msg(auth_client.post(f'/alliance/kick/{nation.id}')).get('type') == 'error'

    def test_non_founder_cannot_kick(self, app, auth_client, nation):
        n2, ally = self._setup(app, auth_client, nation)
        n3 = _make_nation('OtherMember')
        n3.alliance_id = ally.id
        db.session.commit()
        c3 = _client_for(app, n3.user_id)
        msg = _msg(c3.post(f'/alliance/kick/{n2.id}'))
        assert msg.get('type') == 'error'
        db.session.refresh(n2)
        assert n2.alliance_id == ally.id

    def test_cannot_kick_non_member(self, app, auth_client, nation):
        self._setup(app, auth_client, nation)
        outsider = _make_nation('Outsider')
        assert _msg(auth_client.post(f'/alliance/kick/{outsider.id}')).get('type') == 'error'


class TestLeaveAlliance:
    def test_non_founder_leaves_cleanly(self, app, auth_client, nation):
        auth_client.post('/alliance/create', data={'name': 'Main Alliance'})
        db.session.refresh(nation)
        ally = Alliance.query.filter_by(name='Main Alliance').first()
        n2 = _make_nation('LeavingMember')
        n2.alliance_id = ally.id
        db.session.commit()

        c2 = _client_for(app, n2.user_id)
        resp = c2.post('/alliance/leave')
        assert resp.status_code == 200
        db.session.refresh(n2)
        assert n2.alliance_id is None
        assert db.session.get(Alliance, ally.id) is not None

    def test_founder_leave_transfers_to_other_member(self, app, auth_client, nation):
        auth_client.post('/alliance/create', data={'name': 'Main Alliance'})
        db.session.refresh(nation)
        ally = Alliance.query.filter_by(name='Main Alliance').first()
        n2 = _make_nation('NewFounder')
        n2.alliance_id = ally.id
        db.session.commit()

        resp = auth_client.post('/alliance/leave')
        assert resp.status_code == 200
        db.session.refresh(nation)
        db.session.refresh(ally)
        assert nation.alliance_id is None
        assert ally.founder_id == n2.id

    def test_last_member_leave_disbands_alliance(self, app, auth_client, nation):
        auth_client.post('/alliance/create', data={'name': 'Main Alliance'})
        db.session.refresh(nation)
        ally_id = Alliance.query.filter_by(name='Main Alliance').first().id

        resp = auth_client.post('/alliance/leave')
        assert resp.status_code == 200
        db.session.refresh(nation)
        assert nation.alliance_id is None
        assert db.session.get(Alliance, ally_id) is None

    def test_not_in_alliance_returns_error(self, app, auth_client, nation):
        assert nation.alliance_id is None
        assert _msg(auth_client.post('/alliance/leave')).get('type') == 'error'


class TestDisbandAlliance:
    def test_founder_disbands(self, app, auth_client, nation):
        auth_client.post('/alliance/create', data={'name': 'Main Alliance'})
        db.session.refresh(nation)
        ally_id = Alliance.query.filter_by(name='Main Alliance').first().id
        resp = auth_client.post('/alliance/disband')
        assert resp.status_code == 200
        assert db.session.get(Alliance, ally_id) is None
        db.session.refresh(nation)
        assert nation.alliance_id is None

    def test_removes_all_members(self, app, auth_client, nation):
        auth_client.post('/alliance/create', data={'name': 'Main Alliance'})
        db.session.refresh(nation)
        ally = Alliance.query.filter_by(name='Main Alliance').first()
        n2 = _make_nation('Member1')
        n3 = _make_nation('Member2')
        n2.alliance_id = ally.id
        n3.alliance_id = ally.id
        db.session.commit()

        auth_client.post('/alliance/disband')
        db.session.refresh(n2)
        db.session.refresh(n3)
        assert n2.alliance_id is None
        assert n3.alliance_id is None

    def test_deletes_pending_applications(self, app, auth_client, nation):
        auth_client.post('/alliance/create', data={'name': 'Main Alliance'})
        db.session.refresh(nation)
        ally = Alliance.query.filter_by(name='Main Alliance').first()
        n2 = _make_nation('Applicant')
        db.session.add(AllianceApplication(alliance_id=ally.id, nation_id=n2.id))
        db.session.commit()

        auth_client.post('/alliance/disband')
        assert AllianceApplication.query.filter_by(alliance_id=ally.id).count() == 0

    def test_non_founder_cannot_disband(self, app, auth_client, nation):
        auth_client.post('/alliance/create', data={'name': 'Main Alliance'})
        db.session.refresh(nation)
        ally = Alliance.query.filter_by(name='Main Alliance').first()
        n2 = _make_nation('NonFounder')
        n2.alliance_id = ally.id
        db.session.commit()

        c2 = _client_for(app, n2.user_id)
        msg = _msg(c2.post('/alliance/disband'))
        assert msg.get('type') == 'error'
        assert db.session.get(Alliance, ally.id) is not None

    def test_not_in_alliance_returns_error(self, app, auth_client, nation):
        assert _msg(auth_client.post('/alliance/disband')).get('type') == 'error'


class TestSearchAlliances:
    def test_returns_matching_alliances(self, app, auth_client, nation):
        ally = _make_alliance('Iron Pact', _make_nation('Founder'))
        resp = auth_client.get('/alliance/search?q=Iron')
        assert resp.status_code == 200
        data = resp.get_json()
        assert any(a['name'] == 'Iron Pact' for a in data)

    def test_short_query_returns_empty(self, app, auth_client, nation):
        resp = auth_client.get('/alliance/search?q=X')
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_returns_id_and_name(self, app, auth_client, nation):
        _make_alliance('Steel Union', _make_nation('Founder'))
        resp = auth_client.get('/alliance/search?q=Steel')
        data = resp.get_json()
        assert len(data) > 0
        assert 'id' in data[0]
        assert 'name' in data[0]
