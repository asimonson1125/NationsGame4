"""Tests for territory expansion and resource discovery engine."""
import pytest
from app.game.discovery import (
    roll_expansion, roll_colonization,
    LAND_WEIGHTS, RESOURCE_WEIGHTS, RESOURCE_LEVELS,
    _weighted_distribute, _get_building_level,
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


class TestGetBuildingLevel:
    def test_flora_uses_botanical_station(self):
        assert _get_building_level({'botanical_research_station': 3}, 'apple_tree') == 3

    def test_fauna_uses_wildlife_ranch(self):
        assert _get_building_level({'wildlife_ranch': 2}, 'cow') == 2

    def test_mined_uses_mining_bureau(self):
        assert _get_building_level({'mining_bureau': 2}, 'coal') == 2

    def test_missing_building_defaults_to_1(self):
        assert _get_building_level({}, 'apple_tree') == 1
        assert _get_building_level({}, 'cow') == 1
        assert _get_building_level({}, 'coal') == 1


class TestBuildingGating:
    def test_no_buildings_allows_only_level1_resources(self):
        """With empty buildings dict (all levels default to 1), only level 1 resources pass."""
        buildings = {}
        for continent in ALL_CONTINENTS:
            weights = RESOURCE_WEIGHTS[continent]
            eligible = {
                res: w for res, w in weights.items()
                if w > 0 and _get_building_level(buildings, res) >= RESOURCE_LEVELS.get(res, 1)
            }
            for res in eligible:
                level = RESOURCE_LEVELS.get(res, 1)
                assert level == 1, (
                    f"{res} (level {level}) should not be eligible in {continent} "
                    f"without buildings"
                )

    def test_level2_building_unlocks_level2_resources(self):
        """Mining Bureau level 2 unlocks copper and lead (level 2 mined) in Westberg."""
        buildings = {'mining_bureau': 2}
        weights = RESOURCE_WEIGHTS['Westberg']
        eligible = {
            res: w for res, w in weights.items()
            if w > 0 and _get_building_level(buildings, res) >= RESOURCE_LEVELS.get(res, 1)
        }
        assert 'copper' in eligible
        assert 'lead' in eligible
        assert 'coal' in eligible   # level 1 still present

    def test_level3_building_needed_for_level3_resources(self):
        """Gold is level 3 mined. Mining Bureau level 2 should not unlock it."""
        weights = RESOURCE_WEIGHTS['Westberg']

        eligible_l2 = {
            res: w for res, w in weights.items()
            if w > 0 and _get_building_level({'mining_bureau': 2}, res) >= RESOURCE_LEVELS.get(res, 1)
        }
        assert 'gold' not in eligible_l2

        eligible_l3 = {
            res: w for res, w in weights.items()
            if w > 0 and _get_building_level({'mining_bureau': 3}, res) >= RESOURCE_LEVELS.get(res, 1)
        }
        assert 'gold' in eligible_l3

    def test_fauna_building_gates_fauna_independently(self):
        """Wildlife Ranch gates fauna resources; Mining Bureau doesn't affect them."""
        buildings = {'mining_bureau': 3, 'wildlife_ranch': 1}
        weights = RESOURCE_WEIGHTS['Westberg']
        eligible = {
            res: w for res, w in weights.items()
            if w > 0 and _get_building_level(buildings, res) >= RESOURCE_LEVELS.get(res, 1)
        }
        # cow is level 2 fauna — wildlife_ranch=1 should still block it
        assert 'cow' not in eligible

        buildings_l2 = {'wildlife_ranch': 2}
        eligible_l2 = {
            res: w for res, w in weights.items()
            if w > 0 and _get_building_level(buildings_l2, res) >= RESOURCE_LEVELS.get(res, 1)
        }
        assert 'cow' in eligible_l2


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

    def test_building_gated_resources_not_discovered_without_building(self):
        """Level 2+ resources must not appear without the appropriate building."""
        buildings = {}   # all default to level 1
        for _ in range(50):
            _, discovered, _ = roll_expansion('Westberg', 1_000_000, buildings=buildings)
            for res in discovered:
                assert RESOURCE_LEVELS.get(res, 1) == 1, (
                    f"{res} (level {RESOURCE_LEVELS[res]}) discovered without building"
                )

    def test_building_level2_enables_level2_resources(self):
        """With mining_bureau=2, level 2 mined resources can appear over many rolls."""
        buildings = {'mining_bureau': 3}  # unlocks gold (level 3)
        found_level2_plus = False
        for _ in range(100):
            _, discovered, _ = roll_expansion('Westberg', 10_000_000, buildings=buildings)
            if any(RESOURCE_LEVELS.get(res, 1) >= 2 for res in discovered):
                found_level2_plus = True
                break
        assert found_level2_plus, "Level 2+ resources never discovered despite having building level 3"


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
        """Colonization uses total//2 for discoveries vs expansion's total//10."""
        pop = 1_000_000
        exp_disc = sum(sum(roll_expansion('Westberg', pop)[1].values()) for _ in range(10))
        col_disc = sum(sum(roll_colonization('Westberg', pop)[1].values()) for _ in range(10))
        assert col_disc > exp_disc

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
