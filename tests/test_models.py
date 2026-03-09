"""Tests for military models — Division, Unit, RecruitmentQueue, Battle, CombatReport."""
from datetime import datetime, timezone, timedelta
from app.models import Division, Unit, RecruitmentQueue, Battle, CombatReport, Nation
from app import db


class TestDivision:
    def test_create_division(self, app, nation):
        div = Division(nation_id=nation.id, name='Alpha')
        db.session.add(div)
        db.session.commit()
        assert div.id is not None
        assert div.name == 'Alpha'
        assert div.mobilization_state == 'demobilized'
        assert div.in_combat is False

    def test_division_nation_relationship(self, app, nation):
        div = Division(nation_id=nation.id, name='Bravo')
        db.session.add(div)
        db.session.commit()
        assert nation.divisions.count() >= 1

    def test_division_units_relationship(self, app, nation):
        div = Division(nation_id=nation.id, name='Charlie')
        db.session.add(div)
        db.session.commit()
        u = Unit(nation_id=nation.id, division_id=div.id, unit_key='infantry',
                 firepower=3, armour=1, maneuver=2, hp=50, max_hp=50)
        db.session.add(u)
        db.session.commit()
        assert div.units.count() == 1


class TestUnit:
    def test_create_unit(self, app, nation):
        u = Unit(nation_id=nation.id, unit_key='infantry',
                 firepower=3, armour=1, maneuver=2, hp=50, max_hp=50)
        db.session.add(u)
        db.session.commit()
        assert u.id is not None
        assert u.level == 1
        assert u.xp == 0
        assert u.division_id is None

    def test_unit_default_custom_name(self, app, nation):
        u = Unit(nation_id=nation.id, unit_key='infantry',
                 firepower=3, armour=1, maneuver=2, hp=50, max_hp=50)
        db.session.add(u)
        db.session.commit()
        assert u.custom_name == ''

    def test_unassigned_unit(self, app, nation):
        u = Unit(nation_id=nation.id, unit_key='m1a1_abrahms',
                 firepower=3, armour=4, maneuver=2, hp=130, max_hp=130)
        db.session.add(u)
        db.session.commit()
        unassigned = Unit.query.filter_by(nation_id=nation.id, division_id=None).all()
        assert len(unassigned) >= 1


class TestRecruitmentQueue:
    def test_create_queue_entry(self, app, nation):
        now = datetime.now(timezone.utc)
        entry = RecruitmentQueue(
            nation_id=nation.id, unit_key='infantry',
            started_at=now, completes_at=now + timedelta(hours=1),
        )
        db.session.add(entry)
        db.session.commit()
        assert entry.id is not None
        assert entry.completes_at > entry.started_at

    def test_queue_query_ready(self, app, nation):
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        entry = RecruitmentQueue(
            nation_id=nation.id, unit_key='infantry',
            started_at=past - timedelta(hours=1), completes_at=past,
        )
        db.session.add(entry)
        db.session.commit()
        ready = RecruitmentQueue.query.filter(
            RecruitmentQueue.completes_at <= datetime.now(timezone.utc)
        ).all()
        assert len(ready) >= 1


class TestBattle:
    def test_create_battle(self, app, nation):
        from app.models import User
        u2 = User(username='defender', email='def@test.com')
        u2.set_password('password')
        db.session.add(u2)
        db.session.flush()
        n2 = Nation(user_id=u2.id, name='DefenderNation', continent='Westberg')
        db.session.add(n2)
        db.session.flush()

        div_a = Division(nation_id=nation.id, name='Attackers')
        div_d = Division(nation_id=n2.id, name='Defenders')
        db.session.add_all([div_a, div_d])
        db.session.flush()

        battle = Battle(
            attacker_division_id=div_a.id, defender_division_id=div_d.id,
            attacker_nation_id=nation.id, defender_nation_id=n2.id,
        )
        db.session.add(battle)
        db.session.commit()

        assert battle.id is not None
        assert battle.status == 'active'
        assert battle.winner is None


class TestCombatReport:
    def test_create_report(self, app, nation):
        from app.models import User
        u2 = User(username='defender2', email='def2@test.com')
        u2.set_password('password')
        db.session.add(u2)
        db.session.flush()
        n2 = Nation(user_id=u2.id, name='DefNation2', continent='Westberg')
        db.session.add(n2)
        db.session.flush()

        div_a = Division(nation_id=nation.id, name='A')
        div_d = Division(nation_id=n2.id, name='D')
        db.session.add_all([div_a, div_d])
        db.session.flush()

        battle = Battle(
            attacker_division_id=div_a.id, defender_division_id=div_d.id,
            attacker_nation_id=nation.id, defender_nation_id=n2.id,
        )
        db.session.add(battle)
        db.session.flush()

        report = CombatReport(battle_id=battle.id, message='Test hit for 10 damage!')
        db.session.add(report)
        db.session.commit()

        assert report.id is not None
        assert battle.reports.count() == 1
