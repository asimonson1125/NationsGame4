"""XP thresholds and level-up logic for military units."""

import math
import random

MAX_LEVEL = 15

# Pre-compute XP thresholds: xp_for_next_level(1) = 100, each next = ceil(prev * 1.5)
_XP_THRESHOLDS = [None]  # index 0 unused (levels are 1-based)
_prev = 100
for _lv in range(1, MAX_LEVEL):
    _XP_THRESHOLDS.append(_prev)
    _prev = math.ceil(_prev * 1.5)
_XP_THRESHOLDS.append(None)  # level 15 (max) — no next level


def xp_for_next_level(level):
    """Return XP needed to advance from *level* to *level+1*.

    Returns None if the unit is already at MAX_LEVEL.
    """
    if level < 1 or level >= MAX_LEVEL:
        return None
    return _XP_THRESHOLDS[level]


def process_xp_gain(unit, xp_amount):
    """Add *xp_amount* to *unit*, processing any level-ups.

    Returns a list of ``(new_level, buff_description)`` tuples for each
    level gained.  Buffs are applied directly to the unit's innate stats.
    """
    if unit.level >= MAX_LEVEL:
        return []

    unit.xp += xp_amount
    level_ups = []

    while unit.level < MAX_LEVEL:
        needed = xp_for_next_level(unit.level)
        if needed is None or unit.xp < needed:
            break
        # Level up
        unit.xp -= needed
        unit.level += 1
        buff_desc = _apply_random_buff(unit)
        level_ups.append((unit.level, buff_desc))

    # Discard excess XP at max level
    if unit.level >= MAX_LEVEL:
        unit.xp = 0

    return level_ups


# Minimum unit level required to equip each rarity tier
RARITY_LEVEL_REQ = {
    'Common': 1,
    'Uncommon': 1,
    'Rare': 5,
    'Epic': 10,
    'Legendary': 15,
}


def can_equip_rarity(unit_level, rarity):
    """Return True if a unit at *unit_level* can equip equipment of *rarity*."""
    return unit_level >= RARITY_LEVEL_REQ.get(rarity, 1)


def _apply_random_buff(unit):
    """Apply a random stat buff on level-up. Returns a human-readable description."""
    choice = random.randint(0, 3)
    if choice == 0:
        unit.firepower += 1
        return '+1 Firepower'
    elif choice == 1:
        unit.armour += 1
        return '+1 Armour'
    elif choice == 2:
        unit.maneuver += 1
        return '+1 Maneuver'
    else:
        bonus = math.ceil(unit.max_hp * 0.10)
        unit.max_hp += bonus
        # Scale current HP proportionally so the unit doesn't appear damaged
        unit.hp += bonus
        return f'+{bonus} Max HP'
