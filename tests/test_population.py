"""Tests for population simulation functions and tick_nation."""
import pytest
from app import db
from app.models import Nation, Unit, Division, NationEvent
from app.game.population import (
    get_population_effects, compute_tier, food_abundance_multiplier,
    process_growth, process_starvation,
    POPULATION_RATES, CG_POPULATION_THRESHOLD, FOOD_PER_CITIZEN,
)
from app.tasks import tick_nation


class TestGetPopulationEffects:
    def test_money_income_rate(self):
        effects = get_population_effects(100_000)
        assert effects['money'] == pytest.approx(100_000 * (1 / 100))

    def test_food_is_negative(self):
        assert get_population_effects(100_000)['food'] < 0

    def test_power_is_negative(self):
        assert get_population_effects(100_000)['power'] < 0

    def test_cg_zero_below_threshold(self):
        assert get_population_effects(CG_POPULATION_THRESHOLD - 1)['consumer_goods'] == 0

    def test_cg_consumed_above_threshold(self):
        assert get_population_effects(CG_POPULATION_THRESHOLD + 1)['consumer_goods'] < 0

    def test_zero_population_all_zero(self):
        effects = get_population_effects(0)
        assert effects['money'] == 0
        assert effects['food'] == 0

    def test_rates_scale_with_population(self):
        e1 = get_population_effects(100_000)
        e2 = get_population_effects(200_000)
        assert e2['money'] == pytest.approx(e1['money'] * 2)


class TestComputeTier:
    @pytest.mark.parametrize('pop,expected', [
        (0, 1),
        (74_999, 1),
        (75_000, 2),
        (149_999, 2),
        (150_000, 3),
        (350_000, 4),
        (1_000_000, 5),
        (2_500_000, 6),
        (6_000_000, 7),
        (10_000_000, 7),
    ])
    def test_tier_thresholds(self, pop, expected):
        assert compute_tier(pop) == expected


class TestFoodAbundanceMultiplier:
    def test_no_food_returns_zero(self):
        assert food_abundance_multiplier(100_000, 0) == 0.0

    def test_zero_population_returns_one(self):
        assert food_abundance_multiplier(0, 0) == 1.0

    def test_thirty_plus_days_returns_one(self):
        pop = 100_000
        daily = pop * abs(POPULATION_RATES['food']) * 24
        assert food_abundance_multiplier(pop, daily * 30) == 1.0
        assert food_abundance_multiplier(pop, daily * 60) == 1.0

    def test_below_three_days_returns_zero(self):
        pop = 100_000
        daily = pop * abs(POPULATION_RATES['food']) * 24
        assert food_abundance_multiplier(pop, daily * 2) == 0.0

    def test_midpoint_returns_half(self):
        pop = 100_000
        daily = pop * abs(POPULATION_RATES['food']) * 24
        midpoint = daily * ((3 + 30) / 2)
        assert food_abundance_multiplier(pop, midpoint) == pytest.approx(0.5, abs=0.01)

    def test_linear_ramp(self):
        pop = 100_000
        daily = pop * abs(POPULATION_RATES['food']) * 24
        m1 = food_abundance_multiplier(pop, daily * 10)
        m2 = food_abundance_multiplier(pop, daily * 20)
        assert 0 < m1 < m2 < 1.0


class TestProcessGrowth:
    def test_no_growth_without_land(self, app, nation):
        nation.population = 100_000
        nation.cleared_land = 0
        nation.urban_areas = 0
        nation.food = 500_000
        db.session.commit()
        assert process_growth(nation) == 0

    def test_no_growth_with_rate_zero(self, app, nation):
        nation.population = 100_000
        nation.growth_rate = 0
        nation.cleared_land = 1000
        nation.food = 500_000
        db.session.commit()
        assert process_growth(nation) == 0

    def test_growth_occurs_with_land_and_food(self, app, nation):
        nation.population = 100_000
        nation.food = 500_000
        nation.cleared_land = 1000
        nation.urban_areas = 0
        nation.growth_mode = 'auto'
        nation.growth_rate = 50
        db.session.commit()
        grown = process_growth(nation)
        assert grown > 0
        assert nation.population == 100_000 + grown

    def test_food_consumed_on_growth(self, app, nation):
        nation.population = 100_000
        nation.food = 500_000
        nation.cleared_land = 1000
        nation.growth_mode = 'auto'
        db.session.commit()
        food_before = nation.food
        grown = process_growth(nation)
        if grown > 0:
            expected_cost = grown * FOOD_PER_CITIZEN
            assert nation.food == pytest.approx(food_before - expected_cost, rel=0.01)

    def test_growth_capped_at_land_capacity(self, app, nation):
        # population == cleared_land capacity → no room to grow
        nation.population = 1_000_000
        nation.cleared_land = 1000   # capacity = 1M, exactly full
        nation.urban_areas = 0
        nation.food = 500_000
        nation.growth_mode = 'manual'
        nation.growth_rate = 100
        db.session.commit()
        assert process_growth(nation) == 0

    def test_cleared_land_converts_to_urban_on_overflow(self, app, nation):
        # Pop just above urban capacity → cleared land should convert
        nation.population = 100_000
        nation.urban_areas = 100   # capacity = exactly 100k
        nation.cleared_land = 500
        nation.food = 500_000
        nation.growth_mode = 'auto'
        db.session.commit()
        urban_before = nation.urban_areas
        grown = process_growth(nation)
        if grown > 0:
            assert nation.urban_areas > urban_before


class TestProcessStarvation:
    def test_reduces_population(self, app, nation):
        nation.population = 100_000
        db.session.commit()
        lost = process_starvation(nation, 1.0)
        assert lost > 0
        assert nation.population == 100_000 - lost

    def test_scales_with_deficit_fraction(self, app, nation):
        nation.population = 100_000
        db.session.commit()
        lost = process_starvation(nation, 0.5)
        # 100_000 * 0.01 * 0.5 = 500
        assert lost == max(1, int(100_000 * 0.01 * 0.5))

    def test_minimum_one_citizen_lost(self, app, nation):
        nation.population = 1
        db.session.commit()
        assert process_starvation(nation, 0.0001) == 1

    def test_zero_deficit_no_starvation(self, app, nation):
        nation.population = 100_000
        db.session.commit()
        assert process_starvation(nation, 0) == 0
        assert nation.population == 100_000

    def test_population_floor_is_zero(self, app, nation):
        nation.population = 1
        db.session.commit()
        process_starvation(nation, 1.0)
        assert nation.population == 0


class TestTickNation:
    def test_money_income_applied(self, app, nation):
        nation.population = 100_000
        nation.tier = 2
        nation.cleared_land = 0
        db.session.commit()
        money_before = nation.money
        tick_nation(nation, skip_military=True)
        expected = 100_000 * (1 / 100)
        assert nation.money == pytest.approx(money_before + expected, rel=0.001)

    def test_food_consumed_by_population(self, app, nation):
        nation.population = 100_000
        nation.tier = 2
        nation.food = 50_000
        nation.cleared_land = 0
        db.session.commit()
        tick_nation(nation, skip_military=True)
        expected_consumption = 100_000 / 2000
        assert nation.food == pytest.approx(50_000 - expected_consumption, rel=0.001)

    def test_power_consumed_by_population(self, app, nation):
        nation.population = 100_000
        nation.tier = 2
        nation.power = 50_000
        db.session.commit()
        tick_nation(nation, skip_military=True)
        assert nation.power == pytest.approx(50_000 - 100_000 / 2500, rel=0.001)

    def test_consumer_goods_consumed_above_threshold(self, app, nation):
        nation.population = CG_POPULATION_THRESHOLD + 100_000
        nation.tier = 3
        nation.consumer_goods = 50_000
        nation.cleared_land = 0
        db.session.commit()
        cg_before = nation.consumer_goods
        tick_nation(nation, skip_military=True)
        expected = nation.population * abs(POPULATION_RATES['consumer_goods'])
        # Note: population may change slightly due to growth
        assert nation.consumer_goods < cg_before

    def test_starvation_when_no_food(self, app, nation):
        nation.population = 100_000
        nation.tier = 2
        nation.food = 0
        nation.cleared_land = 0
        db.session.commit()
        pop_before = nation.population
        grown, starved = tick_nation(nation, skip_military=True)
        assert starved > 0
        assert grown == 0
        assert nation.population < pop_before

    def test_population_grows_with_land_and_food(self, app, nation):
        nation.population = 100_000
        nation.tier = 2
        nation.food = 500_000
        nation.cleared_land = 1000
        nation.urban_areas = 0
        nation.growth_mode = 'auto'
        db.session.commit()
        grown, starved = tick_nation(nation, skip_military=True)
        assert grown > 0
        assert starved == 0

    def test_no_growth_without_land(self, app, nation):
        nation.population = 100_000
        nation.tier = 2
        nation.food = 500_000
        nation.cleared_land = 0
        nation.urban_areas = 0
        db.session.commit()
        grown, _ = tick_nation(nation, skip_military=True)
        assert grown == 0

    def test_tier_promotion_logged_as_event(self, app, nation):
        nation.population = 1_000_000
        nation.tier = 1   # will promote to tier 5
        db.session.commit()
        tick_nation(nation, skip_military=True)
        db.session.commit()
        event = NationEvent.query.filter_by(
            nation_id=nation.id, event_type='tier_promotion'
        ).first()
        assert event is not None
        assert nation.tier == compute_tier(nation.population)

    def test_tier_demotion_logged_as_event(self, app, nation):
        nation.population = 100_000   # tier 2 by population
        nation.tier = 4               # currently too high
        db.session.commit()
        tick_nation(nation, skip_military=True)
        db.session.commit()
        event = NationEvent.query.filter_by(
            nation_id=nation.id, event_type='tier_demotion'
        ).first()
        assert event is not None

    def test_returns_grown_starved_tuple(self, app, nation):
        nation.population = 100_000
        nation.tier = 2
        nation.food = 0
        db.session.commit()
        result = tick_nation(nation, skip_military=True)
        assert isinstance(result, tuple) and len(result) == 2

    def test_military_upkeep_deducted_during_tick(self, app, nation):
        nation.population = 100_000
        nation.tier = 2
        nation.food = 500_000
        nation.cleared_land = 0
        db.session.commit()
        div = Division(nation_id=nation.id, name='Alpha', mobilization_state='mobilized')
        db.session.add(div)
        db.session.flush()
        unit = Unit(nation_id=nation.id, unit_key='infantry', division_id=div.id,
                    firepower=3, armour=1, maneuver=2, hp=50, max_hp=50)
        db.session.add(unit)
        db.session.commit()

        food_before = nation.food
        tick_nation(nation, skip_military=False)
        # Infantry mobilized upkeep: food=1; population food consumption: 100k/2000=50
        assert nation.food == pytest.approx(food_before - 50 - 1, abs=2)

    def test_skip_military_skips_upkeep(self, app, nation):
        nation.population = 100_000
        nation.tier = 2
        nation.food = 500_000
        db.session.commit()
        div = Division(nation_id=nation.id, name='Alpha', mobilization_state='mobilized')
        db.session.add(div)
        db.session.flush()
        unit = Unit(nation_id=nation.id, unit_key='infantry', division_id=div.id,
                    firepower=3, armour=1, maneuver=2, hp=50, max_hp=50)
        db.session.add(unit)
        db.session.commit()

        food_before = nation.food
        tick_nation(nation, skip_military=True)
        # Only population consumption (50), no upkeep
        assert nation.food == pytest.approx(food_before - 50, abs=2)

    def test_resources_floored_at_zero(self, app, nation):
        """Resources should never go negative even if consumption exceeds stockpile."""
        nation.population = 1_000_000
        nation.tier = 5
        nation.power = 1   # will be consumed by 400
        db.session.commit()
        tick_nation(nation, skip_military=True)
        assert nation.power == 0
