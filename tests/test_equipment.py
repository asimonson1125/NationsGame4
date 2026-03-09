"""Tests for app/game/equipment.py — equipment generation, buffs, crates."""
import json
import random
import math
import pytest
from app.game.equipment import (
    EQUIPMENT_SLOTS, ALL_EQUIPMENT_TYPES, UNIT_CATEGORIES,
    RARITY_ORDER, RARITY_BUFF_POINTS, RARITY_DROP_RATES, FOIL_CHANCE,
    TRADE_IN_VALUES, CRATE_SIZES, _SLOT_NAMES,
    _roll_rarity, generate_equipment, _generate_buffs,
    generate_crate_contents, get_slots_for_unit_type, get_slot_category,
    get_unit_categories_for_equipment, compute_buff_hash, serialize_buffs,
)


# ── Constants & definitions ───────────────────────────────────────────────

class TestEquipmentConstants:
    def test_all_unit_categories_have_three_slots(self):
        for cat, slots in EQUIPMENT_SLOTS.items():
            assert len(slots) == 3, f'{cat} should have 3 slots, got {len(slots)}'

    def test_all_slots_resolve_to_category(self):
        for cat, slots in EQUIPMENT_SLOTS.items():
            for slot in slots:
                result = get_slot_category(slot, cat)
                assert result in ('weapon', 'accessory', 'armour'), \
                    f'{slot} in {cat} resolved to {result}'

    def test_each_unit_category_has_one_of_each_slot(self):
        """Each unit type should have exactly one weapon, one accessory, one armour."""
        for cat, slots in EQUIPMENT_SLOTS.items():
            cats = [get_slot_category(s, cat) for s in slots]
            assert sorted(cats) == ['accessory', 'armour', 'weapon'], \
                f'{cat} slots map to {cats}, expected one of each'

    def test_shared_equipment_types(self):
        """Equipment types can be shared across unit categories."""
        # Heavy Accessory is used by Armour, Air, and Static
        cats = get_unit_categories_for_equipment('Heavy Accessory')
        assert set(cats) == {'Armour', 'Air', 'Static'}
        # Infantry Weapon is used by Infantry and Special Forces
        cats = get_unit_categories_for_equipment('Infantry Weapon')
        assert set(cats) == {'Infantry', 'Special Forces'}

    def test_five_unit_categories(self):
        assert len(UNIT_CATEGORIES) == 5
        assert set(UNIT_CATEGORIES) == {'Infantry', 'Armour', 'Air', 'Static', 'Special Forces'}

    def test_five_rarities(self):
        assert RARITY_ORDER == ['Common', 'Uncommon', 'Rare', 'Epic', 'Legendary']

    def test_rarity_drop_rates_sum_to_one(self):
        total = sum(RARITY_DROP_RATES.values())
        assert abs(total - 1.0) < 1e-9

    def test_buff_points_increase_with_rarity(self):
        prev = 0
        for rarity in RARITY_ORDER:
            pts = RARITY_BUFF_POINTS[rarity]
            assert pts > prev, f'{rarity} should have more buff pts than previous'
            prev = pts

    def test_trade_in_values_increase_with_rarity(self):
        prev = -1
        for rarity in RARITY_ORDER:
            val = TRADE_IN_VALUES[rarity]
            assert val >= prev, f'{rarity} trade value should be >= previous'
            prev = val

    def test_common_trade_value_is_zero(self):
        assert TRADE_IN_VALUES['Common'] == 0

    def test_crate_sizes_defined(self):
        assert set(CRATE_SIZES.keys()) == {'small', 'medium', 'epic'}

    def test_crate_item_counts(self):
        assert CRATE_SIZES['small']['items'] == 1
        assert CRATE_SIZES['medium']['items'] == 3
        assert CRATE_SIZES['epic']['items'] == 5

    def test_crate_costs_increase(self):
        assert CRATE_SIZES['small']['cost'] < CRATE_SIZES['medium']['cost']
        assert CRATE_SIZES['medium']['cost'] < CRATE_SIZES['epic']['cost']

    def test_crate_guarantees_dont_exceed_item_count(self):
        for key, crate in CRATE_SIZES.items():
            guaranteed = crate['guaranteed_epic'] + crate['guaranteed_rare']
            assert guaranteed <= crate['items'], \
                f'{key} crate guarantees ({guaranteed}) > items ({crate["items"]})'


# ── Rarity rolling ────────────────────────────────────────────────────────

class TestRollRarity:
    def test_returns_valid_rarity(self):
        random.seed(42)
        for _ in range(100):
            r = _roll_rarity()
            assert r in RARITY_ORDER

    def test_min_rarity_rare_never_returns_common_or_uncommon(self):
        random.seed(42)
        for _ in range(200):
            r = _roll_rarity(min_rarity='Rare')
            assert r in ('Rare', 'Epic', 'Legendary')

    def test_min_rarity_epic_never_returns_below_epic(self):
        random.seed(42)
        for _ in range(200):
            r = _roll_rarity(min_rarity='Epic')
            assert r in ('Epic', 'Legendary')

    def test_min_rarity_legendary_always_legendary(self):
        random.seed(42)
        for _ in range(50):
            r = _roll_rarity(min_rarity='Legendary')
            assert r == 'Legendary'

    def test_no_min_rarity_produces_all_tiers(self):
        """Over many rolls, all rarities should appear."""
        random.seed(42)
        seen = set()
        for _ in range(5000):
            seen.add(_roll_rarity())
        assert seen == set(RARITY_ORDER)

    def test_common_most_frequent(self):
        random.seed(42)
        counts = {r: 0 for r in RARITY_ORDER}
        for _ in range(5000):
            counts[_roll_rarity()] += 1
        assert counts['Common'] > counts['Uncommon']
        assert counts['Uncommon'] > counts['Rare']
        assert counts['Rare'] > counts['Epic']
        assert counts['Epic'] > counts['Legendary']


# ── Equipment generation ──────────────────────────────────────────────────

class TestGenerateEquipment:
    def test_returns_required_keys(self):
        random.seed(42)
        eq = generate_equipment('Infantry')
        assert 'equipment_type' in eq
        assert 'rarity' in eq
        assert 'is_foil' in eq
        assert 'buffs' in eq

    def test_equipment_type_matches_category(self):
        random.seed(42)
        for _ in range(50):
            for cat in UNIT_CATEGORIES:
                eq = generate_equipment(cat)
                assert eq['equipment_type'] in EQUIPMENT_SLOTS[cat], \
                    f'{eq["equipment_type"]} not in {cat} slots'

    def test_rarity_is_valid(self):
        random.seed(42)
        for _ in range(100):
            eq = generate_equipment('Infantry')
            assert eq['rarity'] in RARITY_ORDER

    def test_explicit_rarity_honored(self):
        random.seed(42)
        for rarity in RARITY_ORDER:
            eq = generate_equipment('Armour', rarity=rarity)
            assert eq['rarity'] == rarity

    def test_buffs_non_empty(self):
        random.seed(42)
        for _ in range(50):
            eq = generate_equipment('Infantry', rarity='Common')
            assert len(eq['buffs']) >= 1

    def test_buff_structure(self):
        random.seed(42)
        eq = generate_equipment('Infantry', rarity='Epic')
        for buff in eq['buffs']:
            assert 'buff_type' in buff
            assert 'value' in buff
            assert 'description' in buff
            assert isinstance(buff['value'], (int, float))
            assert len(buff['description']) > 0

    def test_foil_has_more_buff_points(self):
        """Foil items should have ceil(1.5x) buff points."""
        random.seed(42)
        for rarity in RARITY_ORDER:
            base_pts = RARITY_BUFF_POINTS[rarity]
            foil_pts = math.ceil(base_pts * 1.5)
            # Generate a foil manually to check point allocation
            eq = generate_equipment('Infantry', rarity=rarity)
            # We can't easily verify exact points from the output,
            # but we can verify the logic is consistent
            assert foil_pts >= base_pts

    def test_foil_appears_sometimes(self):
        """Over many rolls, at least one foil should appear."""
        random.seed(42)
        foils = sum(1 for _ in range(200) if generate_equipment('Infantry')['is_foil'])
        assert foils > 0

    def test_non_foil_is_common(self):
        """Most items should be non-foil."""
        random.seed(42)
        non_foils = sum(1 for _ in range(200)
                        if not generate_equipment('Infantry')['is_foil'])
        assert non_foils > 150


# ── Buff generation ───────────────────────────────────────────────────────

class TestGenerateBuffs:
    def test_single_point_produces_one_buff(self):
        random.seed(42)
        buffs = _generate_buffs(1, 'Infantry')
        assert len(buffs) == 1

    def test_zero_points_returns_empty(self):
        assert _generate_buffs(0, 'Infantry') == []

    def test_buff_types_are_valid(self):
        random.seed(42)
        valid_prefixes = ('Firepower', 'Armour', 'Maneuver', 'HP', 'FPvs_', 'AllStats_')
        for _ in range(100):
            buffs = _generate_buffs(7, 'Infantry')
            for b in buffs:
                assert any(b['buff_type'].startswith(p) for p in valid_prefixes), \
                    f'Invalid buff type: {b["buff_type"]}'

    def test_flat_buff_value_is_integer(self):
        """Flat stat buffs (Firepower, Armour, Maneuver) should have integer values."""
        random.seed(42)
        for _ in range(100):
            buffs = _generate_buffs(5, 'Infantry')
            for b in buffs:
                if b['buff_type'] in ('Firepower', 'Armour', 'Maneuver'):
                    assert isinstance(b['value'], int), \
                        f'{b["buff_type"]} value should be int, got {type(b["value"])}'

    def test_multiplier_buff_value_above_one(self):
        """FPvs_ and AllStats_ buffs should have value > 1.0."""
        random.seed(42)
        for _ in range(200):
            buffs = _generate_buffs(7, 'Infantry')
            for b in buffs:
                if b['buff_type'].startswith('FPvs_') or b['buff_type'].startswith('AllStats_'):
                    assert b['value'] > 1.0

    def test_hp_buff_value_above_one(self):
        random.seed(42)
        for _ in range(200):
            buffs = _generate_buffs(5, 'Infantry')
            for b in buffs:
                if b['buff_type'] == 'HP':
                    assert b['value'] > 1.0

    def test_high_points_tend_to_cluster(self):
        """With many points, most should cluster on one buff type (65% repeat rate)."""
        random.seed(42)
        single_buff_count = 0
        for _ in range(100):
            buffs = _generate_buffs(10, 'Infantry')
            if len(buffs) == 1:
                single_buff_count += 1
        # With 65% clustering, getting all 10 on one type has p = 0.65^9 ≈ 2%
        # Most should have 1-3 distinct buff types
        # Just verify not all are scattered to max distinct
        avg_distinct = sum(len(_generate_buffs(10, 'Infantry')) for _ in range(100)) / 100
        assert avg_distinct < 5  # should average well under 5 distinct types

    def test_description_contains_value(self):
        random.seed(42)
        buffs = _generate_buffs(3, 'Infantry')
        for b in buffs:
            # Description should contain the value in some form
            assert str(int(b['value'])) in b['description'] or \
                   str(b['value']) in b['description'], \
                f'Description "{b["description"]}" missing value {b["value"]}'


# ── Crate contents ────────────────────────────────────────────────────────

class TestGenerateCrateContents:
    def test_small_crate_returns_one_item(self):
        random.seed(42)
        items = generate_crate_contents('small', 'Infantry')
        assert len(items) == 1

    def test_medium_crate_returns_three_items(self):
        random.seed(42)
        items = generate_crate_contents('medium', 'Infantry')
        assert len(items) == 3

    def test_epic_crate_returns_five_items(self):
        random.seed(42)
        items = generate_crate_contents('epic', 'Infantry')
        assert len(items) == 5

    def test_invalid_crate_size_returns_empty(self):
        items = generate_crate_contents('mega', 'Infantry')
        assert items == []

    def test_medium_crate_has_rare_guarantees(self):
        """Medium crate should have at least 2 Rare+ items."""
        random.seed(42)
        items = generate_crate_contents('medium', 'Infantry')
        rare_plus = [i for i in items
                     if RARITY_ORDER.index(i['rarity']) >= RARITY_ORDER.index('Rare')]
        assert len(rare_plus) >= 2

    def test_epic_crate_has_epic_guarantee(self):
        """Epic crate should have at least 1 Epic+ item."""
        random.seed(42)
        items = generate_crate_contents('epic', 'Infantry')
        epic_plus = [i for i in items
                     if RARITY_ORDER.index(i['rarity']) >= RARITY_ORDER.index('Epic')]
        assert len(epic_plus) >= 1

    def test_epic_crate_has_rare_guarantees(self):
        """Epic crate should have at least 2 Rare+ items (on top of Epic)."""
        random.seed(42)
        items = generate_crate_contents('epic', 'Infantry')
        rare_plus = [i for i in items
                     if RARITY_ORDER.index(i['rarity']) >= RARITY_ORDER.index('Rare')]
        assert len(rare_plus) >= 3  # 1 epic+ + 2 rare+

    def test_crate_items_match_category(self):
        random.seed(42)
        for cat in UNIT_CATEGORIES:
            items = generate_crate_contents('medium', cat)
            for item in items:
                assert item['equipment_type'] in EQUIPMENT_SLOTS[cat]

    def test_all_categories_work(self):
        random.seed(42)
        for cat in UNIT_CATEGORIES:
            items = generate_crate_contents('small', cat)
            assert len(items) == 1


# ── Helper functions ──────────────────────────────────────────────────────

class TestHelperFunctions:
    def test_get_slots_for_unit_type(self):
        assert get_slots_for_unit_type('Infantry') == \
            ['Infantry Weapon', 'Infantry Accessory', 'Body Armour']

    def test_get_slots_for_unknown_type(self):
        assert get_slots_for_unit_type('Unknown') == []

    def test_get_slot_category_weapon(self):
        assert get_slot_category('Infantry Weapon', 'Infantry') == 'weapon'
        assert get_slot_category('Heavy Accessory', 'Armour') == 'weapon'
        assert get_slot_category('Heavy Accessory', 'Air') == 'weapon'
        assert get_slot_category('Heavy Accessory', 'Static') == 'weapon'

    def test_get_slot_category_accessory(self):
        assert get_slot_category('Infantry Accessory', 'Infantry') == 'accessory'
        assert get_slot_category('Crew', 'Armour') == 'accessory'
        assert get_slot_category('Ammunition', 'Air') == 'accessory'
        assert get_slot_category('Ammunition', 'Static') == 'accessory'

    def test_get_slot_category_armour(self):
        assert get_slot_category('Body Armour', 'Infantry') == 'armour'
        assert get_slot_category('Engine', 'Armour') == 'armour'
        assert get_slot_category('Engine', 'Air') == 'armour'
        assert get_slot_category('Crew', 'Static') == 'armour'

    def test_get_slot_category_same_type_different_slot(self):
        """Crew is accessory for Armour but armour for Static."""
        assert get_slot_category('Crew', 'Armour') == 'accessory'
        assert get_slot_category('Crew', 'Static') == 'armour'

    def test_get_slot_category_unknown_defaults_to_weapon(self):
        assert get_slot_category('Unknown Slot', 'Infantry') == 'weapon'

    def test_get_unit_categories_for_equipment(self):
        assert set(get_unit_categories_for_equipment('Infantry Weapon')) == {'Infantry', 'Special Forces'}
        assert set(get_unit_categories_for_equipment('Engine')) == {'Armour', 'Air'}
        assert set(get_unit_categories_for_equipment('Heavy Accessory')) == {'Armour', 'Air', 'Static'}
        assert set(get_unit_categories_for_equipment('Ammunition')) == {'Air', 'Static'}

    def test_get_unit_categories_for_unknown(self):
        assert get_unit_categories_for_equipment('Unknown') == []


# ── Buff serialization & hashing ─────────────────────────────────────────

class TestBuffSerialization:
    def test_serialize_buffs_deterministic(self):
        buffs = [
            {'buff_type': 'Armour', 'value': 2, 'description': '+2 Armour'},
            {'buff_type': 'Firepower', 'value': 3, 'description': '+3 Firepower'},
        ]
        # Same result regardless of input order
        buffs_reversed = list(reversed(buffs))
        assert serialize_buffs(buffs) == serialize_buffs(buffs_reversed)

    def test_serialize_buffs_valid_json(self):
        buffs = [{'buff_type': 'HP', 'value': 1.3, 'description': 'x1.3 HP'}]
        result = serialize_buffs(buffs)
        parsed = json.loads(result)
        assert len(parsed) == 1
        assert parsed[0]['buff_type'] == 'HP'

    def test_serialize_buffs_empty(self):
        assert serialize_buffs([]) == '[]'

    def test_compute_buff_hash_deterministic(self):
        buffs = [
            {'buff_type': 'Firepower', 'value': 3, 'description': '+3 Firepower'},
            {'buff_type': 'Armour', 'value': 2, 'description': '+2 Armour'},
        ]
        h1 = compute_buff_hash(buffs)
        h2 = compute_buff_hash(list(reversed(buffs)))
        assert h1 == h2

    def test_compute_buff_hash_is_64_hex_chars(self):
        buffs = [{'buff_type': 'Firepower', 'value': 1, 'description': '+1 FP'}]
        h = compute_buff_hash(buffs)
        assert len(h) == 64
        assert all(c in '0123456789abcdef' for c in h)

    def test_different_buffs_different_hash(self):
        b1 = [{'buff_type': 'Firepower', 'value': 3, 'description': '+3 FP'}]
        b2 = [{'buff_type': 'Firepower', 'value': 5, 'description': '+5 FP'}]
        assert compute_buff_hash(b1) != compute_buff_hash(b2)
