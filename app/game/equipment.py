"""Equipment definitions, buff generation, and loot crate logic."""

import hashlib
import json
import random
import math

from .constants import CONTINENTS

# ── Equipment slots per unit category ─────────────────────────────────────
# Positions: [0]=weapon, [1]=accessory, [2]=armour
EQUIPMENT_SLOTS = {
    'Infantry':       ['Infantry Weapon', 'Infantry Accessory', 'Body Armour'],
    'Armour':         ['Heavy Accessory', 'Crew', 'Engine'],
    'Air':            ['Heavy Accessory', 'Ammunition', 'Engine'],
    'Static':         ['Heavy Accessory', 'Ammunition', 'Crew'],
    'Special Forces': ['Infantry Weapon', 'Infantry Accessory', 'Body Armour'],
}

# Slot position names — index matches EQUIPMENT_SLOTS position
_SLOT_NAMES = ['weapon', 'accessory', 'armour']

# All valid equipment type strings (deduplicated)
ALL_EQUIPMENT_TYPES = sorted(set(
    et for slots in EQUIPMENT_SLOTS.values() for et in slots
))

# Unit categories
UNIT_CATEGORIES = list(EQUIPMENT_SLOTS.keys())

# ── Rarity system ─────────────────────────────────────────────────────────
RARITY_ORDER = ['Common', 'Uncommon', 'Rare', 'Epic', 'Legendary']

RARITY_BUFF_POINTS = {
    'Common': 1,
    'Uncommon': 2,
    'Rare': 4,
    'Epic': 7,
    'Legendary': 10,
}

RARITY_DROP_RATES = {
    'Common': 0.40,
    'Uncommon': 0.35,
    'Rare': 0.20,
    'Epic': 0.04,
    'Legendary': 0.01,
}

FOIL_CHANCE = 0.05  # 5%

# ── Trade-in values ───────────────────────────────────────────────────────
TRADE_IN_VALUES = {
    'Common': 0,
    'Uncommon': 1,
    'Rare': 5,
    'Epic': 15,
    'Legendary': 40,
}

# ── Rarity display colors (Tailwind classes) ──────────────────────────────
RARITY_COLORS = {
    'Common':    {'bg': '', 'border': 'border-slate-600',    'text': 'text-slate-400',   'badge': 'bg-slate-700 text-slate-300'},
    'Uncommon':  {'bg': '', 'border': 'border-emerald-700',  'text': 'text-emerald-400', 'badge': 'bg-emerald-900/60 text-emerald-300'},
    'Rare':      {'bg': '', 'border': 'border-blue-700',     'text': 'text-blue-400',    'badge': 'bg-blue-900/60 text-blue-300'},
    'Epic':      {'bg': '', 'border': 'border-purple-700',   'text': 'text-purple-400',  'badge': 'bg-purple-900/60 text-purple-300'},
    'Legendary': {'bg': '', 'border': 'border-amber-600',    'text': 'text-amber-400',   'badge': 'bg-amber-900/60 text-amber-300'},
}

# ── Crate definitions ─────────────────────────────────────────────────────
CRATE_SIZES = {
    'small':  {'items': 1, 'cost': 1,  'guaranteed_rare': 0, 'guaranteed_epic': 0},
    'medium': {'items': 3, 'cost': 20, 'guaranteed_rare': 2, 'guaranteed_epic': 0},
    'epic':   {'items': 5, 'cost': 50, 'guaranteed_rare': 2, 'guaranteed_epic': 1},
}

# ── Buff types with weights (higher = more likely to repeat) ──────────────
# Each buff type: (key, buff_type_code, description_template, per_point_value)
_FLAT_BUFFS = [
    ('firepower', 'Firepower',  '+{val} Firepower', 1),
    ('armour',    'Armour',     '+{val} Armour',     1),
    ('maneuver',  'Maneuver',   '+{val} Maneuver',   1),
    ('hp',        'HP',         'x{val} HP',         0.1),  # per point adds 0.1x
]

_UNIT_TYPES_FOR_MULT = ['Infantry', 'Armour', 'Air', 'Static', 'Special Forces']


def _roll_rarity(min_rarity=None):
    """Roll a random rarity. If min_rarity is set, re-roll anything below it."""
    rarities = list(RARITY_DROP_RATES.keys())
    weights = list(RARITY_DROP_RATES.values())

    if min_rarity and min_rarity in RARITY_ORDER:
        min_idx = RARITY_ORDER.index(min_rarity)
        # Zero out weights for rarities below minimum
        for i in range(min_idx):
            weights[i] = 0
        # Renormalize
        total = sum(weights)
        if total > 0:
            weights = [w / total for w in weights]

    return random.choices(rarities, weights=weights, k=1)[0]


def generate_equipment(unit_category, rarity=None):
    """Generate a single piece of equipment for the given unit category.

    Returns dict: {equipment_type, rarity, is_foil, buffs: [{buff_type, value, description}]}
    """
    if rarity is None:
        rarity = _roll_rarity()

    slots = EQUIPMENT_SLOTS.get(unit_category, EQUIPMENT_SLOTS['Infantry'])
    equipment_type = random.choice(slots)

    is_foil = random.random() < FOIL_CHANCE

    base_points = RARITY_BUFF_POINTS[rarity]
    if is_foil:
        total_points = math.ceil(base_points * 1.5)
    else:
        total_points = base_points

    buffs = _generate_buffs(total_points, unit_category)

    return {
        'equipment_type': equipment_type,
        'rarity': rarity,
        'is_foil': is_foil,
        'buffs': buffs,
    }


def _generate_buffs(total_points, unit_category):
    """Generate buffs for equipment, tending to stack points on the same type."""
    if total_points <= 0:
        return []

    # Build pool of possible buff types
    buff_pool = []
    # Flat stat buffs (weight 4 each — most common)
    for key, btype, template, per_point in _FLAT_BUFFS:
        buff_pool.append((btype, template, per_point, 4.0))

    # Type multiplier buff: "1.25x firepower against <type> units" (weight 1.5 each)
    for utype in _UNIT_TYPES_FOR_MULT:
        desc = '{{val}}x firepower against {t} units'.format(t=utype)
        buff_pool.append(('FPvs_' + utype.replace(' ', '_'), desc, 0.25, 1.5))

    # Continent buff: "1.1x all stats in <continent>" (weight 1 each)
    for cont in CONTINENTS:
        desc = '{{val}}x all stats in {c}'.format(c=cont)
        buff_pool.append(('AllStats_' + cont.replace(' ', '_'), desc, 0.1, 1.0))

    # First point: pick randomly from pool
    types_list = [b[0] for b in buff_pool]
    weights = [b[3] for b in buff_pool]

    # Allocate points — tend to cluster on same buff type
    allocations = {}  # buff_index -> points
    current_idx = random.choices(range(len(buff_pool)), weights=weights, k=1)[0]
    allocations[current_idx] = 1

    for _ in range(total_points - 1):
        # 65% chance to add another point to the current type
        if random.random() < 0.65 and current_idx in allocations:
            allocations[current_idx] = allocations.get(current_idx, 0) + 1
        else:
            # Pick a new type (or same one again by chance)
            current_idx = random.choices(range(len(buff_pool)), weights=weights, k=1)[0]
            allocations[current_idx] = allocations.get(current_idx, 0) + 1

    # Convert allocations to buff dicts
    buffs = []
    for idx, points in allocations.items():
        btype, desc_template, per_point, _ = buff_pool[idx]

        if btype == 'HP':
            # HP is multiplicative: base 1.0 + per_point * points
            value = round(1.0 + per_point * points, 2)
            description = desc_template.format(val=value)
        elif btype.startswith('FPvs_'):
            # Multiplier: base 1.0 + 0.25 * points
            value = round(1.0 + per_point * points, 2)
            description = desc_template.format(val=value)
        elif btype.startswith('AllStats_'):
            # Continent multiplier: base 1.0 + 0.1 * points
            value = round(1.0 + per_point * points, 2)
            description = desc_template.format(val=value)
        else:
            # Flat stat: just points
            value = points
            description = desc_template.format(val=points)

        buffs.append({
            'buff_type': btype,
            'value': value,
            'description': description,
        })

    return buffs


def generate_crate_contents(crate_size, unit_category):
    """Generate all equipment items for a crate.

    Returns list of equipment dicts from generate_equipment().
    """
    crate = CRATE_SIZES.get(crate_size)
    if not crate:
        return []

    items = []
    guaranteed_epic = crate['guaranteed_epic']
    guaranteed_rare = crate['guaranteed_rare']
    normal_count = crate['items'] - guaranteed_epic - guaranteed_rare

    # Generate guaranteed epic+ items
    for _ in range(guaranteed_epic):
        rarity = _roll_rarity(min_rarity='Epic')
        items.append(generate_equipment(unit_category, rarity=rarity))

    # Generate guaranteed rare+ items
    for _ in range(guaranteed_rare):
        rarity = _roll_rarity(min_rarity='Rare')
        items.append(generate_equipment(unit_category, rarity=rarity))

    # Generate normal items
    for _ in range(normal_count):
        items.append(generate_equipment(unit_category))

    random.shuffle(items)
    return items


def get_slots_for_unit_type(unit_type):
    """Return the 3 compatible equipment type strings for a unit type."""
    return EQUIPMENT_SLOTS.get(unit_type, [])


def get_slot_category(equipment_type, unit_type):
    """Return 'weapon', 'accessory', or 'armour' based on position in the unit's slot list."""
    slots = EQUIPMENT_SLOTS.get(unit_type, [])
    try:
        idx = slots.index(equipment_type)
        return _SLOT_NAMES[idx]
    except (ValueError, IndexError):
        return 'weapon'


def get_unit_categories_for_equipment(equipment_type):
    """Return all unit categories that can use this equipment type."""
    return [cat for cat, slots in EQUIPMENT_SLOTS.items() if equipment_type in slots]


def serialize_buffs(buffs_list):
    """Canonically sort a list of buff dicts and return a JSON string.

    Each buff dict must have at least 'buff_type', 'value', 'description'.
    Sorting is by buff_type then value for deterministic output.
    """
    sorted_buffs = sorted(buffs_list, key=lambda b: (b['buff_type'], b['value']))
    return json.dumps(sorted_buffs, sort_keys=True, separators=(',', ':'))


def compute_buff_hash(buffs_list):
    """Compute SHA-256 hex digest of canonically-sorted buff JSON."""
    return hashlib.sha256(serialize_buffs(buffs_list).encode()).hexdigest()
