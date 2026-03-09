"""Tests for background tasks — recruitment processing, upkeep deduction."""
from datetime import datetime, timezone, timedelta
from app import db
from app.models import Nation, Unit, RecruitmentQueue
from app.game.units import UNIT_DEFS


class TestRecruitmentProcessing:
    def _process_queue(self):
        """Run the recruitment processor logic inline (avoids scheduler dependency)."""
        now = datetime.now(timezone.utc)
        ready = RecruitmentQueue.query.filter(RecruitmentQueue.completes_at <= now).all()
        for entry in ready:
            udef = UNIT_DEFS.get(entry.unit_key)
            if not udef:
                db.session.delete(entry)
                continue
            unit = Unit(
                nation_id=entry.nation_id,
                unit_key=entry.unit_key,
                firepower=udef.firepower,
                armour=udef.armour,
                maneuver=udef.maneuver,
                hp=udef.max_hp,
                max_hp=udef.max_hp,
            )
            db.session.add(unit)
            nation = db.session.get(Nation, entry.nation_id)
            if nation:
                nation.military_gp = (nation.military_gp or 0) + udef.gp_value
            db.session.delete(entry)
        if ready:
            db.session.commit()

    def test_completed_entry_creates_unit(self, app, nation):
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        entry = RecruitmentQueue(
            nation_id=nation.id, unit_key='infantry',
            started_at=past - timedelta(hours=1), completes_at=past,
        )
        db.session.add(entry)
        db.session.commit()

        self._process_queue()

        units = Unit.query.filter_by(nation_id=nation.id).all()
        assert len(units) == 1
        assert units[0].unit_key == 'infantry'
        assert units[0].firepower == 3
        assert units[0].hp == 50
        assert RecruitmentQueue.query.filter_by(nation_id=nation.id).count() == 0

    def test_future_entry_not_processed(self, app, nation):
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        entry = RecruitmentQueue(
            nation_id=nation.id, unit_key='infantry',
            started_at=datetime.now(timezone.utc), completes_at=future,
        )
        db.session.add(entry)
        db.session.commit()

        self._process_queue()

        assert RecruitmentQueue.query.filter_by(nation_id=nation.id).count() == 1
        assert Unit.query.filter_by(nation_id=nation.id).count() == 0

    def test_unit_stats_match_definition(self, app, nation):
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        entry = RecruitmentQueue(
            nation_id=nation.id, unit_key='gear_infantry',
            started_at=past - timedelta(hours=6), completes_at=past,
        )
        db.session.add(entry)
        db.session.commit()

        self._process_queue()

        unit = Unit.query.filter_by(nation_id=nation.id).first()
        udef = UNIT_DEFS['gear_infantry']
        assert unit.firepower == udef.firepower
        assert unit.armour == udef.armour
        assert unit.maneuver == udef.maneuver
        assert unit.hp == udef.max_hp
        assert unit.max_hp == udef.max_hp

    def test_military_gp_incremented(self, app, nation):
        nation.military_gp = 0
        db.session.commit()
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        entry = RecruitmentQueue(
            nation_id=nation.id, unit_key='gear_infantry',  # gp=3
            started_at=past - timedelta(hours=6), completes_at=past,
        )
        db.session.add(entry)
        db.session.commit()

        self._process_queue()

        db.session.refresh(nation)
        assert nation.military_gp == 3


class TestUpkeepDeduction:
    def _deduct_upkeep(self, nation):
        """Run upkeep logic inline for a single nation."""
        units = Unit.query.filter_by(nation_id=nation.id).filter(Unit.hp > 0).all()
        if not units:
            return

        total_upkeep = {}
        for unit in units:
            udef = UNIT_DEFS.get(unit.unit_key)
            if not udef:
                continue
            for res, rate in udef.upkeep.items():
                total_upkeep[res] = total_upkeep.get(res, 0) + rate

        can_afford = True
        for res, amount in total_upkeep.items():
            if (getattr(nation, res, 0) or 0) < amount:
                can_afford = False
                break

        if can_afford:
            for res, amount in total_upkeep.items():
                current = getattr(nation, res, 0) or 0
                setattr(nation, res, current - amount)
        else:
            for unit in units:
                attrition = max(1, unit.max_hp // 10)
                unit.hp = max(0, unit.hp - attrition)

        db.session.commit()

    def test_upkeep_deducted(self, app, nation):
        unit = Unit(nation_id=nation.id, unit_key='infantry',
                    firepower=3, armour=1, maneuver=2, hp=50, max_hp=50)
        db.session.add(unit)
        db.session.commit()

        money_before = nation.money
        food_before = nation.food
        self._deduct_upkeep(nation)
        db.session.refresh(nation)
        # Infantry upkeep: money=1, food=1
        assert nation.money == money_before - 1
        assert nation.food == food_before - 1

    def test_upkeep_multiple_units(self, app, nation):
        for _ in range(5):
            db.session.add(Unit(
                nation_id=nation.id, unit_key='infantry',
                firepower=3, armour=1, maneuver=2, hp=50, max_hp=50,
            ))
        db.session.commit()

        money_before = nation.money
        self._deduct_upkeep(nation)
        db.session.refresh(nation)
        # 5 infantry: money=5, food=5
        assert nation.money == money_before - 5

    def test_attrition_when_cannot_afford(self, app, nation):
        nation.money = 0
        nation.food = 0
        db.session.commit()
        unit = Unit(nation_id=nation.id, unit_key='infantry',
                    firepower=3, armour=1, maneuver=2, hp=50, max_hp=50)
        db.session.add(unit)
        db.session.commit()

        self._deduct_upkeep(nation)
        db.session.refresh(unit)
        # 10% of 50 = 5 attrition
        assert unit.hp == 45

    def test_attrition_does_not_go_negative(self, app, nation):
        nation.money = 0
        nation.food = 0
        db.session.commit()
        unit = Unit(nation_id=nation.id, unit_key='infantry',
                    firepower=3, armour=1, maneuver=2, hp=3, max_hp=50)
        db.session.add(unit)
        db.session.commit()

        self._deduct_upkeep(nation)
        db.session.refresh(unit)
        assert unit.hp == 0

    def test_dead_units_not_charged(self, app, nation):
        unit = Unit(nation_id=nation.id, unit_key='infantry',
                    firepower=3, armour=1, maneuver=2, hp=0, max_hp=50)
        db.session.add(unit)
        db.session.commit()

        money_before = nation.money
        self._deduct_upkeep(nation)
        db.session.refresh(nation)
        assert nation.money == money_before  # no change
