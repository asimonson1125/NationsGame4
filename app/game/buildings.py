from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class BuildingDef:
    name: str
    unit_type: str = ''           # military buildings: matches UnitDef.unit_type
    unlock_tier: int = 1          # minimum nation tier to construct
    max_level: int = 1
    level_costs: List[Dict[str, float]] = field(default_factory=list)
    level_upgrade_time: List[int] = field(default_factory=list)  # minutes per level
    gp_per_level: List[int] = field(default_factory=list)
    factory_category: str = ''    # factory buildings: 'flora', 'fauna', or 'mined'
    level_max_tier: List[int] = field(default_factory=list)  # factory tier band ceiling per level


BUILDING_DEFS: Dict[str, BuildingDef] = {

    # ── MILITARY BUILDINGS ─────────────────────────────────────────────────

    'barracks': BuildingDef(
        name='Barracks',
        unit_type='Infantry',
        unlock_tier=1,
        max_level=4,
        level_costs=[
            {},  # Level 1 — seeded free on registration
            {'money': 25_000, 'building_materials': 1_000},
            {'money': 75_000, 'building_materials': 5_000, 'metal': 500},
            {'money': 150_000, 'building_materials': 10_000, 'metal': 2_500},
        ],
        level_upgrade_time=[0, 240, 720, 1440],
        gp_per_level=[5, 10, 15, 25],
    ),
    'special_forces_hq': BuildingDef(
        name='Special Forces HQ',
        unit_type='Special Forces',
        unlock_tier=2,
        max_level=4,
        level_costs=[
            {'money': 10_000, 'building_materials': 500},
            {'money': 30_000, 'building_materials': 2_000},
            {'money': 75_000, 'building_materials': 5_000, 'metal': 500},
            {'money': 200_000, 'building_materials': 10_000, 'metal': 2_500},
        ],
        level_upgrade_time=[120, 480, 960, 1920],
        gp_per_level=[5, 10, 20, 35],
    ),
    'armored_vehicle_factory': BuildingDef(
        name='Armored Vehicle Factory',
        unit_type='Armour',
        unlock_tier=3,
        max_level=5,
        level_costs=[
            {'money': 25_000, 'building_materials': 1_000, 'metal': 500},
            {'money': 50_000, 'building_materials': 5_000, 'metal': 1_000},
            {'money': 100_000, 'building_materials': 10_000, 'metal': 5_000},
            {'money': 250_000, 'building_materials': 25_000, 'metal': 10_000},
            {'money': 500_000, 'building_materials': 50_000, 'metal': 25_000},
        ],
        level_upgrade_time=[480, 1440, 2880, 5760, 10080],
        gp_per_level=[5, 15, 25, 40, 60],
    ),
    'artillery_defense_base': BuildingDef(
        name='Artillery & Defense Base',
        unit_type='Static',
        unlock_tier=3,
        max_level=5,
        level_costs=[
            {'money': 20_000, 'building_materials': 2_000, 'metal': 250},
            {'money': 50_000, 'building_materials': 5_000, 'metal': 1_000},
            {'money': 100_000, 'building_materials': 10_000, 'metal': 2_500},
            {'money': 200_000, 'building_materials': 25_000, 'metal': 5_000},
            {'money': 500_000, 'building_materials': 75_000, 'metal': 15_000},
        ],
        level_upgrade_time=[480, 1440, 2880, 5760, 10080],
        gp_per_level=[5, 15, 25, 40, 60],
    ),
    'airfield': BuildingDef(
        name='Airfield',
        unit_type='Air',
        unlock_tier=4,
        max_level=5,
        level_costs=[
            {'money': 50_000, 'building_materials': 5_000, 'metal': 1_000},
            {'money': 100_000, 'building_materials': 10_000, 'metal': 2_500, 'fuel': 500},
            {'money': 250_000, 'building_materials': 25_000, 'metal': 5_000, 'fuel': 2_500},
            {'money': 500_000, 'building_materials': 50_000, 'metal': 10_000, 'fuel': 5_000},
            {'money': 1_000_000, 'building_materials': 100_000, 'metal': 25_000, 'fuel': 10_000},
        ],
        level_upgrade_time=[1440, 2880, 5760, 10080, 20160],
        gp_per_level=[10, 20, 35, 55, 80],
    ),

    # ── FACTORY PREREQUISITE BUILDINGS ────────────────────────────────────
    # level_max_tier: the highest factory tier each level unlocks.
    # Bands: Lvl 1 → tier 1-2, Lvl 2 → tier 3-4, Lvl 3 → tier 5-6, Lvl 4 → tier 7+

    'botanical_research_station': BuildingDef(
        name='Botanical Research Station',
        factory_category='flora',
        unlock_tier=1,
        max_level=4,
        level_costs=[
            {'money': 5_000, 'building_materials': 500},
            {'money': 25_000, 'building_materials': 2_500},
            {'money': 100_000, 'building_materials': 10_000, 'metal': 500},
            {'money': 500_000, 'building_materials': 50_000, 'metal': 2_500},
        ],
        level_upgrade_time=[60, 480, 1440, 5760],
        gp_per_level=[3, 8, 18, 40],
        level_max_tier=[2, 4, 6, 10],
    ),
    'wildlife_ranch': BuildingDef(
        name='Wildlife Ranch',
        factory_category='fauna',
        unlock_tier=1,
        max_level=3,
        level_costs=[
            {'money': 5_000, 'building_materials': 500},
            {'money': 25_000, 'building_materials': 2_500},
            {'money': 100_000, 'building_materials': 10_000, 'metal': 500},
        ],
        level_upgrade_time=[60, 480, 1440],
        gp_per_level=[3, 8, 18],
        level_max_tier=[2, 4, 6],
    ),
    'mining_bureau': BuildingDef(
        name='Mining Bureau',
        factory_category='mined',
        unlock_tier=1,
        max_level=3,
        level_costs=[
            {'money': 5_000, 'building_materials': 500},
            {'money': 25_000, 'building_materials': 2_500},
            {'money': 100_000, 'building_materials': 10_000, 'metal': 500},
        ],
        level_upgrade_time=[60, 480, 1440],
        gp_per_level=[3, 8, 18],
        level_max_tier=[2, 4, 6],
    ),
}

# unit_type -> building_key (military buildings only)
_TYPE_TO_BUILDING = {
    bdef.unit_type: key for key, bdef in BUILDING_DEFS.items() if bdef.unit_type
}

# factory_category -> building_key (factory buildings only)
_CATEGORY_TO_BUILDING = {
    bdef.factory_category: key for key, bdef in BUILDING_DEFS.items() if bdef.factory_category
}


def building_for_unit_type(unit_type: str):
    """Return the building_key required for a unit type, or None."""
    return _TYPE_TO_BUILDING.get(unit_type)


def building_for_factory_category(category: str):
    """Return the building_key required for a factory category, or None."""
    return _CATEGORY_TO_BUILDING.get(category)


def required_level(building_key: str, tier: int) -> int:
    """Return the building level needed to access a unit or factory of the given tier.

    Military buildings use the unlock_tier offset formula.
    Factory buildings use level_max_tier bands.
    """
    bdef = BUILDING_DEFS.get(building_key)
    if not bdef:
        return 1
    if bdef.level_max_tier:
        for i, max_tier in enumerate(bdef.level_max_tier):
            if tier <= max_tier:
                return i + 1
        return len(bdef.level_max_tier)
    return tier - (bdef.unlock_tier - 1)


def units_unlocked_at_level(building_key: str, level: int) -> List[str]:
    """Return player-recruitable unit_keys unlocked at exactly this building level."""
    from .units import UNIT_DEFS
    bdef = BUILDING_DEFS.get(building_key)
    if not bdef or not bdef.unit_type:
        return []
    target_tier = bdef.unlock_tier + (level - 1)
    return [
        key for key, udef in UNIT_DEFS.items()
        if udef.unit_type == bdef.unit_type
        and udef.tier == target_tier
        and not udef.npc_only
    ]


def factories_unlocked_at_level(building_key: str, level: int) -> List[str]:
    """Return factory_keys unlocked at exactly this building level."""
    from .factories import FACTORY_DEFS
    bdef = BUILDING_DEFS.get(building_key)
    if not bdef or not bdef.factory_category or not bdef.level_max_tier:
        return []
    max_tier = bdef.level_max_tier[level - 1]
    min_tier = (bdef.level_max_tier[level - 2] + 1) if level > 1 else 1
    return [
        key for key, fdef in FACTORY_DEFS.items()
        if fdef.category == bdef.factory_category and min_tier <= fdef.tier <= max_tier
    ]
