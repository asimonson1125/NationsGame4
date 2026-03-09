"""Tests for equipment buff integration in combat.py."""
import random
import pytest
from app import db
from app.models import Equipment, Unit
from app.game.combat import (
    _get_equipment_buffs, _sum_flat_buff, _get_hp_multiplier,
    _get_fp_vs_multiplier, _get_continent_multiplier,
    _get_effective_firepower, _get_effective_armour,
    _effective_maneuver, calculate_damage,
)
from app.game.equipment import compute_buff_hash, serialize_buffs
from app.game.units import UNIT_DEFS


# ── Helpers ───────────────────────────────────────────────────────────────

def _make_unit_with_equipment(nation, unit_key='infantry', buffs_by_slot=None):
    """Create a unit and attach equipment with specific buffs.

    buffs_by_slot: dict of slot -> list of (buff_type, value, description)
        slot is 'weapon', 'accessory', or 'armour'
    """
    udef = UNIT_DEFS[unit_key]
    unit = Unit(
        nation_id=nation.id, unit_key=unit_key,
        firepower=udef.firepower, armour=udef.armour,
        maneuver=udef.maneuver, hp=udef.max_hp, max_hp=udef.max_hp,
    )
    db.session.add(unit)
    db.session.flush()

    if buffs_by_slot:
        # Map unit type to equipment types
        from app.game.equipment import EQUIPMENT_SLOTS
        slots = EQUIPMENT_SLOTS.get(udef.unit_type, EQUIPMENT_SLOTS['Infantry'])
        slot_to_type = {
            'weapon': slots[0],
            'accessory': slots[1],
            'armour': slots[2],
        }

        for slot_name, buff_list in buffs_by_slot.items():
            eq_type = slot_to_type[slot_name]
            buff_dicts = [{'buff_type': bt, 'value': val, 'description': desc}
                          for bt, val, desc in buff_list]
            eq = Equipment(
                nation_id=nation.id, equipment_type=eq_type,
                rarity='Epic', is_foil=False,
                buff_hash=compute_buff_hash(buff_dicts),
                buff_json=serialize_buffs(buff_dicts),
            )
            db.session.add(eq)
            db.session.flush()
            if slot_name == 'weapon':
                unit.weapon_id = eq.id
            elif slot_name == 'accessory':
                unit.accessory_id = eq.id
            elif slot_name == 'armour':
                unit.armour_eq_id = eq.id

    db.session.commit()
    return unit


def _make_bare_unit(nation, unit_key='infantry'):
    """Create a unit with no equipment."""
    udef = UNIT_DEFS[unit_key]
    unit = Unit(
        nation_id=nation.id, unit_key=unit_key,
        firepower=udef.firepower, armour=udef.armour,
        maneuver=udef.maneuver, hp=udef.max_hp, max_hp=udef.max_hp,
    )
    db.session.add(unit)
    db.session.commit()
    return unit


# ── Equipment buff helper tests ───────────────────────────────────────────

class TestEquipmentBuffHelpers:
    def test_get_equipment_buffs_empty(self, app, nation):
        unit = _make_bare_unit(nation)
        buffs = _get_equipment_buffs(unit)
        assert buffs == []

    def test_get_equipment_buffs_from_weapon(self, app, nation):
        unit = _make_unit_with_equipment(nation, buffs_by_slot={
            'weapon': [('Firepower', 5, '+5 Firepower')],
        })
        buffs = _get_equipment_buffs(unit)
        assert ('Firepower', 5) in buffs

    def test_get_equipment_buffs_from_all_slots(self, app, nation):
        unit = _make_unit_with_equipment(nation, buffs_by_slot={
            'weapon': [('Firepower', 3, '+3 FP')],
            'accessory': [('Maneuver', 2, '+2 Man')],
            'armour': [('Armour', 4, '+4 Arm')],
        })
        buffs = _get_equipment_buffs(unit)
        assert len(buffs) == 3
        assert ('Firepower', 3) in buffs
        assert ('Maneuver', 2) in buffs
        assert ('Armour', 4) in buffs

    def test_sum_flat_buff(self):
        buffs = [('Firepower', 3), ('Armour', 2), ('Firepower', 5)]
        assert _sum_flat_buff(buffs, 'Firepower') == 8
        assert _sum_flat_buff(buffs, 'Armour') == 2
        assert _sum_flat_buff(buffs, 'Maneuver') == 0

    def test_get_hp_multiplier_single(self):
        buffs = [('HP', 1.3)]
        assert _get_hp_multiplier(buffs) == pytest.approx(1.3)

    def test_get_hp_multiplier_multiple_multiplicative(self):
        buffs = [('HP', 1.2), ('HP', 1.5)]
        assert _get_hp_multiplier(buffs) == pytest.approx(1.8)

    def test_get_hp_multiplier_none(self):
        buffs = [('Firepower', 5)]
        assert _get_hp_multiplier(buffs) == 1.0

    def test_get_fp_vs_multiplier_matching(self):
        buffs = [('FPvs_Armour', 1.5)]
        assert _get_fp_vs_multiplier(buffs, 'Armour') == pytest.approx(1.5)

    def test_get_fp_vs_multiplier_no_match(self):
        buffs = [('FPvs_Armour', 1.5)]
        assert _get_fp_vs_multiplier(buffs, 'Infantry') == 1.0

    def test_get_fp_vs_multiplier_special_forces(self):
        buffs = [('FPvs_Special_Forces', 1.75)]
        assert _get_fp_vs_multiplier(buffs, 'Special Forces') == pytest.approx(1.75)

    def test_get_continent_multiplier_matching(self):
        buffs = [('AllStats_Westberg', 1.3)]
        assert _get_continent_multiplier(buffs, 'Westberg') == pytest.approx(1.3)

    def test_get_continent_multiplier_no_match(self):
        buffs = [('AllStats_Westberg', 1.3)]
        assert _get_continent_multiplier(buffs, 'Tind') == 1.0

    def test_get_continent_multiplier_empty_continent(self):
        buffs = [('AllStats_Westberg', 1.3)]
        assert _get_continent_multiplier(buffs, '') == 1.0
        assert _get_continent_multiplier(buffs, None) == 1.0

    def test_get_continent_multiplier_san_sebastian(self):
        buffs = [('AllStats_San_Sebastian', 1.2)]
        assert _get_continent_multiplier(buffs, 'San Sebastian') == pytest.approx(1.2)


# ── Effective firepower with equipment ────────────────────────────────────

class TestEffectiveFirepowerWithEquipment:
    def test_flat_fp_buff_adds_to_base(self, app, nation):
        # Infantry base fp=3, +5 from equipment = 8
        attacker = _make_unit_with_equipment(nation, buffs_by_slot={
            'weapon': [('Firepower', 5, '+5 FP')],
        })
        defender = _make_bare_unit(nation, 'infantry')
        fp = _get_effective_firepower(attacker, defender)
        assert fp == 8  # 3 + 5

    def test_fp_vs_type_multiplier(self, app, nation):
        # +5 FP + 1.5x vs Armour
        attacker = _make_unit_with_equipment(nation, buffs_by_slot={
            'weapon': [
                ('Firepower', 5, '+5 FP'),
                ('FPvs_Armour', 1.5, '1.5x vs Armour'),
            ],
        })
        defender = _make_bare_unit(nation, 'm1a1_abrahms')
        fp = _get_effective_firepower(attacker, defender)
        # (3 + 5) * 1.5 = 12.0  (no unit ability multiplier for basic infantry)
        assert fp == pytest.approx(12.0)

    def test_fp_vs_type_no_match(self, app, nation):
        attacker = _make_unit_with_equipment(nation, buffs_by_slot={
            'weapon': [('FPvs_Armour', 1.5, '1.5x vs Armour')],
        })
        defender = _make_bare_unit(nation, 'infantry')
        fp = _get_effective_firepower(attacker, defender)
        # No match, so just base fp=3, no multiplier
        assert fp == pytest.approx(3.0)

    def test_continent_multiplier_applied(self, app, nation):
        attacker = _make_unit_with_equipment(nation, buffs_by_slot={
            'weapon': [('AllStats_Westberg', 1.2, '1.2x in Westberg')],
        })
        defender = _make_bare_unit(nation, 'infantry')
        fp = _get_effective_firepower(attacker, defender, continent='Westberg')
        assert fp == pytest.approx(3 * 1.2)

    def test_continent_multiplier_no_match(self, app, nation):
        attacker = _make_unit_with_equipment(nation, buffs_by_slot={
            'weapon': [('AllStats_Westberg', 1.2, '1.2x in Westberg')],
        })
        defender = _make_bare_unit(nation, 'infantry')
        fp = _get_effective_firepower(attacker, defender, continent='Tind')
        assert fp == pytest.approx(3.0)

    def test_no_equipment_unchanged(self, app, nation):
        attacker = _make_bare_unit(nation, 'infantry')
        defender = _make_bare_unit(nation, 'infantry')
        fp = _get_effective_firepower(attacker, defender)
        assert fp == 3  # base infantry fp

    def test_unit_ability_plus_equipment_stack(self, app, nation):
        # AT4 infantry: 4x FP vs armour (unit ability), plus equipment +2 FP
        attacker = _make_unit_with_equipment(nation, 'at4_infantry', buffs_by_slot={
            'weapon': [('Firepower', 2, '+2 FP')],
        })
        defender = _make_bare_unit(nation, 'm1a1_abrahms')
        fp = _get_effective_firepower(attacker, defender)
        # (3 base + 2 eq = 5) * 4 (unit ability vs Armour) = 20
        assert fp == pytest.approx(20.0)


# ── Effective armour with equipment ───────────────────────────────────────

class TestEffectiveArmourWithEquipment:
    def test_flat_armour_buff(self, app, nation):
        attacker = _make_bare_unit(nation, 'infantry')
        defender = _make_unit_with_equipment(nation, buffs_by_slot={
            'armour': [('Armour', 3, '+3 Armour')],
        })
        arm = _get_effective_armour(defender, attacker)
        assert arm == 4  # 1 base + 3 eq

    def test_continent_multiplier_on_armour(self, app, nation):
        attacker = _make_bare_unit(nation, 'infantry')
        defender = _make_unit_with_equipment(nation, buffs_by_slot={
            'armour': [('AllStats_Tind', 1.5, '1.5x in Tind')],
        })
        arm = _get_effective_armour(defender, attacker, continent='Tind')
        assert arm == pytest.approx(1 * 1.5)


# ── Effective maneuver with equipment ─────────────────────────────────────

class TestEffectiveManeuverWithEquipment:
    def test_flat_maneuver_buff(self, app, nation):
        unit = _make_unit_with_equipment(nation, buffs_by_slot={
            'accessory': [('Maneuver', 3, '+3 Maneuver')],
        })
        man = _effective_maneuver(unit, [], [])
        assert man == 5  # 2 base + 3 eq

    def test_continent_multiplier_on_maneuver(self, app, nation):
        unit = _make_unit_with_equipment(nation, buffs_by_slot={
            'accessory': [('AllStats_Zaheria', 1.5, '1.5x in Zaheria')],
        })
        man = _effective_maneuver(unit, [], [], continent='Zaheria')
        assert man == pytest.approx(2 * 1.5)


# ── Full damage calculation with equipment ────────────────────────────────

class TestCalculateDamageWithEquipment:
    def test_equipment_increases_damage(self, app, nation):
        """Unit with +5 FP equipment should deal more damage than without."""
        random.seed(42)
        attacker_eq = _make_unit_with_equipment(nation, buffs_by_slot={
            'weapon': [('Firepower', 5, '+5 FP')],
        })
        defender = _make_bare_unit(nation, 'infantry')
        dmg_eq, _, _ = calculate_damage(attacker_eq, defender)

        random.seed(42)
        attacker_bare = _make_bare_unit(nation, 'infantry')
        dmg_bare, _, _ = calculate_damage(attacker_bare, defender)

        assert dmg_eq > dmg_bare

    def test_armour_equipment_reduces_damage(self, app, nation):
        """Defender with +5 Armour equipment should take less damage."""
        attacker = _make_bare_unit(nation, 'infantry')

        random.seed(42)
        defender_eq = _make_unit_with_equipment(nation, buffs_by_slot={
            'armour': [('Armour', 5, '+5 Armour')],
        })
        dmg_eq, _, _ = calculate_damage(attacker, defender_eq)

        random.seed(42)
        defender_bare = _make_bare_unit(nation, 'infantry')
        dmg_bare, _, _ = calculate_damage(attacker, defender_bare)

        assert dmg_eq < dmg_bare

    def test_continent_buff_in_damage_calc(self, app, nation):
        """Continent buff should modify damage when defender_continent matches."""
        random.seed(42)
        attacker = _make_unit_with_equipment(nation, buffs_by_slot={
            'weapon': [('AllStats_Westberg', 1.5, '1.5x in Westberg')],
        })
        defender = _make_bare_unit(nation, 'infantry')

        dmg_match, _, _ = calculate_damage(attacker, defender,
                                           defender_continent='Westberg')
        random.seed(42)
        dmg_no_match, _, _ = calculate_damage(attacker, defender,
                                              defender_continent='Tind')

        assert dmg_match > dmg_no_match

    def test_equipment_details_in_output(self, app, nation):
        """Damage details should reflect equipment-modified stats."""
        random.seed(42)
        attacker = _make_unit_with_equipment(nation, buffs_by_slot={
            'weapon': [('Firepower', 5, '+5 FP')],
        })
        defender = _make_bare_unit(nation, 'infantry')
        _, _, details = calculate_damage(attacker, defender)
        # eff_fp should be 8 (3 base + 5 eq)
        assert details['eff_fp'] == pytest.approx(8.0)
