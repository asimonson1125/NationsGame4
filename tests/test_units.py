"""Tests for app/game/units.py — unit definitions."""
from app.game.units import UNIT_DEFS, UnitDef

def test_unit_types_breakdown():
    by_type = {}
    for u in UNIT_DEFS.values():
        if not u.npc_only:
            by_type.setdefault(u.unit_type, 0)
            by_type[u.unit_type] += 1
    assert by_type == {
        'Infantry': 10,
        'Armour': 10,
        'Static': 5,
        'Air': 9,
        'Special Forces': 5,
    }


def test_all_entries_are_unitdef():
    for key, udef in UNIT_DEFS.items():
        assert isinstance(udef, UnitDef), f'{key} is not a UnitDef'


def test_keys_are_snake_case():
    import re
    pattern = re.compile(r'^[a-z0-9][a-z0-9_]*$')
    for key in UNIT_DEFS:
        assert pattern.match(key), f'Key {key!r} is not snake_case'


def test_all_units_have_positive_stats():
    for key, u in UNIT_DEFS.items():
        assert u.firepower >= 0, f'{key} firepower < 0'
        assert u.armour >= 0, f'{key} armour < 0'
        assert u.maneuver >= 0, f'{key} maneuver < 0'
        assert u.max_hp > 0, f'{key} max_hp <= 0'


def test_all_units_have_cost():
    for key, u in UNIT_DEFS.items():
        if u.npc_only:
            continue
        assert len(u.recruit_cost) > 0, f'{key} has no recruit cost'
        for res, amt in u.recruit_cost.items():
            assert amt > 0, f'{key} cost {res} <= 0'


def test_all_units_have_recruit_time():
    for key, u in UNIT_DEFS.items():
        if u.npc_only:
            continue
        assert u.recruit_time > 0, f'{key} recruit_time <= 0'


def test_tier_range():
    for key, u in UNIT_DEFS.items():
        if u.npc_only:
            continue
        assert 1 <= u.tier <= 10, f'{key} tier {u.tier} out of range'


def test_gp_value_positive():
    for key, u in UNIT_DEFS.items():
        if u.npc_only:
            continue
        assert u.gp_value >= 1, f'{key} gp_value < 1'


def test_upkeep_resources_are_valid():
    valid = {'money', 'food', 'power', 'building_materials', 'consumer_goods',
             'metal', 'ammunition', 'fuel', 'uranium'}
    for key, u in UNIT_DEFS.items():
        for res in u.upkeep:
            assert res in valid, f'{key} upkeep has invalid resource {res!r}'


def test_cost_resources_are_valid():
    valid = {'money', 'food', 'power', 'building_materials', 'consumer_goods',
             'metal', 'ammunition', 'fuel', 'uranium'}
    for key, u in UNIT_DEFS.items():
        for res in u.recruit_cost:
            assert res in valid, f'{key} cost has invalid resource {res!r}'


# ── Spot-check specific NG3 units ────────────────────────────────────────

def test_infantry_stats():
    u = UNIT_DEFS['infantry']
    assert u.name == 'Infantry'
    assert u.firepower == 3
    assert u.armour == 1
    assert u.maneuver == 2
    assert u.max_hp == 50
    assert u.recruit_cost == {'money': 1000}
    assert u.upkeep == {'money': 1, 'food': 1}
    assert u.recruit_time == 3600


def test_national_guard_defending():
    u = UNIT_DEFS['national_guard']
    assert u.name == 'National Guard'
    assert any('1.5x all combat stats while defending' in a for a in u.special_abilities)


def test_gear_infantry_stats():
    u = UNIT_DEFS['gear_infantry']
    assert u.firepower == 6
    assert u.armour == 4
    assert u.maneuver == 4
    assert u.max_hp == 115


def test_m1a1_abrahms_stats():
    u = UNIT_DEFS['m1a1_abrahms']
    assert u.name == 'M1A1 Abrahms'
    assert u.unit_type == 'Armour'
    assert u.firepower == 3
    assert u.armour == 4
    assert u.max_hp == 130
    assert u.recruit_cost == {'money': 10000, 'metal': 100}


def test_gearhound_warhead_stats():
    u = UNIT_DEFS['gearhound_warhead']
    assert u.firepower == 7
    assert u.armour == 7
    assert u.max_hp == 245
    assert u.upkeep.get('uranium') == 3


def test_railgun_stats():
    u = UNIT_DEFS['railgun']
    assert u.firepower == 20
    assert u.max_hp == 150
    assert u.recruit_cost == {'money': 500000, 'building_materials': 25000, 'metal': 5000}


def test_lockheed_ac130_abilities():
    u = UNIT_DEFS['lockheed_ac_130']
    assert u.maneuver == 11
    abilities = u.special_abilities
    assert any('4x firepower against infantry units' in a for a in abilities)
    assert any('4x firepower against armour units' in a for a in abilities)
    assert any('4x firepower against special forces units' in a for a in abilities)
    assert any('4x maneuver multiplier to friendly units' in a for a in abilities)


def test_fortified_bunker_stats():
    u = UNIT_DEFS['fortified_bunker']
    assert u.armour == 10
    assert u.max_hp == 1040


def test_b2_spirit_stats():
    u = UNIT_DEFS['b_2_spirit']
    assert u.firepower == 9
    assert u.armour == 6
    assert u.maneuver == 8
    assert u.max_hp == 155
    assert u.upkeep.get('uranium') == 1
