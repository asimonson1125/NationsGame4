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
    'Westberg': {'apple_tree': 3, 'oak_tree': 5, 'cow': 500, 'coal': 500, 'iron': 250, 'uraninite': 19, 'petroleum': 150, 'marble': 100, 'sheep': 300, 'copper': 200, 'lead': 150, 'silver': 80},
    'Amarino': {'apple_tree': 5, 'cow': 500, 'goat': 300, 'uraninite': 250, 'petroleum': 25, 'cocoa': 100, 'rubber_tree': 80, 'elephant': 60},
    'San Sebastian': {'oak_tree': 13, 'cow': 250, 'sheep': 400, 'coal': 250, 'iron': 0, 'uraninite': 25, 'petroleum': 25, 'marble': 200, 'copper': 300, 'lead': 200},
    'Tind': {'apple_tree': 1, 'cow': 250, 'iron': 1139, 'coal': 1000, 'uraninite': 250, 'petroleum': 25, 'platinum': 100, 'salmon': 200},
    'Zaheria': {'cactus': 200, 'goat': 300, 'cow': 100, 'petroleum': 1500, 'uraninite': 1500, 'gold': 200, 'silicon': 200, 'sulfur': 300},
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


def roll_expansion(continent, population):
    """Returns (new_land: dict, discovered: dict)."""
    land_weights = LAND_WEIGHTS.get(continent, DEFAULT_LAND_WEIGHTS)
    total_gained = max(1, population // 100)
    new_land = _weighted_distribute(land_weights, total_gained)

    resource_weights = RESOURCE_WEIGHTS.get(continent, DEFAULT_RESOURCE_WEIGHTS)
    discovered = {res: amt for res, amt in resource_weights.items() if amt > 0}

    return new_land, discovered, total_gained


def roll_colonization(target_continent, population):
    """Returns (new_land: dict, discovered: dict) — 5x land, more discoveries."""
    land_weights = LAND_WEIGHTS.get(target_continent, DEFAULT_LAND_WEIGHTS)
    # Colonization gives 5x the land of a normal expansion
    total_gained = max(1, (population // 100) * 5)
    new_land = _weighted_distribute(land_weights, total_gained)

    resource_weights = RESOURCE_WEIGHTS.get(target_continent, DEFAULT_RESOURCE_WEIGHTS)
    discovered = {res: amt * 5 for res, amt in resource_weights.items() if amt > 0}

    return new_land, discovered, total_gained
