import json
import math
import re
import random
from datetime import datetime, timezone
from .units import UNIT_DEFS
from .equipment import EQUIPMENT_SLOTS
from .combat_logs import get_battle_log


# ── Ability parsers ───────────────────────────────────────────────────────

# Map "infantry units" -> "Infantry", "armour units" -> "Armour", etc.
_TYPE_NAMES = {
    'infantry': 'Infantry',
    'armour': 'Armour',
    'static': 'Static',
    'air': 'Air',
    'special forces': 'Special Forces',
}


def _parse_fp_multiplier(ability_text):
    """Parse 'Nx firepower against <type> units' -> (multiplier, target_type)."""
    m = re.match(r'(\d+)x firepower against (\w[\w\s]*?) units', ability_text, re.I)
    if m:
        mult = int(m.group(1))
        raw_type = m.group(2).strip().lower()
        target = _TYPE_NAMES.get(raw_type)
        if target:
            return mult, target
    return None, None


def _parse_armour_multiplier(ability_text):
    """Parse 'Nx armour against <type> units' -> (multiplier, target_type)."""
    m = re.match(r'(\d+)x armour against (\w[\w\s]*?) units', ability_text, re.I)
    if m:
        mult = int(m.group(1))
        raw_type = m.group(2).strip().lower()
        target = _TYPE_NAMES.get(raw_type)
        if target:
            return mult, target
    return None, None


def _parse_damage_reduction(ability_text):
    """Parse 'Reduces damage to friendly <type> units by N%' -> (fraction, target_type)."""
    m = re.match(r'Reduces damage to friendly (\w[\w\s]*?) units by (\d+)%', ability_text, re.I)
    if m:
        raw_type = m.group(1).strip().lower()
        pct = int(m.group(2))
        target = _TYPE_NAMES.get(raw_type)
        if target:
            return pct / 100, target
    return None, None


def _parse_maneuver_reduction(ability_text):
    """Parse 'Reduces maneuver of enemy units by N%' -> fraction."""
    m = re.match(r'Reduces maneuver of enemy units by (\d+)%', ability_text, re.I)
    if m:
        return int(m.group(1)) / 100
    return None


def _has_ability(unit_key, keyword):
    """Check if a unit definition has a special ability containing the keyword."""
    udef = UNIT_DEFS.get(unit_key)
    if not udef:
        return False
    return any(keyword.lower() in a.lower() for a in udef.special_abilities)


def _get_abilities(unit_key):
    """Get special abilities list for a unit key."""
    udef = UNIT_DEFS.get(unit_key)
    return udef.special_abilities if udef else []


# ── Equipment buff helpers ─────────────────────────────────────────────────

def _get_equipment_buffs(unit):
    """Collect all equipment buffs from a unit's three equipment slots.

    Returns a list of (buff_type, value) tuples.
    """
    buffs = []
    for eq in getattr(unit, 'equipment_items', []):
        for b in eq.buffs:
            buffs.append((b.buff_type, b.value))
    return buffs


def _sum_flat_buff(eq_buffs, stat_name):
    """Sum flat stat buffs (Firepower, Armour, Maneuver) from equipment."""
    return sum(val for bt, val in eq_buffs if bt == stat_name)


def _get_hp_multiplier(eq_buffs):
    """Get combined HP multiplier from equipment (multiplicative)."""
    mult = 1.0
    for bt, val in eq_buffs:
        if bt == 'HP':
            mult *= val
    return mult


def _get_fp_vs_multiplier(eq_buffs, target_type):
    """Get firepower multiplier against a specific unit type from equipment."""
    key = 'FPvs_' + target_type.replace(' ', '_')
    mult = 1.0
    for bt, val in eq_buffs:
        if bt == key:
            mult *= val
    return mult


def _get_continent_multiplier(eq_buffs, continent):
    """Get all-stats continent multiplier from equipment."""
    if not continent:
        return 1.0
    key = 'AllStats_' + continent.replace(' ', '_')
    mult = 1.0
    for bt, val in eq_buffs:
        if bt == key:
            mult *= val
    return mult


# ── Core combat ───────────────────────────────────────────────────────────

def _get_effective_firepower(attacker, defender, continent=None):
    """Get attacker's effective firepower, applying type-based multipliers and equipment."""
    fp = attacker.firepower
    defender_udef = UNIT_DEFS.get(defender.unit_key)
    defender_type = defender_udef.unit_type if defender_udef else ''

    # Equipment flat buff
    eq_buffs = _get_equipment_buffs(attacker)
    fp += _sum_flat_buff(eq_buffs, 'Firepower')

    for ability in _get_abilities(attacker.unit_key):
        mult, target = _parse_fp_multiplier(ability)
        if mult and target == defender_type:
            fp = fp * mult
            break  # only one fp multiplier applies

    # Equipment: firepower vs type multiplier
    fp *= _get_fp_vs_multiplier(eq_buffs, defender_type)

    # Equipment: continent multiplier
    fp *= _get_continent_multiplier(eq_buffs, continent)

    return fp


def _get_effective_armour(defender, attacker, continent=None):
    """Get defender's effective armour, applying type-based multipliers and equipment."""
    arm = defender.armour
    attacker_udef = UNIT_DEFS.get(attacker.unit_key)
    attacker_type = attacker_udef.unit_type if attacker_udef else ''

    # Equipment flat buff
    eq_buffs = _get_equipment_buffs(defender)
    arm += _sum_flat_buff(eq_buffs, 'Armour')

    for ability in _get_abilities(defender.unit_key):
        mult, target = _parse_armour_multiplier(ability)
        if mult and target == attacker_type:
            arm = arm * mult
            break

    # Equipment: continent multiplier
    arm *= _get_continent_multiplier(eq_buffs, continent)

    return arm


def _get_roll_multiplier(unit_key):
    """Get base roll multiplier (e.g. '3x base roll multiplier')."""
    for ability in _get_abilities(unit_key):
        m = re.match(r'(\d+)x base roll multiplier', ability, re.I)
        if m:
            return int(m.group(1))
    return 1


def _get_defending_bonus(unit_key):
    """Check for '1.5x all combat stats while defending' -> multiplier or 1.0."""
    for ability in _get_abilities(unit_key):
        m = re.match(r'([\d.]+)x all combat stats while defending', ability, re.I)
        if m:
            return float(m.group(1))
    return 1.0


def _get_damage_reduction(friendly_units, target_unit):
    """Sum damage reduction from support units (medics, repair trucks, etc.).
    Each ability capped at max 2 per division."""
    target_udef = UNIT_DEFS.get(target_unit.unit_key)
    target_type = target_udef.unit_type if target_udef else ''
    total_reduction = 0.0

    # Group support units by ability text to enforce max-2 cap
    support_counts = {}
    for unit in friendly_units:
        if unit.hp <= 0 or unit.id == target_unit.id:
            continue
        for ability in _get_abilities(unit.unit_key):
            frac, atype = _parse_damage_reduction(ability)
            if frac and atype == target_type:
                key = ability
                support_counts[key] = support_counts.get(key, 0) + 1
                if support_counts[key] <= 2:
                    total_reduction += frac

    return min(total_reduction, 0.75)  # cap at 75% reduction


def _get_maneuver_debuff(enemy_units):
    """Sum maneuver reduction from enemy support units (signals jammers).
    Each ability capped at max 2 per division."""
    total_reduction = 0.0
    support_counts = {}
    for unit in enemy_units:
        if unit.hp <= 0:
            continue
        for ability in _get_abilities(unit.unit_key):
            frac = _parse_maneuver_reduction(ability)
            if frac:
                key = ability
                support_counts[key] = support_counts.get(key, 0) + 1
                if support_counts[key] <= 2:
                    total_reduction += frac

    return min(total_reduction, 0.5)  # cap at 50%


def _get_maneuver_buff(friendly_units):
    """Get maneuver multiplier from AC-130 style buffs. Max 1 per division."""
    for unit in friendly_units:
        if unit.hp <= 0:
            continue
        for ability in _get_abilities(unit.unit_key):
            m = re.match(r'(\d+)x maneuver multiplier to friendly units', ability, re.I)
            if m:
                return int(m.group(1))
    return 1


def _effective_maneuver(unit, allies, enemies, is_defender=False, continent=None):
    """Compute a unit's effective maneuver weight for initiative selection."""
    man = unit.maneuver

    # Equipment flat maneuver buff
    eq_buffs = _get_equipment_buffs(unit)
    man += _sum_flat_buff(eq_buffs, 'Maneuver')

    # Roll multiplier (snipers get 3x)
    man *= _get_roll_multiplier(unit.unit_key)

    # Defending bonus (National Guard etc.)
    if is_defender:
        man *= _get_defending_bonus(unit.unit_key)

    # Friendly maneuver buff (AC-130)
    if allies:
        man *= _get_maneuver_buff(allies)

    # Enemy maneuver debuff (signals jammer)
    if enemies:
        man *= (1 - _get_maneuver_debuff(enemies))

    # Equipment: continent multiplier
    man *= _get_continent_multiplier(eq_buffs, continent)

    return max(man, 0.01)  # floor to avoid zero weight


def select_initiative(attacker_units, defender_units, continent=None):
    """Select one unit from the combined pool, weighted by effective maneuver.

    Returns (unit, side) where side is 'attacker' or 'defender'.
    Units are selected with replacement — any alive unit can win each tick.
    """
    candidates = []
    weights = []

    for unit in attacker_units:
        candidates.append((unit, 'attacker'))
        weights.append(_effective_maneuver(unit, attacker_units, defender_units,
                                           is_defender=False, continent=continent))

    for unit in defender_units:
        candidates.append((unit, 'defender'))
        weights.append(_effective_maneuver(unit, defender_units, attacker_units,
                                           is_defender=True, continent=continent))

    if not candidates:
        return None, None

    (unit, side), = random.choices(candidates, weights=weights, k=1)
    return unit, side


def maneuver_roll(unit_a, unit_b, a_allies=None, b_allies=None,
                  a_is_defender=False, b_is_defender=False):
    """Returns (first_attacker, second_attacker) based on maneuver stats.

    Legacy two-unit initiative roll — kept for backwards compatibility.
    The battle engine now uses select_initiative() for pool-wide selection.
    """
    man_a = _effective_maneuver(unit_a, a_allies, b_allies, is_defender=a_is_defender)
    man_b = _effective_maneuver(unit_b, b_allies, a_allies, is_defender=b_is_defender)

    total = man_a + man_b
    if total == 0:
        return (unit_a, unit_b) if random.random() < 0.5 else (unit_b, unit_a)

    roll = random.random() * total
    if roll < man_a:
        return unit_a, unit_b
    return unit_b, unit_a


def calculate_damage(attacker, defender, attacker_allies=None, defender_allies=None,
                     attacker_is_defending=False, defender_is_defending=False,
                     attacker_maneuver=None, defender_maneuver=None,
                     defender_continent=None):
    """Calculate damage dealt by attacker to defender.

    Returns (damage, hit_type, details) where:
      - damage: final int damage
      - hit_type: 'critical', 'hit', 'graze', or 'miss'
      - details: dict with every intermediate value for the combat log

    NG3 formula: base damage = FP×10 − Armour×5 + rand(-4,+4).
    A d100 hit roll modified by maneuver differential determines hit type:
    critical (≥90, ×1.5), normal (11–89), graze (1–10, ×0.5), miss (≤0, 0).
    """
    base_fp = attacker.firepower
    base_armour = defender.armour

    # Effective firepower (with type multiplier + equipment)
    eff_fp = _get_effective_firepower(attacker, defender, continent=defender_continent)
    fp_type_mult = eff_fp / base_fp if base_fp else 1

    # AllStatsMultiplier — defending bonus applies to ALL stats of the
    # defending-side unit, including firepower when that unit wins initiative.
    atk_def_bonus = _get_defending_bonus(attacker.unit_key) if attacker_is_defending else 1.0
    eff_fp *= atk_def_bonus

    # Effective armour (with type multiplier + defending bonus + equipment)
    eff_armour_raw = _get_effective_armour(defender, attacker, continent=defender_continent)
    armour_type_mult = eff_armour_raw / base_armour if base_armour else 1
    def_bonus = _get_defending_bonus(defender.unit_key) if defender_is_defending else 1.0
    eff_armour = eff_armour_raw * def_bonus

    # Base damage: NG3 formula
    base_damage = (eff_fp * 10) - (eff_armour * 5)
    variance = random.randint(-4, 4)
    damage = base_damage + variance

    # Damage reduction from support units (applied before hit type, matching NG3)
    dmg_red = 0.0
    if defender_allies:
        dmg_red = _get_damage_reduction(defender_allies, defender)
        damage *= (1 - dmg_red)
    dmg_after_reduction = damage

    # Hit roll: d100 + maneuver differential
    d100 = random.randint(1, 100)
    atk_man = attacker_maneuver or 0
    def_man = defender_maneuver or 0
    man_mod = atk_man - def_man
    final_roll = d100 + man_mod

    if final_roll >= 90:
        hit_type = 'critical'
        hit_mult = 1.5
        damage = int(damage * 1.5)
        final_damage = max(1, damage)
    elif final_roll <= 0:
        hit_type = 'miss'
        hit_mult = 0
        final_damage = 0
    elif final_roll <= 10:
        hit_type = 'graze'
        hit_mult = 0.5
        damage = int(damage * 0.5)
        final_damage = max(1, damage)
    else:
        hit_type = 'hit'
        hit_mult = 1.0
        final_damage = max(1, int(damage))

    details = {
        'base_fp': base_fp,
        'fp_type_mult': round(fp_type_mult, 2),
        'atk_def_bonus': round(atk_def_bonus, 2),
        'eff_fp': round(eff_fp, 2),
        'base_armour': base_armour,
        'armour_type_mult': round(armour_type_mult, 2),
        'def_bonus': round(def_bonus, 2),
        'eff_armour': round(eff_armour, 2),
        'base_damage': round(base_damage, 2),
        'variance': variance,
        'dmg_reduction_pct': round(dmg_red * 100, 1),
        'dmg_after_reduction': round(dmg_after_reduction, 2),
        'd100': d100,
        'atk_maneuver': round(atk_man, 2),
        'def_maneuver': round(def_man, 2),
        'man_mod': round(man_mod, 2),
        'final_roll': round(final_roll, 2),
        'hit_type': hit_type,
        'hit_mult': hit_mult,
        'final_damage': final_damage,
    }

    return final_damage, hit_type, details


def _side_strength(units):
    """NG3 strength formula: sum of effective stats + hp/10 for alive units."""
    return sum(u.effective_firepower + u.effective_armour + u.effective_maneuver + u.hp // 10
               for u in units)


def process_battle_round(battle, db_session):
    """Process one combat tick — one unit wins initiative and attacks one enemy.

    All alive units from both sides are pooled. A maneuver-weighted random
    selection picks the initiative winner, who then attacks a random enemy.
    No retaliation. Units are selected with replacement across ticks, so the
    same unit can act on consecutive ticks.

    Retreat: if one side's strength drops below 1/3 of the other's, there
    is a 50% chance per tick that the weaker side retreats.
    """
    from ..models import Unit, CombatReport

    # Get battle location for equipment continent buffs
    defender_continent = getattr(battle, 'location', '') or ''

    # Query ALL units (including dead) to build stable indices, then filter alive
    all_atk = Unit.query.filter_by(division_id=battle.attacker_division_id, nation_id=battle.attacker_nation_id).order_by(Unit.division_joined_at, Unit.id).all()
    all_def = Unit.query.filter_by(division_id=battle.defender_division_id, nation_id=battle.defender_nation_id).order_by(Unit.division_joined_at, Unit.id).all()
    attacker_units = [u for u in all_atk if u.hp > 0]
    defender_units = [u for u in all_def if u.hp > 0]

    # Build unit index maps (1-based, stable across the whole battle)
    atk_div_name = battle.attacker_division_name or ''
    def_div_name = battle.defender_division_name or ''
    _unit_idx = {}
    for i, u in enumerate(all_atk, 1):
        udef = UNIT_DEFS.get(u.unit_key)
        base = udef.name if udef else u.unit_key
        name = u.custom_name if u.custom_name else base
        _unit_idx[u.id] = f"{name} ({atk_div_name}-{i})"
    for i, u in enumerate(all_def, 1):
        udef = UNIT_DEFS.get(u.unit_key)
        base = udef.name if udef else u.unit_key
        name = u.custom_name if u.custom_name else base
        _unit_idx[u.id] = f"{name} ({def_div_name}-{i})"

    reports = []
    now = datetime.now(timezone.utc)

    # Check for battle end — no units left
    if not attacker_units:
        battle.status = 'finished'
        battle.winner = 'defender'
        battle.finished_at = now
        _end_battle(battle, db_session)
        msg = f"Battle over! Defender ({battle.defender_nation_name or battle.defender_nation.name}) wins!"
        reports.append(msg)
        db_session.add(CombatReport(battle_id=battle.id, attacker_nation_id=battle.attacker_nation_id, message=msg, created_at=now))
        return reports

    if not defender_units:
        battle.status = 'finished'
        battle.winner = 'attacker'
        battle.finished_at = now
        _end_battle(battle, db_session)
        msg = f"Battle over! Attacker ({battle.attacker_nation_name or battle.attacker_nation.name}) wins!"
        reports.append(msg)
        db_session.add(CombatReport(battle_id=battle.id, attacker_nation_id=battle.attacker_nation_id, message=msg, created_at=now))
        return reports

    # Retreat check — weaker side flees if strength < opponent / 3
    atk_str = _side_strength(attacker_units)
    def_str = _side_strength(defender_units)

    if def_str < atk_str / 3 and random.random() < 0.5:
        battle.status = 'finished'
        battle.winner = 'attacker'
        battle.finished_at = now
        _end_battle(battle, db_session)
        msg = f"Defender retreats! {battle.attacker_nation_name or battle.attacker_nation.name} wins!"
        reports.append(msg)
        db_session.add(CombatReport(battle_id=battle.id, attacker_nation_id=battle.attacker_nation_id, message=msg, created_at=now))
        return reports

    if atk_str < def_str / 3 and random.random() < 0.5:
        battle.status = 'finished'
        battle.winner = 'defender'
        battle.finished_at = now
        _end_battle(battle, db_session)
        msg = f"Attacker retreats! {battle.defender_nation_name or battle.defender_nation.name} wins!"
        reports.append(msg)
        db_session.add(CombatReport(battle_id=battle.id, attacker_nation_id=battle.attacker_nation_id, message=msg, created_at=now))
        return reports

    # Select initiative winner from the combined pool
    init_unit, init_side = select_initiative(attacker_units, defender_units,
                                             continent=defender_continent)

    # Pick a random target from the opposing side
    if init_side == 'attacker':
        target = random.choice(defender_units)
        init_is_defending = False
        target_is_defending = True
        init_allies = attacker_units
        target_allies = defender_units
    else:
        target = random.choice(attacker_units)
        init_is_defending = True
        target_is_defending = False
        init_allies = defender_units
        target_allies = attacker_units

    init_name = _unit_idx.get(init_unit.id, init_unit.unit_key)
    target_name = _unit_idx.get(target.id, target.unit_key)

    # Compute effective maneuver for hit roll modifier
    init_man = _effective_maneuver(init_unit, init_allies, target_allies,
                                   is_defender=init_is_defending,
                                   continent=defender_continent)
    target_man = _effective_maneuver(target, target_allies, init_allies,
                                     is_defender=target_is_defending,
                                     continent=defender_continent)

    # Single attack — no retaliation
    dmg, hit_type, calc_details = calculate_damage(
        init_unit, target,
        attacker_allies=init_allies, defender_allies=target_allies,
        attacker_is_defending=init_is_defending,
        defender_is_defending=target_is_defending,
        attacker_maneuver=init_man, defender_maneuver=target_man,
        defender_continent=defender_continent,
    )
    target.hp = max(0, target.hp - dmg)

    # Add unit identity to details for the combat log popup
    calc_details['attacker'] = init_name
    calc_details['target'] = target_name
    details_json = json.dumps(calc_details)

    init_udef = UNIT_DEFS.get(init_unit.unit_key)
    target_udef = UNIT_DEFS.get(target.unit_key)
    init_type = init_udef.unit_type if init_udef else 'Any'
    target_type = target_udef.unit_type if target_udef else 'Any'

    msg = get_battle_log(
        attacker_name=init_name,
        attacker_type=init_type,
        target_name=target_name,
        target_type=target_type,
        hit_type=hit_type,
        damage=dmg,
        target_hp=target.hp,
        target_max_hp=target.effective_max_hp
    )

    if target.hp <= 0:
        msg += f" — {target_name} has been destroyed!"

    reports.append(msg)
    db_session.add(CombatReport(battle_id=battle.id, attacker_nation_id=battle.attacker_nation_id, message=msg, details=details_json, created_at=now))

    if target.hp <= 0:
        # Check if the opposing side is wiped out — end battle immediately
        if init_side == 'attacker':
            remaining = [u for u in defender_units if u.hp > 0]
        else:
            remaining = [u for u in attacker_units if u.hp > 0]

        if not remaining:
            winner = 'attacker' if init_side == 'attacker' else 'defender'
            winner_name = (battle.attacker_nation_name or battle.attacker_nation.name) if winner == 'attacker' else (battle.defender_nation_name or battle.defender_nation.name)
            battle.status = 'finished'
            battle.winner = winner
            battle.finished_at = now
            _end_battle(battle, db_session)
            msg = f"Battle over! {winner_name} wins!"
            reports.append(msg)
            db_session.add(CombatReport(battle_id=battle.id, attacker_nation_id=battle.attacker_nation_id, message=msg, created_at=now))

    return reports


def _snapshot_units(units):
    """Serialize unit state to a JSON-friendly list of dicts.

    Captures base stats, effective (equipment-boosted) stats, equipment
    details, and abilities so the battle detail popup can render fully
    from snapshot data alone.
    """
    result = []
    for u in units:
        udef = UNIT_DEFS.get(u.unit_key)

        # Equipment slot snapshots
        slots = []
        if udef:
            slot_types = EQUIPMENT_SLOTS.get(udef.unit_type, [])
            slot_names = ['weapon', 'accessory', 'armour']
            slot_labels = ['Weapon', 'Accessory', 'Armour']
            equipped_map = {
                'weapon': getattr(u, 'weapon', None),
                'accessory': getattr(u, 'accessory', None),
                'armour': getattr(u, 'armour_eq', None),
            }
            for stype, sname, slabel in zip(slot_types, slot_names, slot_labels):
                eq = equipped_map.get(sname)
                eq_data = None
                if eq:
                    eq_data = {
                        'equipment_type': eq.equipment_type,
                        'rarity': eq.rarity,
                        'is_foil': eq.is_foil,
                        'buffs': [
                            {'buff_type': b.buff_type, 'value': b.value,
                             'description': b.description}
                            for b in eq.buffs
                        ],
                    }
                slots.append({'label': slabel, 'type': stype, 'equipped': eq_data})

        # Equipment abilities
        eq_abilities = []
        for eq in getattr(u, 'equipment_items', []):
            for buff in eq.buffs:
                if buff.buff_type.startswith('FPvs_') or buff.buff_type.startswith('AllStats_'):
                    eq_abilities.append(buff.description)

        hp_mult = u._eq_hp_multiplier() if hasattr(u, '_eq_hp_multiplier') else 1.0

        result.append({
            'unit_key': u.unit_key,
            'custom_name': u.custom_name or '',
            'level': getattr(u, 'level', 1),
            'xp': getattr(u, 'xp', 0),
            'hp': u.hp,
            'max_hp': u.max_hp,
            'firepower': u.firepower,
            'armour': u.armour,
            'maneuver': u.maneuver,
            'effective_firepower': u.effective_firepower,
            'effective_armour': u.effective_armour,
            'effective_maneuver': u.effective_maneuver,
            'effective_max_hp': u.effective_max_hp,
            'hp_mult': hp_mult,
            'eq_abilities': eq_abilities,
            'slots': slots,
        })
    return result


def _destroy_unit_equipment(unit, db_session):
    """Destroy equipment equipped on a destroyed unit.

    Decrements each equipped item's count by 1 and deletes the Equipment
    row entirely if the count reaches zero.
    """
    from ..models import Equipment
    for eq_id in (unit.weapon_id, unit.accessory_id, unit.armour_eq_id):
        if eq_id:
            eq = db_session.get(Equipment, (eq_id, unit.nation_id))
            if eq:
                eq.count -= 1
                if eq.count <= 0:
                    db_session.delete(eq)


def _initial_strength(units):
    """Compute a division's full strength (all units at max HP) for loot token calculation."""
    return sum(
        u.effective_firepower + u.effective_armour + u.effective_maneuver + u.effective_max_hp // 10
        for u in units
    )


def _destroyed_unit_names(units):
    """Return a list of display names for destroyed units (hp <= 0)."""
    names = []
    for u in units:
        if u.hp <= 0:
            udef = UNIT_DEFS.get(u.unit_key)
            name = udef.name if udef else u.unit_key
            if u.custom_name:
                name = f'{u.custom_name} ({name})'
            names.append(name)
    return names


def _battle_message(div_name, enemy_name, battle_id, is_victory,
                    tokens=0, destroyed_names=None, mission_rewards=None,
                    level_ups=None):
    """Build the HTML body for a battle result system message."""
    link = (f'<a href="/military/battle/{battle_id}" '
            f'class="text-amber-400 hover:text-amber-300 underline">'
            f'View Battle Details</a>')

    if is_victory:
        lines = [
            f'Your division "{div_name}" was victorious against {enemy_name}!',
            '',
            f'Loot tokens earned: {tokens:,}',
        ]
        if mission_rewards:
            lines.append('')
            lines.append('Mission rewards ready to collect:')
            for res, amt in mission_rewards.items():
                lines.append(f'  \u2022 {int(amt):,} {res.replace("_", " ")}')
        if level_ups:
            lines.append('')
            lines.append('Level ups:')
            for name, ups in level_ups.items():
                for lvl, buff in ups:
                    lines.append(f'  \u2022 {name} reached Lv.{lvl}! ({buff})')
    else:
        lines = [
            f'Your division "{div_name}" was defeated by {enemy_name}.',
        ]

    if destroyed_names:
        lines.append('')
        lines.append('Units destroyed:')
        for name in destroyed_names:
            lines.append(f'  \u2022 {name}')

    lines.append('')
    lines.append(link)
    return '\n'.join(lines)


def _send_battle_notifications(battle, atk_units, def_units, db_session,
                               level_ups=None):
    """Send system mail to battle participants and grant loot tokens to the winner."""
    from ..models import Message, Nation

    is_pve = battle.battle_type in ('peacekeeping', 'pve_mission')
    winner_side = battle.winner  # 'attacker' or 'defender'

    atk_nation = db_session.get(Nation, battle.attacker_nation_id)
    def_nation = db_session.get(Nation, battle.defender_nation_id)
    atk_div_name = battle.attacker_division_name or 'Your division'
    def_div_name = battle.defender_division_name or 'Enemy division'
    atk_nation_display = battle.attacker_nation_name or atk_nation.name
    def_nation_display = battle.defender_nation_name or def_nation.name

    atk_strength = _initial_strength(atk_units)
    def_strength = _initial_strength(def_units)
    atk_destroyed = _destroyed_unit_names(atk_units)
    def_destroyed = _destroyed_unit_names(def_units)

    # Split level_ups by side for the correct notification
    atk_level_ups = {}
    def_level_ups = {}
    if level_ups:
        atk_ids = {u.id for u in atk_units}
        for uid, ups in level_ups.items():
            # Find the display name for this unit
            unit = next((u for u in atk_units + def_units if u.id == uid), None)
            if not unit:
                continue
            udef = UNIT_DEFS.get(unit.unit_key)
            name = unit.custom_name or (udef.name if udef else unit.unit_key)
            if uid in atk_ids:
                atk_level_ups.setdefault(name, []).extend(ups)
            else:
                def_level_ups.setdefault(name, []).extend(ups)

    # Look up mission rewards for pve_mission battles
    mission_rewards = None
    mission_name = None
    if battle.battle_type == 'pve_mission' and battle.mission_offer_id and winner_side == 'attacker':
        from ..models import MissionOffer
        from .missions import MISSION_DEFS
        offer = db_session.get(MissionOffer, battle.mission_offer_id)
        if offer:
            mdef = MISSION_DEFS.get(offer.mission_key)
            if mdef:
                mission_rewards = mdef.rewards
                mission_name = mdef.name

    # --- Attacker notification ---
    if winner_side == 'attacker':
        tokens = math.ceil(def_strength / 25)
        atk_nation.loot_tokens = (atk_nation.loot_tokens or 0) + tokens
        subject = f'Victory \u2014 {mission_name}' if mission_name else f'Victory \u2014 {atk_div_name}'
        body = _battle_message(atk_div_name, def_nation_display, battle.id,
                               is_victory=True, tokens=tokens,
                               destroyed_names=atk_destroyed,
                               mission_rewards=mission_rewards,
                               level_ups=atk_level_ups or None)
    else:
        subject = f'Defeat \u2014 {atk_div_name}'
        body = _battle_message(atk_div_name, def_nation_display, battle.id,
                               is_victory=False,
                               destroyed_names=atk_destroyed)

    db_session.add(Message(
        sender_id=None,
        recipient_id=battle.attacker_nation_id,
        subject=subject,
        body=body,
        message_type='system',
    ))

    # --- Defender notification (PvP only) ---
    if not is_pve:
        if winner_side == 'defender':
            tokens = math.ceil(atk_strength / 5)
            def_nation.loot_tokens = (def_nation.loot_tokens or 0) + tokens
            subject = f'Victory \u2014 {def_div_name}'
            body = _battle_message(def_div_name, atk_nation_display, battle.id,
                                   is_victory=True, tokens=tokens,
                                   destroyed_names=def_destroyed,
                                   level_ups=def_level_ups or None)
        else:
            subject = f'Defeat \u2014 {def_div_name}'
            body = _battle_message(def_div_name, atk_nation_display, battle.id,
                                   is_victory=False,
                                   destroyed_names=def_destroyed)

        db_session.add(Message(
            sender_id=None,
            recipient_id=battle.defender_nation_id,
            subject=subject,
            body=body,
            message_type='system',
        ))


def _end_battle(battle, db_session):
    """Clean up after battle ends — snapshot unit state, disband destroyed."""
    from ..models import Division, Unit, Nation
    from .levels import process_xp_gain

    # Query both sides' units
    atk_units = Unit.query.filter_by(division_id=battle.attacker_division_id, nation_id=battle.attacker_nation_id).order_by(Unit.division_joined_at, Unit.id).all()
    def_units = Unit.query.filter_by(division_id=battle.defender_division_id, nation_id=battle.defender_nation_id).order_by(Unit.division_joined_at, Unit.id).all()

    # Snapshot BEFORE XP/level-ups so the battle detail shows the state
    # units were actually in during the fight
    battle.attacker_snapshot = json.dumps(_snapshot_units(atk_units))
    battle.defender_snapshot = json.dumps(_snapshot_units(def_units))

    # Award XP to surviving winners (after snapshot)
    level_ups = {}  # {unit_id: [(level, buff_desc), ...]}
    winner_side = battle.winner  # 'attacker' or 'defender'
    if winner_side == 'attacker':
        winners = [u for u in atk_units if u.hp > 0]
        losers = def_units
    else:
        winners = [u for u in def_units if u.hp > 0]
        losers = atk_units

    xp_per_unit = _initial_strength(losers) // 10
    if xp_per_unit > 0:
        for unit in winners:
            ups = process_xp_gain(unit, xp_per_unit)
            if ups:
                level_ups[unit.id] = ups

    # Send notifications and grant loot tokens (before units are deleted)
    _send_battle_notifications(battle, atk_units, def_units, db_session,
                               level_ups=level_ups or None)

    # Resolve mission rewards before NPC cleanup
    if battle.battle_type == 'pve_mission' and battle.mission_offer_id:
        _resolve_mission(battle, db_session)

    # For PvE variants, the NPC defender division is disposable — delete it entirely
    is_pve = battle.battle_type in ('peacekeeping', 'pve_mission')

    # Destroy destroyed units (reduce military GP, destroy equipment)
    for unit in atk_units:
        if unit.hp <= 0:
            nation = db_session.get(Nation, unit.nation_id)
            udef = UNIT_DEFS.get(unit.unit_key)
            if nation and udef:
                nation.military_gp = max(0, (nation.military_gp or 0) - udef.gp_value)
            _destroy_unit_equipment(unit, db_session)
            db_session.delete(unit)

    if is_pve:
        # Delete all NPC units and the NPC division — no FK constraint on division IDs
        for unit in def_units:
            db_session.delete(unit)
        def_div = db_session.get(Division, (battle.defender_division_id, battle.defender_nation_id))
        if def_div:
            db_session.delete(def_div)
    else:
        for unit in def_units:
            if unit.hp <= 0:
                nation = db_session.get(Nation, unit.nation_id)
                udef = UNIT_DEFS.get(unit.unit_key)
                if nation and udef:
                    nation.military_gp = max(0, (nation.military_gp or 0) - udef.gp_value)
                _destroy_unit_equipment(unit, db_session)
                db_session.delete(unit)
        def_div = db_session.get(Division, (battle.defender_division_id, battle.defender_nation_id))
        if def_div:
            def_div.in_combat = False

    atk_div = db_session.get(Division, (battle.attacker_division_id, battle.attacker_nation_id))
    if atk_div:
        atk_div.in_combat = False

    # Credit war victories for pvp battles
    if battle.battle_type == 'pvp' and battle.winner:
        _credit_war_victory(battle, db_session)


def _credit_war_victory(battle, db_session):
    """If this pvp battle is part of a war, credit the victory and notify participants."""
    from ..models import WarBattle, War, Message
    from .war import credit_war_victory, compute_war_scores

    wb = WarBattle.query.filter_by(
        battle_id=battle.id, attacker_nation_id=battle.attacker_nation_id
    ).first()
    if not wb:
        return

    war = db_session.get(War, wb.war_id)
    if not war or war.status != 'active':
        return

    credit_war_victory(war, wb, battle.winner)

    link = (f'<a href="/war/{war.id}" class="text-amber-400 hover:text-amber-300 underline">'
            f'View War</a>')
    winner_nation_id = (battle.attacker_nation_id if battle.winner == 'attacker'
                        else battle.defender_nation_id)
    loser_nation_id = (battle.defender_nation_id if battle.winner == 'attacker'
                       else battle.attacker_nation_id)
    battle_link = (f'<a href="/military/battle/{battle.id}" '
                   f'class="text-amber-400 hover:text-amber-300 underline">View Battle</a>')

    db_session.add(Message(
        sender_id=None,
        recipient_id=winner_nation_id,
        subject=f'Battle Victory — {war.name}',
        body=f'You won a battle in the war "{war.name}".\n\n{battle_link} | {link}',
        message_type='system',
    ))
    db_session.add(Message(
        sender_id=None,
        recipient_id=loser_nation_id,
        subject=f'Battle Defeat — {war.name}',
        body=f'You lost a battle in the war "{war.name}".\n\n{battle_link} | {link}',
        message_type='system',
    ))

    # Notify if a settlement threshold has been crossed
    scores = compute_war_scores(war)
    if scores['attacker_can_demand'] and war.attacker_victories == 3 and war.defender_victories == 0:
        db_session.add(Message(
            sender_id=None,
            recipient_id=war.attacker_nation_id,
            subject=f'Settlement Available — {war.name}',
            body=f'You now lead by 3+ victories and may demand war compensation or annexation.\n\n{link}',
            message_type='system',
        ))
    if scores['defender_can_demand'] and war.defender_victories == 3 and war.attacker_victories == 0:
        db_session.add(Message(
            sender_id=None,
            recipient_id=war.defender_nation_id,
            subject=f'Settlement Available — {war.name}',
            body=f'You now lead by 3+ victories and may demand war compensation or annexation.\n\n{link}',
            message_type='system',
        ))


def _resolve_mission(battle, db_session):
    """Mark mission offer as completed/failed on a pve_mission battle end.

    Rewards are not granted here — the player must click Collect to claim them.
    """
    from ..models import MissionOffer
    from datetime import datetime, timezone

    offer = db_session.get(MissionOffer, battle.mission_offer_id)
    if not offer:
        return

    now = datetime.now(timezone.utc)
    offer.status = 'completed' if battle.winner == 'attacker' else 'failed'
    offer.completed_at = now
