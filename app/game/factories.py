from dataclasses import dataclass, field
from typing import Dict


@dataclass
class FactoryDef:
    name: str
    tier: int
    inputs: Dict[str, float]   # resource -> units per factory per hour
    outputs: Dict[str, float]  # resource -> units per factory per hour
    max_collect_hours: int = 24
    build_cost: Dict[str, float] = field(default_factory=dict)   # resource -> amount per factory
    land_required: Dict[str, int] = field(default_factory=dict)  # land_type -> tiles per factory
    gp_value: int = 1
    build_time: int = 30       # minutes to construct


_TIER_BUILD_TIME = {1: 60, 2: 180, 3: 480, 4: 1440, 5: 2880, 6: 5760, 10: 8640}


def _fd(name, tier, inp, out, cost, land, gp=None, max_h=24, bt=None):
    if bt is None:
        bt = _TIER_BUILD_TIME.get(tier, 60)
    return FactoryDef(
        name=name, tier=tier, inputs=inp, outputs=out,
        max_collect_hours=max_h,
        build_cost=cost, land_required=land,
        gp_value=gp if gp is not None else tier,
        build_time=bt,
    )


from .constants import _M, _P, _F, _BM, _CG, _ME, _AM, _FU, _UR, _WH

FACTORY_DEFS: Dict[str, FactoryDef] = {

    # ── TIER 1 ─────────────────────────────────────────────────────────────
    'farm': _fd(
        'Farm', 1,
        inp={_M: 9}, out={_F: 3},
        cost={_M: 500}, land={'cleared_land': 5}, gp=1, bt=30,
    ),
    'windmill': _fd(
        'Windmill', 1,
        inp={_M: 5}, out={_P: 5},
        cost={_M: 250}, land={'cleared_land': 5}, gp=1, bt=30,
    ),
    'quarry': _fd(
        'Quarry', 1,
        inp={_M: 27}, out={_BM: 3},
        cost={_M: 1000}, land={'mountain': 5}, gp=1, bt=30,
    ),
    'sandstone_quarry': _fd(
        'Sandstone Quarry', 1,
        inp={_M: 27}, out={_BM: 3},
        cost={_M: 1000}, land={'desert': 5}, bt=30,
    ),
    'sawmill': _fd(
        'Sawmill', 1,
        inp={_M: 27}, out={_BM: 3},
        cost={_M: 1000}, land={'forest': 5}, bt=30,
    ),
    'jungle_sawmill': _fd(
        'Jungle Sawmill', 1,
        inp={_M: 27}, out={_BM: 3},
        cost={_M: 1000}, land={'jungle': 5}, bt=30,
    ),
    'concrete_factory': _fd(
        'Concrete Factory', 1,
        inp={_M: 27}, out={_BM: 3},
        cost={_M: 1000}, land={'cleared_land': 10}, bt=30,
    ),
    'stationery_factory': _fd(
        'Stationery Factory', 1,
        inp={_M: 3, _P: 13}, out={_CG: 1},
        cost={_M: 1000, _BM: 250}, land={'cleared_land': 5},
    ),
    'ciderworks': _fd(
        'Ciderworks', 1,
        inp={_M: 11, _P: 11}, out={_CG: 2},
        cost={_M: 1000, _BM: 250, 'apple_tree': 5}, land={'cleared_land': 5},
    ),
    'sandy_soda_factory': _fd(
        'Sandy Soda Factory', 1,
        inp={_M: 11, _P: 11}, out={_CG: 2},
        cost={_M: 1000, _BM: 250, 'cactus': 5}, land={'cleared_land': 5},
    ),
    'silk_factory': _fd(
        'Fancy Uniform Factory', 1,
        inp={_M: 11, _P: 11}, out={_CG: 2},
        cost={_M: 1000, _BM: 250, 'mulberry': 5}, land={'cleared_land': 5},
    ),
    'beekeeper': _fd(
        'Beekeeper', 1,
        inp={_M: 11, _P: 11, 'beehive': 1}, out={_CG: 2},
        cost={_M: 1000, _BM: 250}, land={'cleared_land': 5},
    ),
    'goat_shepherd': _fd(
        'Goat Shepherd', 1,
        inp={_M: 2, _P: 9, 'goat': 1}, out={_F: 1, _CG: 1},
        cost={_M: 1000, _BM: 250}, land={'cleared_land': 5},
    ),
    'clam_divers': _fd(
        'Clam Divers', 1,
        inp={_M: 4, _P: 5, 'clam': 1}, out={_F: 5},
        cost={_M: 1000, _BM: 250}, land={'cleared_land': 1},
    ),
    'shrimp_trawler': _fd(
        'Shrimp Trawler', 1,
        inp={_M: 4, _P: 5, 'shrimp': 1}, out={_F: 5},
        cost={_M: 1000, _BM: 250}, land={'cleared_land': 1},
    ),
    'coal_power_plant': _fd(
        'Coal Power Plant', 1,
        inp={_M: 12, 'coal': 1}, out={_P: 20},
        cost={_M: 1000, _BM: 250}, land={'cleared_land': 5},
    ),
    'iron_smelter': _fd(
        'Iron Smelter', 1,
        inp={_M: 6, _P: 7, 'iron': 1}, out={_ME: 1},
        cost={_M: 1000, _BM: 250}, land={'cleared_land': 5},
    ),
    'stonemason': _fd(
        'Stone Mason', 1,
        inp={_M: 9, _P: 8, 'marble': 1}, out={_BM: 1, _CG: 1},
        cost={_M: 1000, _BM: 250}, land={'cleared_land': 5},
    ),

    # ── TIER 2 ─────────────────────────────────────────────────────────────
    'hydro_plant': _fd(
        'Hydro Plant', 2,
        inp={_M: 7}, out={_P: 10},
        cost={_M: 5000, _BM: 500, _ME: 100}, land={'river': 5},
    ),
    'hydro_dam': _fd(
        'Hydro Dam', 2,
        inp={_M: 7}, out={_P: 10},
        cost={_M: 5000, _BM: 500, _ME: 100}, land={'lake': 5},
    ),
    'coffee_plantation': _fd(
        'Coffee Plantation', 2,
        inp={_M: 23, _P: 23}, out={_CG: 5},
        cost={_M: 5000, _BM: 500, _ME: 100, 'coffea': 5}, land={'cleared_land': 10},
    ),
    'pharmacy': _fd(
        'Pharmacy', 2,
        inp={_M: 23, _P: 23}, out={_CG: 5},
        cost={_M: 5000, _BM: 500, _ME: 100, 'herbs': 5}, land={'cleared_land': 10},
    ),
    'tobacco_plantation': _fd(
        'Tobacco Plantation', 2,
        inp={_M: 23, _P: 23}, out={_CG: 5},
        cost={_M: 5000, _BM: 500, _ME: 100, 'tobacco_plant': 5}, land={'cleared_land': 10},
    ),
    'dairy_farm': _fd(
        'Dairy Farm', 2,
        inp={_M: 6, _P: 7, 'cow': 1}, out={_F: 10},
        cost={_M: 5000, _BM: 500, _ME: 100}, land={'cleared_land': 10},
    ),
    'clothing_factory': _fd(
        'Clothing Factory', 2,
        inp={_M: 23, _P: 23, 'sheep': 1}, out={_CG: 5},
        cost={_M: 5000, _BM: 500, _ME: 100}, land={'cleared_land': 10},
    ),
    'bass_fishery': _fd(
        'Bass Fishery', 2,
        inp={_M: 6, _P: 7, 'bass': 1}, out={_F: 10},
        cost={_M: 5000, _BM: 1000, _ME: 100}, land={'cleared_land': 1},
    ),
    'cod_fishery': _fd(
        'Cod Fishery', 2,
        inp={_M: 6, _P: 7, 'cod': 1}, out={_F: 10},
        cost={_M: 5000, _BM: 1000, _ME: 100}, land={'cleared_land': 1},
    ),
    'aluminum_plant': _fd(
        'Aluminum Plant', 2,
        inp={_M: 25, _P: 36, 'bauxite': 1}, out={_BM: 5, _ME: 2},
        cost={_M: 5000, _BM: 500}, land={'cleared_land': 10},
    ),
    'electrical_engineering_supply_factory': _fd(
        'Electrical Engineering Supply Factory', 2,
        inp={_M: 7, _P: 10, 'copper': 1}, out={_ME: 2},
        cost={_M: 5000, _BM: 500}, land={'cleared_land': 10},
    ),
    'battery_assembler': _fd(
        'Battery Assembler', 2,
        inp={_M: 26, _P: 36, 'lead': 1}, out={_CG: 4, _ME: 2},
        cost={_M: 5000, _BM: 500}, land={'cleared_land': 10},
    ),

    # ── TIER 3 ─────────────────────────────────────────────────────────────
    'cotton_plantation': _fd(
        'Cotton Plantation', 3,
        inp={_M: 34, _P: 39}, out={_CG: 10},
        cost={_M: 10000, _BM: 2000, _ME: 250, 'cotton': 5}, land={'cleared_land': 10},
    ),
    'oak_mill': _fd(
        'Oak Mill', 3,
        inp={_M: 18, _P: 41}, out={_BM: 15},
        cost={_M: 10000, _BM: 2000, _ME: 250, 'oak_tree': 5}, land={'cleared_land': 10},
    ),
    'rubber_band_factory': _fd(
        'Rubber Band Factory', 3,
        inp={_M: 34, _P: 39}, out={_CG: 10},
        cost={_M: 10000, _BM: 2000, _ME: 250, 'rubber_tree': 5}, land={'cleared_land': 10},
    ),
    'hunting_lodge': _fd(
        'Hunting Lodge', 3,
        inp={_M: 52, _P: 13, 'boar': 1}, out={_CG: 5, _F: 10},
        cost={_M: 10000, _BM: 2000, _ME: 250}, land={'cleared_land': 10},
    ),
    'yak_farm': _fd(
        'Yak Farm', 3,
        inp={_M: 52, _P: 13, 'yak': 1}, out={_CG: 5, _F: 10},
        cost={_M: 10000, _BM: 2000, _ME: 250}, land={'cleared_land': 10},
    ),
    'mackerel_fishery': _fd(
        'Mackerel Fishery', 3,
        inp={_M: 6, _P: 12, 'mackerel': 1}, out={_F: 15},
        cost={_M: 10000, _BM: 2000, _ME: 250}, land={'cleared_land': 10},
    ),
    'salmon_fishery': _fd(
        'Salmon Fishery', 3,
        inp={_M: 6, _P: 12, 'salmon': 1}, out={_F: 15},
        cost={_M: 10000, _BM: 2000, _ME: 250}, land={'cleared_land': 10},
    ),
    'gold_mine': _fd(
        'Gold Mine', 3,
        inp={_P: 20, 'gold': 1}, out={_M: 90},
        cost={_M: 10000, _BM: 2000}, land={'cleared_land': 10},
    ),
    'platinum_refinery': _fd(
        'Platinum Refinery', 3,
        inp={_M: 10, _P: 15, 'platinum': 1}, out={_ME: 5},
        cost={_M: 10000, _BM: 2000}, land={'cleared_land': 10},
    ),
    'silver_mine': _fd(
        'Silver Mine', 3,
        inp={_P: 25, 'silver': 1}, out={_M: 100},
        cost={_M: 10000, _BM: 2000}, land={'cleared_land': 10},
    ),

    # ── TIER 4 ─────────────────────────────────────────────────────────────
    'nuclear_power_plant': _fd(
        'Nuclear Power Plant', 4,
        inp={_M: 25, _UR: 1}, out={_P: 250},
        cost={_M: 15000, _BM: 5000, _ME: 1000}, land={'cleared_land': 20}, gp=8,
    ),
    'christmas_tree_factory': _fd(
        'Christmas Tree Factory', 4,
        inp={_M: 50, _P: 50}, out={_CG: 15},
        cost={_M: 15000, _BM: 5000, _ME: 1000, 'christmas_tree': 5}, land={'cleared_land': 10},
    ),
    'chocolate_factory': _fd(
        'Chocolate Factory', 4,
        inp={_M: 12, _P: 48}, out={_CG: 12, _F: 15},
        cost={_M: 15000, _BM: 5000, _ME: 1000, 'cocoa': 5}, land={'cleared_land': 10},
    ),
    'winery': _fd(
        'Winery', 4,
        inp={_M: 12, _P: 48}, out={_CG: 12, _F: 15},
        cost={_M: 15000, _BM: 5000, _ME: 1000, 'grapevine': 5}, land={'cleared_land': 10},
    ),
    'mozzarella_factory': _fd(
        'Mozzarella Factory', 4,
        inp={_M: 22, _P: 44, 'buffalo': 1}, out={_CG: 16},
        cost={_M: 15000, _BM: 5000, _ME: 1000}, land={'cleared_land': 20},
    ),
    'ivory_arts': _fd(
        'Ivory Arts', 4,
        inp={_M: 22, _P: 44, 'elephant': 1}, out={_CG: 16},
        cost={_M: 15000, _BM: 5000, _ME: 1000}, land={'cleared_land': 20},
    ),
    'hardened_fisherman': _fd(
        'Hardened Fisherman', 4,
        inp={_M: 20, _P: 26, 'piranha': 1}, out={_F: 35},
        cost={_M: 15000, _BM: 5000, _ME: 1000}, land={'cleared_land': 10},
    ),
    'dolphin_aquarium': _fd(
        'Dolphin Aquarium', 4,
        inp={_M: 25, _P: 26, 'dolphin': 1}, out={_M: 175},
        cost={_M: 15000, _BM: 5000, _ME: 1000}, land={'cleared_land': 10},
    ),
    'explosives_factory': _fd(
        'Explosives Factory', 4,
        inp={_M: 10, _P: 19, 'saltpeter': 1}, out={_AM: 3},
        cost={_M: 15000, _BM: 5000, _ME: 1000}, land={'cleared_land': 10},
    ),
    'petroleum_factory': _fd(
        'Petroleum Refinery', 4,
        inp={_M: 27, _P: 54, 'petroleum': 1}, out={_FU: 5},
        cost={_M: 15000, _BM: 5000, _ME: 1000}, land={'cleared_land': 10},
    ),
    'nuclear_reactor': _fd(
        'Nuclear Reactor', 4,
        inp={_M: 30, _P: 59, 'uraninite': 1}, out={_UR: 3},
        cost={_M: 15000, _BM: 5000, _ME: 1000}, land={'cleared_land': 10}, gp=8,
    ),

    # ── TIER 5 ─────────────────────────────────────────────────────────────
    'brewery': _fd(
        'Brewery', 5,
        inp={_M: 19, _P: 67}, out={_CG: 28},
        cost={_M: 25000, _BM: 10000, _ME: 2000, 'hops': 5}, land={'cleared_land': 10},
    ),
    'kingwood_mill': _fd(
        'Kingwood Mill', 5,
        inp={_M: 24, _P: 64}, out={_BM: 30},
        cost={_M: 25000, _BM: 10000, _ME: 2000, 'kingwood': 5}, land={'cleared_land': 10},
    ),
    'ropery': _fd(
        'Ropery', 5,
        inp={_M: 19, _P: 67}, out={_CG: 28},
        cost={_M: 25000, _BM: 10000, _ME: 2000, 'hemp': 5}, land={'cleared_land': 10},
    ),
    'fur_farm': _fd(
        'Fur Farm', 5,
        inp={_M: 45, _P: 45, 'fox': 1}, out={_CG: 40},
        cost={_M: 25000, _BM: 10000, _ME: 2000}, land={'cleared_land': 10},
    ),
    'fancy_carpet_maker': _fd(
        'Fancy Carpet Maker', 5,
        inp={_M: 45, _P: 45, 'panther': 1}, out={_CG: 40},
        cost={_M: 25000, _BM: 10000, _ME: 2000}, land={'cleared_land': 10},
    ),
    'exotic_seafood_restaurant': _fd(
        'Exotic Seafood Restaurant', 5,
        inp={_M: 45, _P: 45, 'shark': 1}, out={_F: 30, _CG: 15},
        cost={_M: 25000, _BM: 10000, _ME: 2000}, land={'cleared_land': 1},
    ),
    'whaler': _fd(
        'Whaler', 5,
        inp={_M: 45, _P: 45, 'whale': 1}, out={_F: 15, _CG: 30},
        cost={_M: 25000, _BM: 10000, _ME: 2000}, land={'cleared_land': 1},
    ),
    'ammunition_factory': _fd(
        'Ammunition Factory', 5,
        inp={_M: 12, _P: 20, 'sulfur': 1}, out={_AM: 4},
        cost={_M: 25000, _BM: 10000, _ME: 2000}, land={'cleared_land': 10},
    ),
    'gemmer': _fd(
        'Gemmer', 5,
        inp={_P: 50, 'gemstone': 1}, out={_M: 350},
        cost={_M: 25000, _BM: 10000, _ME: 2000}, land={'cleared_land': 10},
    ),
    'stonesilver_quarry': _fd(
        'Stonesilver Quarry', 5,
        inp={_M: 75, _P: 100, 'stonesilver': 1}, out={_M: 175, _ME: 5, _CG: 5},
        cost={_M: 25000, _BM: 10000, _ME: 2000}, land={'cleared_land': 10},
    ),
    'microchip_factory': _fd(
        'Microchip Factory', 5,
        inp={_M: 45, _P: 45, 'silicon': 1}, out={_CG: 40},
        cost={_M: 25000, _BM: 10000, _ME: 2000}, land={'cleared_land': 10},
    ),
    'oil_refinery': _fd(
        'Oil Refinery', 5,
        inp={_M: 30, _P: 60, 'crude_deep_sea_oil': 1}, out={_FU: 7},
        cost={_M: 25000, _BM: 10000, _ME: 2000}, land={'cleared_land': 10},
    ),

    # ── TIER 6 ─────────────────────────────────────────────────────────────
    'warhead_co_utilizer': _fd(
        'Warhead Co. Utilizer', 6,
        inp={_M: 25, _P: 25, _UR: 1}, out={_AM: 10},
        cost={_M: 50000, _BM: 15000, _ME: 3000}, land={'cleared_land': 10},
    ),
    'warhead_co_extractor': _fd(
        'Warhead Co. Extractor', 6,
        inp={_M: 900, _P: 900, _ME: 300}, out={_UR: 1},
        cost={_M: 50000, _BM: 15000, _ME: 3000}, land={'cleared_land': 10},
    ),

    # ── TIER 10 ────────────────────────────────────────────────────────────
    'whz_radium_facility': _fd(
        'WhZ Radium Facility', 10,
        inp={_M: 3400, _P: 6800, _UR: 10, 'primal_fungus_spore': 1}, out={_WH: 1},
        cost={_M: 10_000_000, _BM: 1_000_000, _ME: 75_000}, land={'cleared_land': 10}, gp=20,
    ),
}
