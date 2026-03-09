"""Tests for military routes — overview, divisions, recruitment, units."""
import json
from datetime import datetime, timezone, timedelta
from app import db
from app.models import Division, Unit, RecruitmentQueue
from app.game.units import UNIT_DEFS


class TestOverview:
    def test_overview_page_loads(self, app, auth_client):
        resp = auth_client.get('/military')
        assert resp.status_code == 200
        assert b'Military Overview' in resp.data

    def test_overview_shows_empty_state(self, app, auth_client):
        resp = auth_client.get('/military')
        assert b'No divisions yet' in resp.data

    def test_overview_requires_login(self, app, client):
        resp = client.get('/military')
        assert resp.status_code == 302  # redirect to login


class TestDivisionRoutes:
    def test_create_division(self, app, auth_client, nation):
        resp = auth_client.post('/military/division/create', data={'name': 'Alpha'})
        assert resp.status_code == 200
        assert b'Alpha' in resp.data
        assert Division.query.filter_by(nation_id=nation.id).count() == 1

    def test_create_division_default_name(self, app, auth_client, nation):
        resp = auth_client.post('/military/division/create', data={'name': ''})
        assert resp.status_code == 200
        div = Division.query.filter_by(nation_id=nation.id).first()
        assert div is not None
        assert 'Division' in div.name

    def test_create_division_max_20(self, app, auth_client, nation):
        for i in range(20):
            db.session.add(Division(nation_id=nation.id, name=f'Div {i}'))
        db.session.flush()
        resp = auth_client.post('/military/division/create', data={'name': 'Extra'})
        assert resp.status_code == 422
        trigger = json.loads(resp.headers.get('HX-Trigger', '{}'))
        assert trigger['showMessage']['type'] == 'error'

    def test_rename_division(self, app, auth_client, nation):
        div = Division(nation_id=nation.id, name='Old Name')
        db.session.add(div)
        db.session.flush()
        resp = auth_client.post(f'/military/division/{div.id}/rename',
                                data={'name': 'New Name'})
        assert resp.status_code == 200
        assert b'New Name' in resp.data

    def test_rename_empty_rejected(self, app, auth_client, nation):
        div = Division(nation_id=nation.id, name='Test')
        db.session.add(div)
        db.session.flush()
        resp = auth_client.post(f'/military/division/{div.id}/rename',
                                data={'name': ''})
        assert resp.status_code == 422

    def test_disband_division_moves_units(self, app, auth_client, nation):
        div = Division(nation_id=nation.id, name='Temp')
        db.session.add(div)
        db.session.flush()
        unit = Unit(nation_id=nation.id, division_id=div.id, unit_key='infantry',
                    firepower=3, armour=1, maneuver=2, hp=50, max_hp=50)
        db.session.add(unit)
        db.session.flush()

        resp = auth_client.post(f'/military/division/{div.id}/disband')
        assert resp.status_code == 200
        # Unit should be unassigned now
        db.session.refresh(unit)
        assert unit.division_id is None
        assert db.session.get(Division, div.id) is None

    def test_disband_in_combat_rejected(self, app, auth_client, nation):
        div = Division(nation_id=nation.id, name='InCombat', in_combat=True)
        db.session.add(div)
        db.session.flush()
        resp = auth_client.post(f'/military/division/{div.id}/disband')
        assert resp.status_code == 422

    def test_mobilize_division(self, app, auth_client, nation):
        div = Division(nation_id=nation.id, name='Mob')
        db.session.add(div)
        db.session.flush()
        resp = auth_client.post(f'/military/division/{div.id}/mobilize')
        assert resp.status_code == 200
        db.session.refresh(div)
        assert div.mobilization_state == 'mobilized'

    def test_demobilize_division(self, app, auth_client, nation):
        div = Division(nation_id=nation.id, name='Demob',
                       mobilization_state='mobilized')
        db.session.add(div)
        db.session.flush()
        resp = auth_client.post(f'/military/division/{div.id}/demobilize')
        assert resp.status_code == 200
        db.session.refresh(div)
        assert div.mobilization_state == 'demobilized'

    def test_wrong_nation_division_rejected(self, app, auth_client, nation):
        resp = auth_client.post('/military/division/99999/rename',
                                data={'name': 'Hack'})
        assert resp.status_code == 422


class TestUnitRoutes:
    def test_move_unit_to_division(self, app, auth_client, nation):
        div = Division(nation_id=nation.id, name='Target')
        db.session.add(div)
        db.session.flush()
        unit = Unit(nation_id=nation.id, unit_key='infantry',
                    firepower=3, armour=1, maneuver=2, hp=50, max_hp=50)
        db.session.add(unit)
        db.session.flush()

        resp = auth_client.post(f'/military/unit/{unit.id}/move',
                                data={'division_id': str(div.id)})
        assert resp.status_code == 200
        db.session.refresh(unit)
        assert unit.division_id == div.id

    def test_move_unit_to_unassigned(self, app, auth_client, nation):
        div = Division(nation_id=nation.id, name='Source')
        db.session.add(div)
        db.session.flush()
        unit = Unit(nation_id=nation.id, division_id=div.id, unit_key='infantry',
                    firepower=3, armour=1, maneuver=2, hp=50, max_hp=50)
        db.session.add(unit)
        db.session.flush()

        resp = auth_client.post(f'/military/unit/{unit.id}/move',
                                data={'division_id': 'none'})
        assert resp.status_code == 200
        db.session.refresh(unit)
        assert unit.division_id is None

    def test_disband_unit(self, app, auth_client, nation):
        unit = Unit(nation_id=nation.id, unit_key='infantry',
                    firepower=3, armour=1, maneuver=2, hp=50, max_hp=50)
        db.session.add(unit)
        db.session.flush()
        uid = unit.id

        resp = auth_client.post(f'/military/unit/{uid}/disband')
        assert resp.status_code == 200
        assert db.session.get(Unit, uid) is None

    def test_disband_unit_reduces_gp(self, app, auth_client, nation):
        nation.military_gp = 5
        db.session.flush()
        unit = Unit(nation_id=nation.id, unit_key='infantry',
                    firepower=3, armour=1, maneuver=2, hp=50, max_hp=50)
        db.session.add(unit)
        db.session.flush()

        auth_client.post(f'/military/unit/{unit.id}/disband')
        db.session.refresh(nation)
        assert nation.military_gp == 4  # gp_value of infantry is 1

    def test_rename_unit(self, app, auth_client, nation):
        unit = Unit(nation_id=nation.id, unit_key='infantry',
                    firepower=3, armour=1, maneuver=2, hp=50, max_hp=50)
        db.session.add(unit)
        db.session.flush()

        resp = auth_client.post(f'/military/unit/{unit.id}/rename',
                                data={'name': 'Sparky'})
        assert resp.status_code == 200
        db.session.refresh(unit)
        assert unit.custom_name == 'Sparky'


class TestRecruitment:
    def test_recruitment_page_loads(self, app, auth_client):
        resp = auth_client.get('/military/recruitment')
        assert resp.status_code == 200
        assert b'Infantry' in resp.data
        assert b'Recruit' in resp.data

    def test_recruitment_page_shows_all_types(self, app, auth_client):
        resp = auth_client.get('/military/recruitment')
        data = resp.data.decode()
        assert 'M1A1 Abrahms' in data
        assert 'Railgun' in data
        assert 'F-35 Lightning II' in data
        assert 'Riot Cop' in data

    def test_recruit_unit_success(self, app, auth_client, nation):
        resp = auth_client.post('/military/recruit', data={'unit_key': 'infantry'})
        assert resp.status_code == 200
        trigger = json.loads(resp.headers.get('HX-Trigger', '{}'))
        assert trigger['showMessage']['type'] == 'success'
        assert RecruitmentQueue.query.filter_by(nation_id=nation.id).count() == 1

    def test_recruit_deducts_cost(self, app, auth_client, nation):
        before = nation.money
        auth_client.post('/military/recruit', data={'unit_key': 'infantry'})
        db.session.refresh(nation)
        assert nation.money == before - 1000  # infantry costs 1000 money

    def test_recruit_tier_gating(self, app, auth_client, nation):
        """Tier-locked units should be rejected for tier-1 nations."""
        nation.tier = 1
        db.session.flush()
        # lockheed_ac_130 is tier 8
        resp = auth_client.post('/military/recruit', data={'unit_key': 'lockheed_ac_130'})
        assert resp.status_code == 422
        trigger = json.loads(resp.headers.get('HX-Trigger', '{}'))
        assert 'Tier' in trigger['showMessage']['message']

    def test_recruit_insufficient_resources(self, app, auth_client, nation):
        nation.money = 0
        db.session.flush()
        resp = auth_client.post('/military/recruit', data={'unit_key': 'infantry'})
        assert resp.status_code == 422

    def test_recruit_queue_limit(self, app, auth_client, nation):
        now = datetime.now(timezone.utc)
        for i in range(10):
            db.session.add(RecruitmentQueue(
                nation_id=nation.id, unit_key='infantry',
                started_at=now, completes_at=now + timedelta(hours=1),
            ))
        db.session.flush()

        resp = auth_client.post('/military/recruit', data={'unit_key': 'infantry'})
        assert resp.status_code == 422
        trigger = json.loads(resp.headers.get('HX-Trigger', '{}'))
        assert 'full' in trigger['showMessage']['message'].lower()

    def test_recruit_unknown_unit(self, app, auth_client):
        resp = auth_client.post('/military/recruit', data={'unit_key': 'nonexistent'})
        assert resp.status_code == 422

    def test_cancel_recruitment(self, app, auth_client, nation):
        now = datetime.now(timezone.utc)
        entry = RecruitmentQueue(
            nation_id=nation.id, unit_key='infantry',
            started_at=now, completes_at=now + timedelta(hours=1),
        )
        db.session.add(entry)
        db.session.flush()
        eid = entry.id
        before = nation.money

        resp = auth_client.post(f'/military/recruit/{eid}/cancel')
        assert resp.status_code == 200
        assert db.session.get(RecruitmentQueue, eid) is None
        # Should get 50% refund
        db.session.refresh(nation)
        assert nation.money == before + 500  # 50% of 1000

    def test_cancel_wrong_nation_rejected(self, app, auth_client):
        resp = auth_client.post('/military/recruit/99999/cancel')
        assert resp.status_code == 422
