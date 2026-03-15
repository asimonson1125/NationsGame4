import random

LAND_WEIGHTS = {
    'Westberg': {'cleared_land': 10, 'forest': 43, 'mountain': 10, 'river': 15, 'lake': 15, 'grassland': 20, 'jungle': 5, 'desert': 0, 'tundra': 2},
    'Amarino': {'cleared_land': 10, 'forest': 10, 'mountain': 5, 'river': 15, 'lake': 15, 'grassland': 5, 'jungle': 60, 'desert': 0, 'tundra': 0},
    'San Sebastian': {'cleared_land': 10, 'forest': 18, 'mountain': 15, 'river': 15, 'lake': 15, 'grassland': 20, 'jungle': 10, 'desert': 15, 'tundra': 2},
    'Tind': {'cleared_land': 10, 'forest': 5, 'mountain': 34, 'river': 20, 'lake': 20, 'grassland': 1, 'jungle': 0, 'desert': 0, 'tundra': 30},
    'Zaheria': {'cleared_land': 10, 'forest': 5, 'mountain': 5, 'river': 5, 'lake': 5, 'grassland': 5, 'jungle': 0, 'desert': 85, 'tundra': 0},
}
DEFAULT_LAND_WEIGHTS = {'cleared_land': 10, 'forest': 20, 'mountain': 20, 'river': 20, 'lake': 20, 'grassland': 30}

RESOURCE_WEIGHTS = {
    'Westberg': {
        'apple_tree': 3, 'mulberry': 1, 'herbs': 3, 'tobacco_plant': 3, 'cotton': 3, 'oak_tree': 5, 'rubber_tree': 1,
        'grapevine': 3, 'hops': 1, 'kingwood': 5, 'hemp': 3, 'beehive': 250, 'goat': 250, 'cow': 500, 'sheep': 250,
        'boar': 200, 'yak': 100, 'buffalo': 250, 'elephant': 100, 'fox': 250, 'clam': 500, 'shrimp': 500, 'bass': 500,
        'cod': 500, 'mackerel': 500, 'salmon': 500, 'piranha': 100, 'dolphin': 250, 'shark': 100, 'whale': 250,
        'coal': 500, 'iron': 250, 'marble': 400, 'bauxite': 400, 'copper': 250, 'lead': 250, 'gold': 250, 'platinum': 250,
        'silver': 250, 'saltpeter': 100, 'uraninite': 19, 'petroleum': 150, 'gemstone': 250, 'stonesilver': 250,
        'silicon': 300, 'crude_deep_sea_oil': 250
    },
    'Amarino': {
        'apple_tree': 5, 'mulberry': 3, 'coffea': 5, 'herbs': 5, 'tobacco_plant': 5, 'cotton': 1, 'oak_tree': 3,
        'rubber_tree': 5, 'cocoa': 5, 'grapevine': 5, 'hops': 3, 'kingwood': 3, 'hemp': 3, 'beehive': 200, 'cow': 500,
        'sheep': 500, 'elephant': 100, 'fox': 500, 'panther': 500, 'clam': 500, 'shrimp': 500, 'bass': 500, 'cod': 500,
        'mackerel': 500, 'salmon': 500, 'piranha': 500, 'dolphin': 250, 'shark': 500, 'whale': 250, 'marble': 400,
        'bauxite': 200, 'gold': 250, 'platinum': 100, 'silver': 250, 'saltpeter': 300, 'sulfur': 300, 'uraninite': 250,
        'petroleum': 25, 'gemstone': 250, 'stonesilver': 299, 'silicon': 500, 'crude_deep_sea_oil': 25
    },
    'San Sebastian': {
        'apple_tree': 1, 'cactus': 1, 'mulberry': 1, 'herbs': 3, 'tobacco_plant': 3, 'cotton': 3, 'oak_tree': 13,
        'rubber_tree': 1, 'grapevine': 3, 'hops': 5, 'kingwood': 13, 'hemp': 3, 'beehive': 100, 'goat': 100, 'cow': 250,
        'sheep': 250, 'boar': 150, 'yak': 75, 'buffalo': 250, 'elephant': 100, 'fox': 500, 'clam': 250, 'shrimp': 250,
        'bass': 250, 'cod': 250, 'mackerel': 250, 'salmon': 250, 'piranha': 250, 'dolphin': 100, 'shark': 250,
        'whale': 100, 'coal': 250, 'marble': 1000, 'bauxite': 500, 'gold': 500, 'platinum': 100, 'silver': 500,
        'saltpeter': 1025, 'sulfur': 1025, 'uraninite': 25, 'petroleum': 25, 'gemstone': 500, 'stonesilver': 200,
        'silicon': 300, 'crude_deep_sea_oil': 25
    },
    'Tind': {
        'apple_tree': 1, 'mulberry': 1, 'herbs': 1, 'cotton': 1, 'oak_tree': 1, 'grapevine': 1, 'hops': 1, 'kingwood': 3,
        'hemp': 1, 'goat': 500, 'cow': 250, 'sheep': 100, 'boar': 500, 'yak': 500, 'buffalo': 100, 'elephant': 100,
        'fox': 100, 'clam': 100, 'shrimp': 100, 'bass': 100, 'cod': 100, 'mackerel': 100, 'salmon': 100, 'dolphin': 50,
        'whale': 50, 'coal': 1000, 'iron': 1139, 'marble': 200, 'bauxite': 500, 'copper': 750, 'lead': 750, 'gold': 250,
        'platinum': 750, 'silver': 250, 'uraninite': 250, 'petroleum': 25, 'gemstone': 500, 'stonesilver': 500,
        'silicon': 250, 'crude_deep_sea_oil': 25
    },
    'Zaheria': {
        'cactus': 5, 'herbs': 1, 'cotton': 1, 'grapevine': 1, 'hops': 1, 'hemp': 1, 'beehive': 100, 'cow': 100,
        'sheep': 100, 'boar': 50, 'elephant': 500, 'clam': 100, 'shrimp': 100, 'bass': 100, 'cod': 100, 'mackerel': 100,
        'salmon': 100, 'piranha': 100, 'shark': 50, 'coal': 500, 'iron': 100, 'marble': 100, 'bauxite': 100,
        'copper': 100, 'gold': 750, 'silver': 750, 'saltpeter': 570, 'sulfur': 570, 'uraninite': 1500, 'petroleum': 1500,
        'gemstone': 250, 'silicon': 100, 'crude_deep_sea_oil': 1500
    },
}
DEFAULT_RESOURCE_WEIGHTS = {'coal': 300, 'iron': 200, 'marble': 150, 'cow': 400, 'sheep': 300}


def _weighted_distribute(weights, total):
    """Distribute `total` across keys by weight, returns dict of key->int (omitting zeros)."""
    filtered = {k: v for k, v in weights.items() if v > 0}
    if not filtered:
        return {}
    weight_sum = sum(filtered.values())
    result = {}
    for key, w in filtered.items():
        amount = int(total * w / weight_sum)
        if amount > 0:
            result[key] = amount
    return result


def _pick_weighted(weights):
    """Pick a random key using weighted random selection."""
    filtered = {k: v for k, v in weights.items() if v > 0}
    if not filtered:
        return None
    keys = list(filtered.keys())
    wts = list(filtered.values())
    return random.choices(keys, weights=wts, k=1)[0]


def _apply_variance(amounts, sigma=0.1):
    """Apply gaussian variance (σ=10%) to each value, ensuring non-negative ints."""
    return {k: max(0, int(v * random.gauss(1.0, sigma))) for k, v in amounts.items() if v > 0}


RESOURCE_TYPES = {
    'apple_tree': 'flora', 'cactus': 'flora', 'mulberry': 'flora', 'coffea': 'flora', 'herbs': 'flora',
    'tobacco_plant': 'flora', 'cotton': 'flora', 'oak_tree': 'flora', 'rubber_tree': 'flora', 'christmas_tree': 'flora',
    'cocoa': 'flora', 'grapevine': 'flora', 'hops': 'flora', 'kingwood': 'flora', 'hemp': 'flora',
    'beehive': 'fauna', 'goat': 'fauna', 'cow': 'fauna', 'sheep': 'fauna', 'boar': 'fauna', 'yak': 'fauna',
    'buffalo': 'fauna', 'elephant': 'fauna', 'fox': 'fauna', 'panther': 'fauna',
    'clam': 'fauna', 'shrimp': 'fauna', 'bass': 'fauna', 'cod': 'fauna', 'mackerel': 'fauna', 'salmon': 'fauna',
    'piranha': 'fauna', 'dolphin': 'fauna', 'shark': 'fauna', 'whale': 'fauna',
    'coal': 'mined', 'iron': 'mined', 'marble': 'mined', 'bauxite': 'mined', 'copper': 'mined', 'lead': 'mined',
    'gold': 'mined', 'platinum': 'mined', 'silver': 'mined', 'saltpeter': 'mined', 'sulfur': 'mined',
    'uraninite': 'mined', 'petroleum': 'mined', 'gemstone': 'mined', 'stonesilver': 'mined', 'silicon': 'mined',
    'crude_deep_sea_oil': 'mined'
}

RESOURCE_LEVELS = {
    'apple_tree': 1, 'cactus': 1, 'mulberry': 1, 'beehive': 1, 'goat': 1, 'clam': 1, 'shrimp': 1, 'coal': 1, 'iron': 1, 'marble': 1,
    'coffea': 2, 'herbs': 2, 'tobacco_plant': 2, 'cow': 2, 'sheep': 2, 'bass': 2, 'cod': 2, 'bauxite': 2, 'copper': 2, 'lead': 2,
    'cotton': 3, 'oak_tree': 3, 'rubber_tree': 3, 'boar': 3, 'yak': 3, 'mackerel': 3, 'salmon': 3, 'gold': 3, 'platinum': 3, 'silver': 3,
    'christmas_tree': 4, 'cocoa': 4, 'grapevine': 4, 'buffalo': 4, 'elephant': 4, 'piranha': 4, 'dolphin': 4, 'saltpeter': 4, 'sulfur': 4, 'uraninite': 4, 'petroleum': 4,
    'hops': 5, 'kingwood': 5, 'hemp': 5, 'fox': 5, 'panther': 5, 'shark': 5, 'whale': 5, 'gemstone': 5, 'stonesilver': 5, 'silicon': 5, 'crude_deep_sea_oil': 5
}


def _get_building_level(buildings, resource_key):
    """Return the level of the prerequisite building for a given resource."""
    cat = RESOURCE_TYPES.get(resource_key)
    if cat == 'flora':
        return buildings.get('botanical_research_station', 1)
    if cat == 'fauna':
        return buildings.get('wildlife_ranch', 1)
    if cat == 'mined':
        return buildings.get('mining_bureau', 1)
    return 1


def roll_expansion(continent, population, buildings=None):
    """Returns (new_land: dict, discovered: dict, total_gained: int)."""
    buildings = buildings or {}
    land_weights = LAND_WEIGHTS.get(continent, DEFAULT_LAND_WEIGHTS)
    new_land = _apply_variance(_weighted_distribute(land_weights, max(1, population // 100)))
    total_gained = sum(new_land.values())

    resource_weights = RESOURCE_WEIGHTS.get(continent, DEFAULT_RESOURCE_WEIGHTS)
    # Filter resources by building level
    eligible_weights = {
        res: weight for res, weight in resource_weights.items()
        if weight > 0 and _get_building_level(buildings, res) >= RESOURCE_LEVELS.get(res, 1)
    }
    
    discovered = _apply_variance(_weighted_distribute(eligible_weights, total_gained // 10))

    return new_land, discovered, total_gained


def roll_colonization(target_continent, population, buildings=None):
    """Returns (new_land: dict, discovered: dict, total_gained: int) — 5x land, more discoveries."""
    buildings = buildings or {}
    land_weights = LAND_WEIGHTS.get(target_continent, DEFAULT_LAND_WEIGHTS)
    new_land = _apply_variance(_weighted_distribute(land_weights, max(1, (population // 100) * 5)))
    total_gained = sum(new_land.values())

    resource_weights = RESOURCE_WEIGHTS.get(target_continent, DEFAULT_RESOURCE_WEIGHTS)
    # Filter resources by building level
    eligible_weights = {
        res: weight for res, weight in resource_weights.items()
        if weight > 0 and _get_building_level(buildings, res) >= RESOURCE_LEVELS.get(res, 1)
    }

    discovered = _apply_variance(_weighted_distribute(eligible_weights, total_gained // 2))

    return new_land, discovered, total_gained
