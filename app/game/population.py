# Population effects per capita per hour.
# Positive = nation gains resources; negative = nation loses resources.
# Rates expressed as 1/N where N = people per unit per hour.
POPULATION_RATES = {
    'money':           1/100,   # 100 people per tax dollar
    'food':           -1/2000, # 2000 people per food
    'power':          -1/2500, # 2500 people per power
    'consumer_goods': -1/5000, # 5000 people per consumer goods
}

# Consumer goods consumption only kicks in above this threshold.
CG_POPULATION_THRESHOLD = 100_000

# Tier thresholds: (min_population, tier) — checked highest-first
# T1: <75k | T2: 75k–150k | T3: 150k–350k | T4: 350k–1M | T5: 1M–2.5M | T6: 2.5M+
TIER_THRESHOLDS = [
    (2_500_000, 6),
    (1_000_000, 5),
    (350_000,   4),
    (150_000,   3),
    (75_000,    2),
]

# Growth constants
GROWTH_MULTIPLIER = 0.05       # base hourly growth factor
FOOD_PER_CITIZEN = 0.1          # food cost per new citizen
LAND_PER_POPULATION = 1000      # 1 tile per 1,000 new pop
STARVATION_RATE = 0.01          # 1% population loss per hour when starving


def get_population_effects(population):
    """Returns dict of resource -> hourly amount for the given population."""
    pop = population or 0
    effects = {}
    for res, rate in POPULATION_RATES.items():
        if res == 'consumer_goods' and pop <= CG_POPULATION_THRESHOLD:
            effects[res] = 0
        else:
            effects[res] = pop * rate
    return effects


def compute_tier(population):
    """Return tier (1-6) based on population."""
    pop = population or 0
    for threshold, tier in TIER_THRESHOLDS:
        if pop >= threshold:
            return tier
    return 1


def compute_population_gp(population):
    """Return GP value for population (1 GP per 10000 citizens)."""
    return max(0, (population or 0) // 10000)


def _cap_growth(pop, new_pop, food, cleared, urban):
    """Apply food and land caps to a desired growth amount. Returns capped int."""
    # Cap by total land capacity
    max_capacity = (urban + cleared) * LAND_PER_POPULATION
    room = max(0, max_capacity - pop)
    if new_pop > room:
        new_pop = room

    # Cap by food
    food_cost = new_pop * FOOD_PER_CITIZEN
    if food < food_cost:
        new_pop = food / FOOD_PER_CITIZEN

    return int(new_pop)


def estimate_pop_delta(nation, rate_override=None):
    """Estimate net hourly population change without modifying the nation.

    Accounts for food limits, land capacity, and starvation.
    Optional rate_override lets the caller preview a different growth rate.
    """
    pop = nation.population or 0
    food = nation.food or 0
    rate = rate_override if rate_override is not None else (nation.growth_rate or 0)
    cleared = nation.cleared_land or 0
    urban = nation.urban_areas or 0

    # Starvation takes precedence when food is 0
    if food <= 0:
        return -max(1, int(pop * STARVATION_RATE))

    if rate <= 0:
        return 0

    if cleared <= 0 and urban <= 0:
        return 0

    new_pop = pop * (rate / 100) * GROWTH_MULTIPLIER
    return _cap_growth(pop, new_pop, food, cleared, urban)


def process_growth(nation):
    """Apply population growth based on nation's growth_rate setting.

    Growth requires food. Land conversion (cleared → urban) happens as a side
    effect when cleared land is available, but growth proceeds regardless —
    population can expand into existing urban areas.

    Returns the number of new citizens added (0 if growth didn't happen).
    """
    rate = nation.growth_rate or 0
    if rate <= 0:
        return 0

    pop = nation.population or 0
    cleared = nation.cleared_land or 0
    urban = nation.urban_areas or 0

    # Need somewhere for people to live
    if cleared <= 0 and urban <= 0:
        return 0

    # Calculate desired new population, capped by food and land capacity
    food_available = nation.food or 0
    new_pop = pop * (rate / 100) * GROWTH_MULTIPLIER
    new_pop_int = _cap_growth(pop, new_pop, food_available, cleared, urban)
    if new_pop_int < 1:
        return 0

    # Land conversion based on total population vs urban capacity.
    # Each urban tile supports LAND_PER_POPULATION citizens.
    new_total = pop + new_pop_int
    urban_capacity = urban * LAND_PER_POPULATION
    if new_total > urban_capacity and cleared > 0:
        import math
        tiles_needed = min(math.ceil((new_total - urban_capacity) / LAND_PER_POPULATION), cleared)
    else:
        tiles_needed = 0

    # Apply changes
    nation.population = new_total
    nation.food = max(0, food_available - (new_pop_int * FOOD_PER_CITIZEN))
    if tiles_needed > 0:
        nation.cleared_land = cleared - tiles_needed
        nation.urban_areas = urban + tiles_needed

    return new_pop_int


def process_starvation(nation):
    """If food is 0, population decreases by 1% per hour.

    Returns the number of citizens lost (0 if no starvation).
    """
    food = nation.food or 0
    if food > 0:
        return 0

    pop = nation.population or 0
    if pop <= 0:
        return 0

    loss = int(pop * STARVATION_RATE)
    loss = max(1, loss)  # lose at least 1
    nation.population = max(0, pop - loss)
    return loss
