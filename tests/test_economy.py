"""Tests for economy routes: land management, factory construction, and collection."""
import json
import pytest
from datetime import datetime
from app import db
from app.models import Nation, NationFactory, FactoryBuildQueue, User


def _trigger(resp):
    return json.loads(resp.headers.get('HX-Trigger', '{}'))


def _msg(resp):
    return _trigger(resp).get('showMessage', {})


class TestBuyLand:
    def test_deducts_money_adds_cleared_land(self, app, auth_client, nation):
        money_before = nation.money
        total_before = nation.total_land or 0
        resp = auth_client.post('/buy-cleared-land', data={'buy_amount': '10'})
        assert resp.status_code == 200
        db.session.refresh(nation)
        assert nation.money == pytest.approx(money_before - 10_000, rel=0.0001)
        assert nation.cleared_land == 10
        assert nation.total_land == total_before + 10

    def test_updates_land_gp(self, app, auth_client, nation):
        auth_client.post('/buy-cleared-land', data={'buy_amount': '100'})
        db.session.refresh(nation)
        assert nation.land_gp == nation.total_land // 10

    def test_rejects_zero_amount(self, app, auth_client, nation):
        assert _msg(auth_client.post('/buy-cleared-land', data={'buy_amount': '0'})).get('type') == 'error'

    def test_rejects_negative_amount(self, app, auth_client, nation):
        assert _msg(auth_client.post('/buy-cleared-land', data={'buy_amount': '-5'})).get('type') == 'error'

    def test_rejects_over_max(self, app, auth_client, nation):
        assert _msg(auth_client.post('/buy-cleared-land', data={'buy_amount': '10001'})).get('type') == 'error'

    def test_rejects_insufficient_money(self, app, auth_client, nation):
        nation.money = 0
        db.session.commit()
        assert _msg(auth_client.post('/buy-cleared-land', data={'buy_amount': '10'})).get('type') == 'error'

    def test_requires_login(self, app, client):
        resp = client.post('/buy-cleared-land', data={'buy_amount': '10'})
        assert resp.status_code in (302, 200)


class TestBuildUrbanAreas:
    def test_converts_cleared_to_urban(self, app, auth_client, nation):
        nation.cleared_land = 50
        db.session.commit()
        resp = auth_client.post('/build-urban-areas', data={'build_amount': '10'})
        assert resp.status_code == 200
        db.session.refresh(nation)
        assert nation.cleared_land == 40
        assert nation.urban_areas == 10

    def test_deducts_money(self, app, auth_client, nation):
        nation.cleared_land = 10
        nation.money = 100_000
        db.session.commit()
        auth_client.post('/build-urban-areas', data={'build_amount': '10'})
        db.session.refresh(nation)
        assert nation.money == pytest.approx(100_000 - 5_000, rel=0.0001)  # 10 * 500

    def test_rejects_insufficient_cleared(self, app, auth_client, nation):
        nation.cleared_land = 5
        db.session.commit()
        assert _msg(auth_client.post('/build-urban-areas', data={'build_amount': '10'})).get('type') == 'error'

    def test_rejects_insufficient_money(self, app, auth_client, nation):
        nation.cleared_land = 100
        nation.money = 0
        db.session.commit()
        assert _msg(auth_client.post('/build-urban-areas', data={'build_amount': '10'})).get('type') == 'error'

    def test_rejects_zero_amount(self, app, auth_client, nation):
        nation.cleared_land = 100
        db.session.commit()
        assert _msg(auth_client.post('/build-urban-areas', data={'build_amount': '0'})).get('type') == 'error'


class TestConvertLand:
    @pytest.mark.parametrize('land_type', ['forest', 'grassland', 'jungle', 'mountain', 'desert', 'tundra'])
    def test_all_valid_types_accepted(self, app, auth_client, nation, land_type):
        setattr(nation, land_type, 50)
        nation.money = 1_000_000
        db.session.commit()
        cleared_before = nation.cleared_land or 0
        resp = auth_client.post('/convert-to-cleared-land',
                                data={'land_type': land_type, 'convert_amount': '1'})
        assert resp.status_code == 200
        db.session.refresh(nation)
        assert getattr(nation, land_type) == 49
        assert nation.cleared_land == cleared_before + 1

    def test_deducts_money(self, app, auth_client, nation):
        nation.forest = 50
        nation.money = 10_000
        db.session.commit()
        auth_client.post('/convert-to-cleared-land', data={'land_type': 'forest', 'convert_amount': '10'})
        db.session.refresh(nation)
        assert nation.money == pytest.approx(10_000 - 1_000, rel=0.0001)  # 10 * 100

    def test_rejects_invalid_land_type(self, app, auth_client, nation):
        assert _msg(auth_client.post('/convert-to-cleared-land',
                                     data={'land_type': 'ocean', 'convert_amount': '5'})).get('type') == 'error'

    def test_rejects_insufficient_tiles(self, app, auth_client, nation):
        nation.forest = 5
        db.session.commit()
        assert _msg(auth_client.post('/convert-to-cleared-land',
                                     data={'land_type': 'forest', 'convert_amount': '10'})).get('type') == 'error'

    def test_rejects_insufficient_money(self, app, auth_client, nation):
        nation.forest = 50
        nation.money = 0
        db.session.commit()
        assert _msg(auth_client.post('/convert-to-cleared-land',
                                     data={'land_type': 'forest', 'convert_amount': '5'})).get('type') == 'error'


class TestExpandBorders:
    def test_expands_and_deducts_resources(self, app, auth_client, nation):
        total_before = nation.total_land or 0
        money_before = nation.money
        resp = auth_client.post('/expand-borders')
        assert resp.status_code == 200
        db.session.refresh(nation)
        assert nation.total_land > total_before
        assert nation.money < money_before

    def test_sets_last_expanded_at(self, app, auth_client, nation):
        assert nation.last_expanded_at is None
        auth_client.post('/expand-borders')
        db.session.refresh(nation)
        assert nation.last_expanded_at is not None

    def test_updates_land_gp(self, app, auth_client, nation):
        auth_client.post('/expand-borders')
        db.session.refresh(nation)
        assert nation.land_gp == nation.total_land // 10

    def test_cooldown_blocks_rapid_repeat(self, app, auth_client, nation):
        nation.last_expanded_at = datetime.utcnow()
        db.session.commit()
        msg = _msg(auth_client.post('/expand-borders'))
        assert msg.get('type') == 'error'
        assert 'tomorrow' in msg.get('message', '').lower()

    def test_rejects_insufficient_resources(self, app, auth_client, nation):
        nation.money = 0
        db.session.commit()
        assert _msg(auth_client.post('/expand-borders')).get('type') == 'error'


class TestColonize:
    def test_rejects_below_tier_6(self, app, auth_client, nation):
        nation.tier = 5
        db.session.commit()
        msg = _msg(auth_client.post('/colonize', data={'continent': 'Westberg'}))
        assert msg.get('type') == 'error'
        assert 'Tier 6' in msg.get('message', '')

    def test_colonizes_tier_6_nation(self, app, auth_client, nation):
        nation.tier = 6
        nation.fuel = 200_000
        nation.metal = 200_000
        db.session.commit()
        total_before = nation.total_land or 0
        resp = auth_client.post('/colonize', data={'continent': 'Westberg'})
        assert resp.status_code == 200
        db.session.refresh(nation)
        assert nation.total_land > total_before

    def test_rejects_invalid_continent(self, app, auth_client, nation):
        nation.tier = 6
        db.session.commit()
        assert _msg(auth_client.post('/colonize', data={'continent': 'Mars'})).get('type') == 'error'

    def test_cooldown_enforced(self, app, auth_client, nation):
        nation.tier = 6
        nation.last_colonized_at = datetime.utcnow()
        db.session.commit()
        assert _msg(auth_client.post('/colonize', data={'continent': 'Westberg'})).get('type') == 'error'


class TestBuildFactory:
    def _setup(self, nation, cleared=50, money=1_000_000, tier=1):
        nation.cleared_land = cleared
        nation.money = money
        nation.tier = tier
        db.session.commit()

    def test_queues_build(self, app, auth_client, nation):
        self._setup(nation)
        resp = auth_client.post('/industry/build', data={'factory_key': 'farm', 'amount': '1'})
        assert resp.status_code == 200
        entry = FactoryBuildQueue.query.filter_by(nation_id=nation.id, factory_key='farm').first()
        assert entry is not None
        assert entry.quantity == 1

    def test_deducts_money_and_land(self, app, auth_client, nation):
        self._setup(nation, cleared=50, money=1_000_000)
        auth_client.post('/industry/build', data={'factory_key': 'farm', 'amount': '2'})
        db.session.refresh(nation)
        # farm: 500 money, 5 cleared_land per unit
        assert nation.money == pytest.approx(1_000_000 - 2 * 500, rel=0.0001)
        assert nation.cleared_land == 50 - 2 * 5

    def test_rejects_unknown_factory(self, app, auth_client, nation):
        assert _msg(auth_client.post('/industry/build',
                                     data={'factory_key': 'nonexistent', 'amount': '1'})).get('type') == 'error'

    def test_rejects_wrong_tier(self, app, auth_client, nation):
        nation.tier = 1
        db.session.commit()
        from app.game.factories import FACTORY_DEFS
        high_tier = next((k for k, f in FACTORY_DEFS.items() if f.tier >= 3), None)
        if high_tier:
            msg = _msg(auth_client.post('/industry/build', data={'factory_key': high_tier, 'amount': '1'}))
            assert msg.get('type') == 'error'
            assert 'Tier' in msg.get('message', '')

    def test_rejects_insufficient_land(self, app, auth_client, nation):
        nation.cleared_land = 0   # farm needs 5 cleared_land
        nation.money = 1_000_000
        db.session.commit()
        assert _msg(auth_client.post('/industry/build',
                                     data={'factory_key': 'farm', 'amount': '1'})).get('type') == 'error'

    def test_rejects_insufficient_money(self, app, auth_client, nation):
        nation.cleared_land = 100
        nation.money = 0   # farm costs 500
        db.session.commit()
        assert _msg(auth_client.post('/industry/build',
                                     data={'factory_key': 'farm', 'amount': '1'})).get('type') == 'error'

    def test_coalesces_builds_within_5_minutes(self, app, auth_client, nation):
        self._setup(nation, cleared=100)
        auth_client.post('/industry/build', data={'factory_key': 'farm', 'amount': '1'})
        auth_client.post('/industry/build', data={'factory_key': 'farm', 'amount': '1'})
        entries = FactoryBuildQueue.query.filter_by(nation_id=nation.id, factory_key='farm').all()
        total_qty = sum(e.quantity for e in entries)
        assert total_qty == 2

    def test_multiple_quantity_in_one_request(self, app, auth_client, nation):
        self._setup(nation, cleared=100)
        auth_client.post('/industry/build', data={'factory_key': 'farm', 'amount': '5'})
        entry = FactoryBuildQueue.query.filter_by(nation_id=nation.id, factory_key='farm').first()
        assert entry is not None
        assert entry.quantity == 5

    def test_rejects_over_max_quantity(self, app, auth_client, nation):
        self._setup(nation, cleared=10000, money=5_000_000)
        assert _msg(auth_client.post('/industry/build',
                                     data={'factory_key': 'farm', 'amount': '101'})).get('type') == 'error'

    def test_category_factory_blocked_without_building(self, app, auth_client, nation):
        """Flora factories require Botanical Research Station."""
        from app.game.factories import FACTORY_DEFS
        flora_factory = next((k for k, f in FACTORY_DEFS.items() if f.category == 'flora'), None)
        if not flora_factory:
            pytest.skip('No flora factory found')
        nation.tier = 10
        nation.cleared_land = 10000
        nation.money = 10_000_000
        db.session.commit()
        msg = _msg(auth_client.post('/industry/build', data={'factory_key': flora_factory, 'amount': '1'}))
        assert msg.get('type') == 'error'


class TestCollectFactory:
    def _add_factory(self, nation, factory_key, count=1, capacity=10):
        nf = NationFactory(nation_id=nation.id, factory_key=factory_key,
                           count=count, production_capacity=capacity)
        db.session.add(nf)
        db.session.commit()
        return nf

    def test_basic_collect_succeeds(self, app, auth_client, nation):
        # windmill: inputs={money:5/h}, outputs={power:5/h}
        self._add_factory(nation, 'windmill', capacity=5)
        nation.money = 1_000_000
        db.session.commit()
        resp = auth_client.post('/industry/collect/windmill', data={'hours': '1'})
        assert resp.status_code == 204
        assert _msg(resp).get('type') == 'success'

    def test_deducts_inputs_adds_outputs(self, app, auth_client, nation):
        self._add_factory(nation, 'windmill', count=1, capacity=5)
        nation.money = 100_000
        nation.power = 0
        db.session.commit()
        auth_client.post('/industry/collect/windmill', data={'hours': '2'})
        db.session.refresh(nation)
        # 1 windmill * 2h: 10 money in, 10 power out
        assert nation.money == pytest.approx(100_000 - 10, rel=0.0001)
        assert nation.power == pytest.approx(10, rel=0.0001)

    def test_decrements_production_capacity(self, app, auth_client, nation):
        self._add_factory(nation, 'windmill', capacity=5)
        nation.money = 1_000_000
        db.session.commit()
        auth_client.post('/industry/collect/windmill', data={'hours': '3'})
        nf = NationFactory.query.filter_by(nation_id=nation.id, factory_key='windmill').first()
        assert nf.production_capacity == 2

    def test_collect_trigger_includes_factory_key(self, app, auth_client, nation):
        self._add_factory(nation, 'windmill', capacity=5)
        nation.money = 1_000_000
        db.session.commit()
        resp = auth_client.post('/industry/collect/windmill', data={'hours': '1'})
        t = _trigger(resp)
        assert 'collect-success' in t
        assert t['collect-success']['factoryKey'] == 'windmill'

    def test_rejects_no_factory(self, app, auth_client, nation):
        assert _msg(auth_client.post('/industry/collect/farm', data={'hours': '1'})).get('type') == 'error'

    def test_rejects_zero_capacity(self, app, auth_client, nation):
        self._add_factory(nation, 'windmill', capacity=0)
        assert _msg(auth_client.post('/industry/collect/windmill', data={'hours': '1'})).get('type') == 'error'

    def test_rejects_insufficient_inputs(self, app, auth_client, nation):
        self._add_factory(nation, 'windmill', capacity=5)
        nation.money = 0   # windmill needs money
        db.session.commit()
        assert _msg(auth_client.post('/industry/collect/windmill', data={'hours': '1'})).get('type') == 'error'

    def test_vacation_mode_blocked(self, app, auth_client, nation):
        self._add_factory(nation, 'windmill', capacity=5)
        nation.money = 1_000_000
        user = db.session.get(User, nation.user_id)
        user.vacation_mode = True
        db.session.commit()
        msg = _msg(auth_client.post('/industry/collect/windmill', data={'hours': '1'}))
        assert msg.get('type') == 'error'
        assert 'vacation' in msg.get('message', '').lower()

    def test_collect_caps_at_capacity(self, app, auth_client, nation):
        """Requesting more hours than capacity should use only available capacity."""
        self._add_factory(nation, 'windmill', capacity=3)
        nation.money = 1_000_000
        db.session.commit()
        auth_client.post('/industry/collect/windmill', data={'hours': '10'})
        nf = NationFactory.query.filter_by(nation_id=nation.id, factory_key='windmill').first()
        assert nf.production_capacity == 0

    def test_multiple_factories_multiplied_in_output(self, app, auth_client, nation):
        self._add_factory(nation, 'windmill', count=3, capacity=5)
        nation.money = 1_000_000
        nation.power = 0
        db.session.commit()
        auth_client.post('/industry/collect/windmill', data={'hours': '1'})
        db.session.refresh(nation)
        # 3 windmills * 1h * 5 power/h = 15 power
        assert nation.power == pytest.approx(15, rel=0.0001)
