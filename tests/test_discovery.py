"""Tests for territory expansion and resource discovery engine."""
import pytest
from app.game.discovery import (
    roll_expansion, roll_colonization,
    LAND_WEIGHTS, RESOURCE_WEIGHTS,
    _weighted_distribute,
)

VALID_LAND_TYPES = frozenset(
    set(LAND_WEIGHTS['Westberg'])
    | set(LAND_WEIGHTS['Zaheria'])
    | set(LAND_WEIGHTS['Tind'])
)
ALL_CONTINENTS = list(LAND_WEIGHTS)


class TestWeightedDistribute:
    def test_proportional_split(self):
        result = _weighted_distribute({'a': 75, 'b': 25}, 1000)
        assert result['a'] == pytest.approx(750, abs=1)
        assert result['b'] == pytest.approx(250, abs=1)

    def test_total_not_exceeded(self):
        result = _weighted_distribute({'a': 50, 'b': 50}, 1000)
        assert sum(result.values()) <= 1000

    def test_zero_weight_key_excluded(self):
        result = _weighted_distribute({'a': 100, 'b': 0}, 100)
        assert 'b' not in result

    def test_empty_weights_returns_empty(self):
        assert _weighted_distribute({}, 100) == {}

    def test_total_zero_returns_empty_or_zeros(self):
        result = _weighted_distribute({'a': 50, 'b': 50}, 0)
        assert sum(result.values()) == 0


class TestRollExpansion:
    def test_returns_three_tuple(self):
        new_land, discovered, total_gained = roll_expansion('Westberg', 100_000)
        assert isinstance(new_land, dict)
        assert isinstance(discovered, dict)
        assert isinstance(total_gained, int)

    def test_total_gained_equals_sum_of_land(self):
        for _ in range(10):
            new_land, _, total_gained = roll_expansion('Westberg', 100_000)
            assert total_gained == sum(new_land.values())

    def test_land_keys_are_valid_types(self):
        for _ in range(10):
            new_land, _, _ = roll_expansion('Westberg', 100_000)
            for key in new_land:
                assert key in VALID_LAND_TYPES, f"Unexpected land type: {key}"

    def test_all_values_non_negative(self):
        for _ in range(10):
            new_land, discovered, _ = roll_expansion('Westberg', 100_000)
            assert all(v >= 0 for v in new_land.values())
            assert all(v >= 0 for v in discovered.values())

    def test_larger_population_yields_more_land(self):
        small = [roll_expansion('Westberg', 1_000)[2] for _ in range(20)]
        large = [roll_expansion('Westberg', 5_000_000)[2] for _ in range(20)]
        assert sum(large) > sum(small)

    def test_unknown_continent_uses_defaults(self):
        new_land, discovered, total_gained = roll_expansion('UnknownContinent', 100_000)
        assert isinstance(new_land, dict)
        assert total_gained == sum(new_land.values())

    def test_continent_weights_reflected_in_land(self):
        # Zaheria has 85% desert — it should dominate over many rolls
        desert_total = 0
        other_total = 0
        for _ in range(30):
            land, _, _ = roll_expansion('Zaheria', 1_000_000)
            desert_total += land.get('desert', 0)
            other_total += sum(v for k, v in land.items() if k != 'desert')
        assert desert_total > other_total

    def test_tind_produces_mountain_heavy_land(self):
        # Tind has 34% mountain weight
        mountain_total = 0
        for _ in range(30):
            land, _, _ = roll_expansion('Tind', 1_000_000)
            mountain_total += land.get('mountain', 0)
        assert mountain_total > 0

    def test_resources_only_from_continent_weights(self):
        # All discovered resource keys should be in Westberg's resource table
        westberg_resources = set(RESOURCE_WEIGHTS['Westberg'])
        for _ in range(20):
            _, discovered, _ = roll_expansion('Westberg', 1_000_000)
            for res in discovered:
                assert res in westberg_resources, f"Unexpected resource: {res}"

    def test_acquisition_formula_amount(self):
        """Verify the amount of discovered resources matches the formula.
        Discovery Total = weight_sum * 3.75 * (population / 1M)
        For 1M pop, and sum=10,000, Total should be ~37,500.
        """
        pop = 1_000_000
        totals = []
        for _ in range(20):
            _, discovered, _ = roll_expansion('Westberg', pop)
            totals.append(sum(discovered.values()))
        avg_total = sum(totals) / len(totals)
        # Should be around 37,500 (with variance and rounding)
        assert 30_000 < avg_total < 45_000


class TestRollColonization:
    def test_returns_three_tuple(self):
        new_land, discovered, total_gained = roll_colonization('Westberg', 100_000)
        assert isinstance(new_land, dict)
        assert isinstance(total_gained, int)

    def test_total_gained_equals_sum_of_land(self):
        for _ in range(10):
            new_land, _, total_gained = roll_colonization('Westberg', 100_000)
            assert total_gained == sum(new_land.values())

    def test_colonization_yields_more_land_than_expansion(self):
        """Colonization should produce ~5x land for the same population."""
        pop = 500_000
        exp = [roll_expansion('Westberg', pop)[2] for _ in range(20)]
        col = [roll_colonization('Westberg', pop)[2] for _ in range(20)]
        assert sum(col) > sum(exp) * 2

    def test_colonization_more_resource_discoveries(self):
        """Colonization yields ~25x more discoveries than expansion for same population."""
        pop = 1_000_000
        exp_disc = sum(sum(roll_expansion('Westberg', pop)[1].values()) for _ in range(10))
        col_disc = sum(sum(roll_colonization('Westberg', pop)[1].values()) for _ in range(10))
        assert col_disc > exp_disc * 20

    def test_colonization_formula_amount(self):
        """Verify the amount of discovered resources matches the colonization formula.
        Discovery Total = weight_sum * 93.75 * (population / 1M)
        For 1M pop, and sum=10,000, Total should be ~937,500.
        """
        pop = 1_000_000
        totals = []
        for _ in range(20):
            _, discovered, _ = roll_colonization('Westberg', pop)
            totals.append(sum(discovered.values()))
        avg_total = sum(totals) / len(totals)
        # Should be around 937,500
        assert 800_000 < avg_total < 1_100_000


    def test_target_continent_affects_land_profile(self):
        # Colonizing Zaheria from any home continent should yield desert-heavy land
        desert = sum(roll_colonization('Zaheria', 1_000_000)[0].get('desert', 0) for _ in range(10))
        forest = sum(roll_colonization('Westberg', 1_000_000)[0].get('forest', 0) for _ in range(10))
        assert desert > 0
        assert forest > 0

    def test_land_keys_are_valid_types(self):
        for _ in range(10):
            new_land, _, _ = roll_colonization('Amarino', 1_000_000)
            for key in new_land:
                assert key in VALID_LAND_TYPES
