import random

LAND_WEIGHTS = {
    'Westberg': {'forest': 300, 'grassland': 400, 'mountain': 150, 'river': 100, 'lake': 50},
    'Amarino': {'jungle': 500, 'river': 200, 'lake': 200, 'grassland': 100},
    'San Sebastian': {'grassland': 350, 'forest': 250, 'desert': 200, 'mountain': 150, 'river': 50},
    'Tind': {'mountain': 400, 'tundra': 300, 'forest': 200, 'river': 100},
    'Zaheria': {'desert': 600, 'mountain': 250, 'tundra': 100, 'grassland': 50},
}
DEFAULT_LAND_WEIGHTS = {'forest': 250, 'grassland': 300, 'mountain': 200, 'river': 150, 'lake': 100}

RESOURCE_WEIGHTS = {
    'Westberg': {'apple_tree': 3, 'oak_tree': 5, 'cow': 500, 'coal': 500, 'iron': 250, 'uraninite': 19, 'petroleum': 150, 'marble': 100, 'sheep': 300, 'copper': 200, 'lead': 150, 'silver': 80},
    'Amarino': {'apple_tree': 5, 'cow': 500, 'goat': 300, 'uraninite': 250, 'petroleum': 25, 'cocoa': 100, 'rubber_tree': 80, 'elephant': 60},
    'San Sebastian': {'oak_tree': 13, 'cow': 250, 'sheep': 400, 'coal': 250, 'iron': 0, 'uraninite': 25, 'petroleum': 25, 'marble': 200, 'copper': 300, 'lead': 200},
    'Tind': {'apple_tree': 1, 'cow': 250, 'iron': 1139, 'coal': 1000, 'uraninite': 250, 'petroleum': 25, 'platinum': 100, 'salmon': 200},
    'Zaheria': {'cactus': 200, 'goat': 300, 'cow': 100, 'petroleum': 1500, 'uraninite': 1500, 'gold': 200, 'silicon': 200, 'sulfur': 300},
}
DEFAULT_RESOURCE_WEIGHTS = {'coal': 300, 'iron': 200, 'marble': 150, 'cow': 400, 'sheep': 300}

EXPANSION_LAND_TOTAL = 10_000


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


def roll_expansion(continent):
    """Returns (new_land: dict, discovered: dict)."""
    land_weights = LAND_WEIGHTS.get(continent, DEFAULT_LAND_WEIGHTS)
    new_land = _weighted_distribute(land_weights, EXPANSION_LAND_TOTAL)

    resource_weights = RESOURCE_WEIGHTS.get(continent, DEFAULT_RESOURCE_WEIGHTS)
    num_discoveries = random.choices([0, 1, 2, 3], weights=[20, 50, 25, 5])[0]
    discovered = {}
    for _ in range(num_discoveries):
        resource = _pick_weighted(resource_weights)
        if resource:
            amount = random.randint(50, 500)
            discovered[resource] = discovered.get(resource, 0) + amount

    return new_land, discovered


def roll_colonization(target_continent):
    """Returns (new_land: dict, discovered: dict) — 5x land, more discoveries."""
    land_weights = LAND_WEIGHTS.get(target_continent, DEFAULT_LAND_WEIGHTS)
    base_land = _weighted_distribute(land_weights, EXPANSION_LAND_TOTAL)
    new_land = {k: v * 5 for k, v in base_land.items()}

    resource_weights = RESOURCE_WEIGHTS.get(target_continent, DEFAULT_RESOURCE_WEIGHTS)
    num_discoveries = random.choices([1, 2, 3, 4], weights=[20, 40, 30, 10])[0]
    discovered = {}
    for _ in range(num_discoveries):
        resource = _pick_weighted(resource_weights)
        if resource:
            amount = random.randint(200, 2000)
            discovered[resource] = discovered.get(resource, 0) + amount

    return new_land, discovered
