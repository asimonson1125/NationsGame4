from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class UnitDef:
    name: str
    unit_type: str           # Infantry, Armour, Static, Air, Special Forces
    firepower: int
    armour: int
    maneuver: int
    max_hp: int
    recruit_cost: Dict[str, float]
    upkeep: Dict[str, float]         # resource -> per-hour rate
    recruit_time: int                 # seconds
    tier: int = 1
    gp_value: int = 1
    special_abilities: List[str] = field(default_factory=list)


from .constants import _M, _P, _F, _BM, _CG, _ME, _AM, _FU, _UR


def _ud(name, unit_type, fp, arm, man, hp, cost, upkeep, time_s,
        tier=1, gp=None, abilities=None):
    return UnitDef(
        name=name, unit_type=unit_type,
        firepower=fp, armour=arm, maneuver=man, max_hp=hp,
        recruit_cost=cost, upkeep=upkeep, recruit_time=time_s,
        tier=tier, gp_value=gp if gp is not None else tier,
        special_abilities=abilities or [],
    )


# Tier mapping from recruit time:
#   1h = tier 1, 2-4h = tier 2, 6h = tier 3, 12h = tier 4,
#   1d = tier 5, 2d = tier 6, 3d = tier 7, 7d = tier 8

UNIT_DEFS: Dict[str, UnitDef] = {

    # ── INFANTRY (10 units) ───────────────────────────────────────────────

    'infantry': _ud(
        'Infantry', 'Infantry', fp=3, arm=1, man=2, hp=50,
        cost={_M: 1000}, upkeep={_M: 1, _F: 1},
        time_s=3600, tier=1, gp=1,
    ),
    'national_guard': _ud(
        'National Guard', 'Infantry', fp=2, arm=1, man=1, hp=50,
        cost={_M: 500}, upkeep={_F: 1},
        time_s=3600, tier=1, gp=1,
        abilities=['1.5x all combat stats while defending'],
    ),
    'medic': _ud(
        'Medic', 'Infantry', fp=1, arm=1, man=2, hp=50,
        cost={_M: 1500}, upkeep={_M: 1},
        time_s=3600, tier=1, gp=1,
        abilities=['Reduces damage to friendly infantry units by 25% (max 2 per division)'],
    ),
    'at4_infantry': _ud(
        'AT4 Infantry', 'Infantry', fp=3, arm=1, man=2, hp=50,
        cost={_M: 3000}, upkeep={_M: 5, _F: 1},
        time_s=7200, tier=2, gp=2,
        abilities=['4x firepower against armour units'],
    ),
    'mortar_infantry': _ud(
        'Mortar Infantry', 'Infantry', fp=3, arm=1, man=2, hp=50,
        cost={_M: 5000}, upkeep={_M: 5, _F: 1},
        time_s=14400, tier=2, gp=2,
        abilities=['4x firepower against infantry units'],
    ),
    'sniper': _ud(
        'Sniper', 'Infantry', fp=3, arm=1, man=2, hp=50,
        cost={_M: 5000}, upkeep={_M: 5, _F: 1},
        time_s=14400, tier=2, gp=2,
        abilities=['4x firepower against special forces units', '3x base roll multiplier'],
    ),
    'gear_infantry': _ud(
        'GEAR Infantry', 'Infantry', fp=6, arm=4, man=4, hp=115,
        cost={_M: 10000}, upkeep={_M: 5, _F: 3, _AM: 1},
        time_s=21600, tier=3, gp=3,
    ),
    'gear_sniper': _ud(
        'GEAR Sniper', 'Infantry', fp=4, arm=2, man=3, hp=75,
        cost={_M: 10000}, upkeep={_M: 5, _F: 3, _AM: 1},
        time_s=21600, tier=3, gp=3,
        abilities=['6x firepower against special forces units', '3x base roll multiplier'],
    ),
    'javelin_infantry': _ud(
        'Javelin Infantry', 'Infantry', fp=4, arm=2, man=3, hp=75,
        cost={_M: 10000}, upkeep={_M: 5, _F: 3, _AM: 1},
        time_s=21600, tier=3, gp=3,
        abilities=['6x firepower against armour units'],
    ),
    'rocket_sniper': _ud(
        'Rocket Sniper', 'Infantry', fp=3, arm=1, man=2, hp=50,
        cost={_M: 25000}, upkeep={_M: 5, _F: 1, _AM: 3},
        time_s=43200, tier=4, gp=4,
        abilities=['4x firepower against armour units', '4x firepower against air units',
                   '3x base roll multiplier'],
    ),

    # ── ARMOUR (10 units) ─────────────────────────────────────────────────

    'm1a1_abrahms': _ud(
        'M1A1 Abrahms', 'Armour', fp=3, arm=4, man=2, hp=130,
        cost={_M: 10000, _ME: 100}, upkeep={_M: 15, _FU: 1, _AM: 1},
        time_s=21600, tier=3, gp=3,
    ),
    'm2_bradley': _ud(
        'M2 Bradley', 'Armour', fp=2, arm=3, man=2, hp=85,
        cost={_M: 7500, _ME: 100}, upkeep={_M: 12, _FU: 1, _AM: 1},
        time_s=43200, tier=4, gp=4,
        abilities=['4x firepower against infantry units'],
    ),
    'armoured_combat_ambulance': _ud(
        'Armoured Combat Ambulance', 'Armour', fp=1, arm=3, man=3, hp=85,
        cost={_M: 5000, _ME: 50}, upkeep={_M: 10, _FU: 1},
        time_s=21600, tier=3, gp=3,
        abilities=['Reduces damage to friendly special forces units by 25% (max 2 per division)'],
    ),
    'k2_black_panther': _ud(
        'K2 Black Panther', 'Armour', fp=3, arm=2, man=1, hp=115,
        cost={_M: 10000, _ME: 100}, upkeep={_M: 15, _FU: 1, _AM: 1},
        time_s=43200, tier=4, gp=4,
        abilities=['4x firepower against static units'],
    ),
    'tank_destroyer': _ud(
        'Tank Destroyer', 'Armour', fp=3, arm=2, man=1, hp=115,
        cost={_M: 15000, _ME: 250}, upkeep={_M: 25, _FU: 3, _AM: 3},
        time_s=86400, tier=5, gp=5,
        abilities=['4x firepower against armour units'],
    ),
    'volvo_repair_truck': _ud(
        'Volvo Repair Truck', 'Armour', fp=1, arm=2, man=3, hp=85,
        cost={_M: 10000, _ME: 100}, upkeep={_M: 15, _FU: 1},
        time_s=86400, tier=5, gp=5,
        abilities=['Reduces damage to friendly armour units by 25% (max 2 per division)'],
    ),
    'type_99a': _ud(
        'Type 99A', 'Armour', fp=3, arm=4, man=2, hp=130,
        cost={_M: 25000, _ME: 500}, upkeep={_M: 30, _FU: 5, _AM: 10},
        time_s=172800, tier=6, gp=6,
        abilities=['4x firepower against static units'],
    ),
    '2k22_tunguska': _ud(
        '2K22 Tunguska', 'Armour', fp=3, arm=2, man=3, hp=115,
        cost={_M: 15000, _ME: 250}, upkeep={_M: 25, _FU: 3, _AM: 3},
        time_s=172800, tier=6, gp=6,
        abilities=['4x firepower against air units'],
    ),
    'gearhound_warhead': _ud(
        'GEARHOUND Warhead', 'Armour', fp=7, arm=7, man=4, hp=245,
        cost={_M: 50000, _ME: 1000}, upkeep={_M: 50, _FU: 15, _AM: 15, _UR: 3},
        time_s=259200, tier=7, gp=7,
    ),
    'gearhound_shredder': _ud(
        'GEARHOUND Shredder', 'Armour', fp=5, arm=4, man=5, hp=130,
        cost={_M: 25000, _ME: 500}, upkeep={_M: 18, _FU: 5, _AM: 5, _UR: 1},
        time_s=259200, tier=7, gp=7,
        abilities=['6x firepower against infantry units'],
    ),

    # ── STATIC (5 units) ─────────────────────────────────────────────────

    'trench_infantry': _ud(
        'Trench Infantry', 'Static', fp=3, arm=6, man=1, hp=130,
        cost={_M: 5000, _BM: 500}, upkeep={_M: 5, _AM: 1},
        time_s=21600, tier=3, gp=3,
        abilities=['6x firepower against infantry units'],
    ),
    'concrete_bunker': _ud(
        'Concrete Bunker', 'Static', fp=2, arm=8, man=1, hp=540,
        cost={_M: 25000, _BM: 2500, _ME: 500},
        upkeep={_M: 12, _P: 10, _AM: 3},
        time_s=43200, tier=4, gp=4,
    ),
    'zpu_4': _ud(
        'ZPU-4', 'Static', fp=3, arm=2, man=2, hp=85,
        cost={_M: 10000}, upkeep={_M: 24, _AM: 5},
        time_s=86400, tier=5, gp=5,
        abilities=['6x firepower against air units'],
    ),
    'fortified_bunker': _ud(
        'Fortified Bunker', 'Static', fp=3, arm=10, man=1, hp=1040,
        cost={_M: 100000, _BM: 10000, _ME: 2000},
        upkeep={_M: 25, _P: 20, _AM: 5},
        time_s=172800, tier=6, gp=6,
    ),
    'railgun': _ud(
        'Railgun', 'Static', fp=20, arm=4, man=2, hp=150,
        cost={_M: 500000, _BM: 25000, _ME: 5000},
        upkeep={_M: 50, _P: 25, _AM: 20},
        time_s=259200, tier=7, gp=7,
    ),

    # ── AIR (9 units) ────────────────────────────────────────────────────

    'f_35_lightning_ii': _ud(
        'F-35 Lightning II', 'Air', fp=4, arm=3, man=5, hp=100,
        cost={_M: 10000, _ME: 100}, upkeep={_M: 16, _FU: 2, _AM: 4},
        time_s=43200, tier=4, gp=4,
    ),
    'mh_6_little_bird': _ud(
        'MH-6 Little Bird', 'Air', fp=3, arm=2, man=4, hp=65,
        cost={_M: 5000, _ME: 25}, upkeep={_M: 10, _FU: 1, _AM: 3},
        time_s=43200, tier=4, gp=4,
        abilities=['4x firepower against special forces units'],
    ),
    'a10_thunderbolt': _ud(
        'A10 Thunderbolt', 'Air', fp=3, arm=3, man=4, hp=80,
        cost={_M: 15000, _ME: 250}, upkeep={_M: 20, _FU: 3, _AM: 5},
        time_s=86400, tier=5, gp=5,
        abilities=['6x firepower against armour units'],
    ),
    'mq_9_reaper': _ud(
        'MQ-9 Reaper', 'Air', fp=3, arm=1, man=3, hp=45,
        cost={_M: 15000, _ME: 250}, upkeep={_M: 12, _FU: 2, _AM: 6},
        time_s=86400, tier=5, gp=5,
        abilities=['4x firepower against infantry units', '4x firepower against armour units'],
    ),
    'f_22_raptor': _ud(
        'F-22 Raptor', 'Air', fp=4, arm=3, man=5, hp=100,
        cost={_M: 25000, _ME: 500}, upkeep={_M: 30, _FU: 4, _AM: 10},
        time_s=172800, tier=6, gp=6,
        abilities=['6x firepower against air units'],
    ),
    'pave_low': _ud(
        'Pave Low', 'Air', fp=4, arm=3, man=4, hp=75,
        cost={_M: 15000, _ME: 250}, upkeep={_M: 10, _FU: 3, _AM: 5},
        time_s=172800, tier=6, gp=6,
        abilities=['6x firepower against special forces units'],
    ),
    'b_2_spirit': _ud(
        'B-2 Spirit', 'Air', fp=9, arm=6, man=8, hp=155,
        cost={_M: 15000, _ME: 250}, upkeep={_M: 40, _FU: 12, _AM: 12, _UR: 1},
        time_s=259200, tier=7, gp=7,
    ),
    'mq_20_avenger': _ud(
        'MQ-20 Avenger', 'Air', fp=4, arm=2, man=5, hp=70,
        cost={_M: 20000, _ME: 500}, upkeep={_M: 25, _FU: 3, _AM: 5},
        time_s=259200, tier=7, gp=7,
        abilities=['6x firepower against infantry units', '6x firepower against armour units'],
    ),
    'lockheed_ac_130': _ud(
        'Lockheed AC-130', 'Air', fp=3, arm=2, man=11, hp=130,
        cost={_M: 100000, _ME: 1000}, upkeep={_M: 100, _FU: 15, _AM: 15},
        time_s=604800, tier=8, gp=8,
        abilities=['4x firepower against infantry units', '4x firepower against armour units',
                   '4x firepower against special forces units',
                   '4x maneuver multiplier to friendly units (max 1 per division)'],
    ),

    # ── SPECIAL FORCES (5 units) ─────────────────────────────────────────

    'riot_cop': _ud(
        'Riot Cop', 'Special Forces', fp=1, arm=4, man=1, hp=75,
        cost={_M: 5000}, upkeep={_M: 5},
        time_s=10800, tier=2, gp=2,
        abilities=['4x armour against infantry units'],
    ),
    'k9_team': _ud(
        'K9 Team', 'Special Forces', fp=1, arm=1, man=6, hp=50,
        cost={_M: 5000}, upkeep={_M: 10, _F: 2},
        time_s=21600, tier=3, gp=3,
        abilities=['4x firepower against infantry units'],
    ),
    'combat_engineer': _ud(
        'Combat Engineer', 'Special Forces', fp=3, arm=1, man=2, hp=50,
        cost={_M: 15000}, upkeep={_M: 12, _F: 1, _AM: 1},
        time_s=43200, tier=4, gp=4,
        abilities=['4x firepower against static units'],
    ),
    'signals_jammer': _ud(
        'Signals Jammer', 'Special Forces', fp=3, arm=1, man=2, hp=50,
        cost={_M: 25000}, upkeep={_M: 15, _F: 1, _P: 15},
        time_s=86400, tier=5, gp=5,
        abilities=['Reduces maneuver of enemy units by 25% (max 2 per division)'],
    ),
    'tyz_uav_engineer': _ud(
        'TyZ UAV Engineer', 'Special Forces', fp=4, arm=2, man=3, hp=75,
        cost={_M: 15000}, upkeep={_M: 20, _F: 1, _P: 15, _FU: 5},
        time_s=43200, tier=4, gp=4,
        abilities=['6x firepower against static units',
                   'Reduces damage to friendly static units by 25% (max 2 per division)'],
    ),
}
