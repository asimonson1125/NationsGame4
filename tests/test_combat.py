"""Tests for app/game/combat.py — combat engine."""
import random
import pytest
from app.game.combat import (
    _parse_fp_multiplier, _parse_armour_multiplier, _parse_damage_reduction,
    _parse_maneuver_reduction, _get_roll_multiplier, _get_defending_bonus,
    _get_effective_firepower, _get_effective_armour, _get_maneuver_buff,
    _has_ability, maneuver_roll, select_initiative, calculate_damage,
    _side_strength,
)
from app.game.units import UNIT_DEFS


# ── Helper: fake unit object ─────────────────────────────────────────────

class FakeUnit:
    """Minimal stand-in for a Unit model row."""
    _next_id = 1

    def __init__(self, unit_key, hp=None):
        self.id = FakeUnit._next_id
        FakeUnit._next_id += 1
        self.unit_key = unit_key
        udef = UNIT_DEFS[unit_key]
        self.firepower = udef.firepower
        self.armour = udef.armour
        self.maneuver = udef.maneuver
        self.max_hp = udef.max_hp
        self.hp = hp if hp is not None else udef.max_hp
        # Equipment slots (None = no equipment)
        self.weapon = None
        self.accessory = None
        self.armour_eq = None


# ── Ability parser tests ─────────────────────────────────────────────────

class TestAbilityParsers:
    def test_fp_multiplier_basic(self):
        mult, target = _parse_fp_multiplier('4x firepower against armour units')
        assert mult == 4
        assert target == 'Armour'

    def test_fp_multiplier_6x(self):
        mult, target = _parse_fp_multiplier('6x firepower against infantry units')
        assert mult == 6
        assert target == 'Infantry'

    def test_fp_multiplier_air(self):
        mult, target = _parse_fp_multiplier('4x firepower against air units')
        assert mult == 4
        assert target == 'Air'

    def test_fp_multiplier_special_forces(self):
        mult, target = _parse_fp_multiplier('4x firepower against special forces units')
        assert mult == 4
        assert target == 'Special Forces'

    def test_fp_multiplier_static(self):
        mult, target = _parse_fp_multiplier('6x firepower against static units')
        assert mult == 6
        assert target == 'Static'

    def test_fp_multiplier_no_match(self):
        mult, target = _parse_fp_multiplier('Reduces damage to friendly infantry units by 25%')
        assert mult is None

    def test_armour_multiplier(self):
        mult, target = _parse_armour_multiplier('4x armour against infantry units')
        assert mult == 4
        assert target == 'Infantry'

    def test_armour_multiplier_no_match(self):
        mult, target = _parse_armour_multiplier('4x firepower against armour units')
        assert mult is None

    def test_damage_reduction(self):
        frac, target = _parse_damage_reduction(
            'Reduces damage to friendly infantry units by 25% (max 2 per division)'
        )
        assert frac == 0.25
        assert target == 'Infantry'

    def test_damage_reduction_armour(self):
        frac, target = _parse_damage_reduction(
            'Reduces damage to friendly armour units by 25% (max 2 per division)'
        )
        assert frac == 0.25
        assert target == 'Armour'

    def test_damage_reduction_no_match(self):
        frac, target = _parse_damage_reduction('4x firepower against armour units')
        assert frac is None

    def test_maneuver_reduction(self):
        frac = _parse_maneuver_reduction(
            'Reduces maneuver of enemy units by 25% (max 2 per division)'
        )
        assert frac == 0.25

    def test_maneuver_reduction_no_match(self):
        frac = _parse_maneuver_reduction('4x firepower against armour units')
        assert frac is None

    def test_roll_multiplier_sniper(self):
        assert _get_roll_multiplier('sniper') == 3

    def test_roll_multiplier_infantry(self):
        assert _get_roll_multiplier('infantry') == 1

    def test_defending_bonus_national_guard(self):
        assert _get_defending_bonus('national_guard') == 1.5

    def test_defending_bonus_infantry(self):
        assert _get_defending_bonus('infantry') == 1.0


# ── Effective stat tests ─────────────────────────────────────────────────

class TestEffectiveStats:
    def test_at4_vs_armour_gets_4x_fp(self):
        at4 = FakeUnit('at4_infantry')
        tank = FakeUnit('m1a1_abrahms')
        eff = _get_effective_firepower(at4, tank)
        assert eff == at4.firepower * 4

    def test_at4_vs_infantry_no_bonus(self):
        at4 = FakeUnit('at4_infantry')
        inf = FakeUnit('infantry')
        eff = _get_effective_firepower(at4, inf)
        assert eff == at4.firepower

    def test_trench_vs_infantry_gets_6x_fp(self):
        trench = FakeUnit('trench_infantry')
        inf = FakeUnit('infantry')
        eff = _get_effective_firepower(trench, inf)
        assert eff == trench.firepower * 6

    def test_riot_cop_armour_vs_infantry(self):
        cop = FakeUnit('riot_cop')
        inf = FakeUnit('infantry')
        eff = _get_effective_armour(cop, inf)
        assert eff == cop.armour * 4

    def test_riot_cop_armour_vs_armour_no_bonus(self):
        cop = FakeUnit('riot_cop')
        tank = FakeUnit('m1a1_abrahms')
        eff = _get_effective_armour(cop, tank)
        assert eff == cop.armour

    def test_ac130_maneuver_buff(self):
        ac130 = FakeUnit('lockheed_ac_130')
        allies = [ac130, FakeUnit('infantry')]
        buff = _get_maneuver_buff(allies)
        assert buff == 4


# ── Maneuver roll tests ─────────────────────────────────────────────────

class TestManeuverRoll:
    def test_higher_maneuver_wins_more_often(self):
        """Unit with higher maneuver should win the roll more than 50% of the time."""
        random.seed(42)
        high = FakeUnit('lockheed_ac_130')  # maneuver 11
        low = FakeUnit('national_guard')     # maneuver 1
        wins = sum(1 for _ in range(1000) if maneuver_roll(high, low)[0] is high)
        assert wins > 700  # should be ~91%

    def test_equal_maneuver_roughly_fair(self):
        random.seed(42)
        a = FakeUnit('infantry')
        b = FakeUnit('infantry')
        wins = sum(1 for _ in range(1000) if maneuver_roll(a, b)[0] is a)
        assert 350 < wins < 650

    def test_sniper_roll_multiplier_helps(self):
        """Sniper with 3x roll multiplier should beat infantry (same base maneuver)."""
        random.seed(42)
        sniper = FakeUnit('sniper')    # maneuver 2, 3x roll
        inf = FakeUnit('infantry')      # maneuver 2, 1x roll
        wins = sum(1 for _ in range(1000) if maneuver_roll(sniper, inf)[0] is sniper)
        assert wins > 600  # should be ~75%

    def test_zero_maneuver_doesnt_crash(self):
        """Static units with maneuver 0 shouldn't cause division by zero."""
        # Fortified bunker has maneuver 1, but let's force 0
        a = FakeUnit('fortified_bunker')
        a.maneuver = 0
        b = FakeUnit('fortified_bunker')
        b.maneuver = 0
        first, second = maneuver_roll(a, b)
        assert first in (a, b)


# ── Initiative selection tests ──────────────────────────────────────────

class TestSelectInitiative:
    def test_returns_unit_from_pool(self):
        a = FakeUnit('infantry')
        b = FakeUnit('infantry')
        unit, side = select_initiative([a], [b])
        assert unit in (a, b)
        assert side in ('attacker', 'defender')

    def test_higher_maneuver_wins_more(self):
        """AC-130 (maneuver 11) should dominate initiative vs infantry (maneuver 2)."""
        random.seed(42)
        fast = FakeUnit('lockheed_ac_130')
        slow = FakeUnit('infantry')
        wins = sum(1 for _ in range(1000)
                   if select_initiative([fast], [slow])[0] is fast)
        assert wins > 700

    def test_equal_units_roughly_fair(self):
        """Two identical units should each win ~50% of the time."""
        random.seed(42)
        a = FakeUnit('infantry')
        b = FakeUnit('infantry')
        a_wins = sum(1 for _ in range(1000)
                     if select_initiative([a], [b])[0] is a)
        assert 350 < a_wins < 650

    def test_same_unit_can_win_consecutively(self):
        """With replacement: same unit can win back-to-back (25% for equal units)."""
        random.seed(42)
        a = FakeUnit('infantry')
        b = FakeUnit('infantry')
        consecutive = 0
        for _ in range(2000):
            w1, _ = select_initiative([a], [b])
            w2, _ = select_initiative([a], [b])
            if w1 is a and w2 is a:
                consecutive += 1
        # Expected ~25% of 2000 = 500, allow wide margin
        assert 300 < consecutive < 700

    def test_sniper_roll_multiplier_in_pool(self):
        """Sniper (3x roll) should dominate vs infantry (1x) at same base maneuver."""
        random.seed(42)
        sniper = FakeUnit('sniper')    # maneuver 2, 3x roll
        inf = FakeUnit('infantry')      # maneuver 2, 1x roll
        wins = sum(1 for _ in range(1000)
                   if select_initiative([sniper], [inf])[0] is sniper)
        assert wins > 600  # ~75%

    def test_many_units_picks_from_full_pool(self):
        """With multiple units per side, all should be selectable."""
        random.seed(42)
        atk = [FakeUnit('infantry') for _ in range(3)]
        dfn = [FakeUnit('infantry') for _ in range(3)]
        seen = set()
        for _ in range(500):
            unit, _ = select_initiative(atk, dfn)
            seen.add(unit.id)
        assert len(seen) == 6


# ── Damage calculation tests ────────────────────────────────────────────

class TestCalculateDamage:
    def test_returns_damage_hit_type_and_details(self):
        random.seed(42)
        a = FakeUnit('infantry')
        b = FakeUnit('infantry')
        dmg, hit_type, details = calculate_damage(a, b)
        assert isinstance(dmg, int)
        assert hit_type in ('critical', 'hit', 'graze', 'miss')
        assert isinstance(details, dict)
        assert details['hit_type'] == hit_type
        assert details['final_damage'] == dmg

    def test_details_contain_all_fields(self):
        random.seed(42)
        a = FakeUnit('infantry')
        b = FakeUnit('infantry')
        _, _, d = calculate_damage(a, b)
        expected_keys = {
            'base_fp', 'fp_type_mult', 'atk_def_bonus', 'eff_fp',
            'base_armour', 'armour_type_mult', 'def_bonus', 'eff_armour',
            'base_damage', 'variance', 'dmg_reduction_pct', 'dmg_after_reduction',
            'd100', 'atk_maneuver', 'def_maneuver', 'man_mod', 'final_roll',
            'hit_type', 'hit_mult', 'final_damage',
        }
        assert expected_keys.issubset(d.keys())

    def test_basic_damage_positive(self):
        """Without maneuver modifier, d100 is 1–100 so no misses possible."""
        random.seed(42)
        a = FakeUnit('infantry')
        b = FakeUnit('infantry')
        dmg, _, _ = calculate_damage(a, b)
        assert dmg >= 1

    def test_type_multiplier_increases_damage(self):
        """AT4 Infantry vs armour should deal more damage than vs infantry."""
        random.seed(42)
        at4 = FakeUnit('at4_infantry')
        tank = FakeUnit('m1a1_abrahms')
        inf = FakeUnit('infantry')

        dmg_vs_armour, _, _ = calculate_damage(at4, tank)
        random.seed(42)
        dmg_vs_infantry, _, _ = calculate_damage(at4, inf)
        assert dmg_vs_armour > dmg_vs_infantry

    def test_armour_multiplier_reduces_damage(self):
        """Riot cop should take less damage from infantry due to 4x armour."""
        random.seed(42)
        inf = FakeUnit('infantry')
        cop = FakeUnit('riot_cop')
        plain = FakeUnit('infantry')

        dmg_vs_cop, _, _ = calculate_damage(inf, cop)
        random.seed(42)
        dmg_vs_plain, _, _ = calculate_damage(inf, plain)
        assert dmg_vs_cop < dmg_vs_plain

    def test_medic_reduces_infantry_damage(self):
        """Medic support should reduce damage to infantry allies."""
        random.seed(42)
        attacker = FakeUnit('m1a1_abrahms')
        defender = FakeUnit('infantry')
        medic = FakeUnit('medic')
        medic.hp = 50  # alive

        dmg_with_medic, _, _ = calculate_damage(
            attacker, defender,
            defender_allies=[defender, medic],
        )
        random.seed(42)
        dmg_without, _, _ = calculate_damage(
            attacker, defender,
            defender_allies=[defender],
        )
        assert dmg_with_medic < dmg_without

    def test_defending_bonus_reduces_damage(self):
        """National Guard defending should take less damage."""
        random.seed(42)
        attacker = FakeUnit('infantry')
        ng = FakeUnit('national_guard')

        dmg_defending, _, _ = calculate_damage(attacker, ng, defender_is_defending=True)
        random.seed(42)
        dmg_attacking, _, _ = calculate_damage(attacker, ng, defender_is_defending=False)
        assert dmg_defending < dmg_attacking

    def test_defending_bonus_boosts_attacker_firepower(self):
        """A defending-side unit that wins initiative gets FP boost from AllStats."""
        random.seed(42)
        ng = FakeUnit('national_guard')  # 1.5x all stats while defending
        target = FakeUnit('infantry')

        dmg_defending, _, d1 = calculate_damage(ng, target, attacker_is_defending=True)
        random.seed(42)
        dmg_not_defending, _, d2 = calculate_damage(ng, target, attacker_is_defending=False)
        assert dmg_defending > dmg_not_defending
        assert d1['atk_def_bonus'] == 1.5
        assert d2['atk_def_bonus'] == 1.0

    def test_damage_always_at_least_one(self):
        """Even heavily armoured units should take at least 1 damage (non-miss)."""
        random.seed(42)
        weak = FakeUnit('medic')       # fp=1
        bunker = FakeUnit('fortified_bunker')  # armour=10
        dmg, hit_type, _ = calculate_damage(weak, bunker)
        # Without maneuver modifier, d100 is 1–100, can't be ≤0, so no miss
        assert dmg >= 1

    def test_miss_possible_with_maneuver_disadvantage(self):
        """Large negative maneuver modifier can cause a miss (finalRoll ≤ 0)."""
        misses = 0
        for i in range(200):
            random.seed(i)
            a = FakeUnit('infantry')
            b = FakeUnit('infantry')
            dmg, hit_type, details = calculate_damage(
                a, b, attacker_maneuver=1, defender_maneuver=200,
            )
            if hit_type == 'miss':
                misses += 1
                assert dmg == 0
                assert details['hit_mult'] == 0
        assert misses > 0  # at least some misses with huge disadvantage

    def test_critical_and_graze_exist(self):
        """Over many rolls, crits and grazes should both appear."""
        hit_types = set()
        for i in range(200):
            random.seed(i)
            a = FakeUnit('infantry')
            b = FakeUnit('infantry')
            _, ht, _ = calculate_damage(a, b)
            hit_types.add(ht)
        assert 'critical' in hit_types
        assert 'graze' in hit_types
        assert 'hit' in hit_types

    def test_damage_formula_coefficients(self):
        """Verify FP×10 − Armour×5 base damage (NG3 formula)."""
        # Infantry: fp=3, armour=1. Infantry vs Infantry:
        # base = 3*10 - 1*5 = 25, +rand(-4,+4), so range 21–29 before hit type
        random.seed(0)
        a = FakeUnit('infantry')
        b = FakeUnit('infantry')
        damages = []
        for i in range(500):
            random.seed(i)
            dmg, ht, _ = calculate_damage(a, b)
            if ht == 'hit':  # only check normal hits (no crit/graze multiplier)
                damages.append(dmg)
        # Normal hits should cluster around 21–29
        assert len(damages) > 0
        assert min(damages) >= 21
        assert max(damages) <= 29

    def test_damage_variance(self):
        """Repeated calculations should produce different values."""
        a = FakeUnit('gear_infantry')
        b = FakeUnit('infantry')
        damages = {calculate_damage(a, b)[0] for _ in range(50)}
        assert len(damages) > 1


class TestRetreatStrength:
    def test_strength_formula(self):
        """Strength = fp + armour + maneuver + hp//10."""
        u = FakeUnit('infantry')  # fp=3, armour=1, maneuver=2, hp=50
        assert _side_strength([u]) == 3 + 1 + 2 + 50 // 10  # = 11

    def test_strength_multiple_units(self):
        a = FakeUnit('infantry')
        b = FakeUnit('infantry')
        assert _side_strength([a, b]) == 2 * (3 + 1 + 2 + 50 // 10)
