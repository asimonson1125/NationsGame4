from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class BuildingDef:
    name: str
    unit_type: str          # matches UnitDef.unit_type
    unlock_tier: int        # minimum nation tier to construct
    max_level: int
    level_costs: List[Dict[str, float]]   # index i = cost to reach level i+1
    level_upgrade_time: List[int]         # minutes per level (same indices)
    gp_per_level: List[int]               # GP awarded when reaching each level


BUILDING_DEFS: Dict[str, BuildingDef] = {
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
}

# unit_type -> building_key lookup
_TYPE_TO_BUILDING = {bdef.unit_type: key for key, bdef in BUILDING_DEFS.items()}


def building_for_unit_type(unit_type: str):
    """Return the building_key required for a unit type, or None."""
    return _TYPE_TO_BUILDING.get(unit_type)


def required_level(building_key: str, unit_tier: int) -> int:
    """Compute the minimum building level needed to recruit a unit of the given tier."""
    bdef = BUILDING_DEFS.get(building_key)
    if not bdef:
        return 1
    return unit_tier - (bdef.unlock_tier - 1)


def units_unlocked_at_level(building_key: str, level: int) -> List[str]:
    """Return unit_keys (player-recruitable only) unlocked at exactly this building level."""
    from .units import UNIT_DEFS
    bdef = BUILDING_DEFS.get(building_key)
    if not bdef:
        return []
    target_tier = bdef.unlock_tier + (level - 1)
    return [
        key for key, udef in UNIT_DEFS.items()
        if udef.unit_type == bdef.unit_type
        and udef.tier == target_tier
        and not udef.npc_only
    ]
