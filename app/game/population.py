import math

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
    (6_000_000, 7),
    (2_500_000, 6),
    (1_000_000, 5),
    (350_000,   4),
    (150_000,   3),
    (75_000,    2),
]

# Growth constants
GROWTH_MULTIPLIER = 0.05       # base hourly growth factor
FOOD_PER_CITIZEN = 0.025          # food cost per new citizen
LAND_PER_POPULATION = 1000      # 1 tile per 1,000 new pop
STARVATION_RATE = 0.0025          # 0.25% population loss per hour when starving
FOOD_STOCKPILE_MIN_DAYS = 3    # no growth below this many days of food
FOOD_STOCKPILE_MAX_DAYS = 30   # max growth at or above this many days of food


def compute_tax_multiplier(nation, effects):
    """Return tax income multiplier based on food/power/CG deficits.

    Tax is halved for each resource the nation cannot cover with its current
    stockpile: no power → x0.5, no CG → x0.5, neither → x0.25.
    """
    multiplier = 1.0
    food_needed = abs(effects.get('food', 0))
    power_needed = abs(effects.get('power', 0))
    cg_needed = abs(effects.get('consumer_goods', 0))
    if food_needed > 0 and (nation.food or 0) < food_needed:
        multiplier *= 0.25
    if power_needed > 0 and (nation.power or 0) < power_needed:
        multiplier *= 0.5
    if cg_needed > 0 and (nation.consumer_goods or 0) < cg_needed:
        multiplier *= 0.5
    return multiplier


def get_population_effects(population):
    """Returns dict of resource -> hourly amount for the given population."""
    pop = population or 0
    effects = {}
    for res, rate in POPULATION_RATES.items():
        if res == 'consumer_goods':
            # Consumer goods consumption only if population > threshold
            if pop > CG_POPULATION_THRESHOLD:
                # Round up consumption magnitude (e.g. -0.0002 -> -1)
                effects[res] = math.floor((pop - CG_POPULATION_THRESHOLD) * rate)
            else:
                effects[res] = 0
        elif rate < 0:
            # Resource consumption: round up magnitude (e.g. -50.1 -> -51)
            effects[res] = math.floor(pop * rate)
        else:
            # Resource income: stay as float
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


def food_abundance_multiplier(population, food_stockpile):
    """Return 0.0–1.0 multiplier based on how many days of food are stockpiled.

    Below FOOD_STOCKPILE_MIN_DAYS of consumption → 0 (no growth).
    Linear ramp from MIN to MAX days → 0.0 to 1.0.
    At or above FOOD_STOCKPILE_MAX_DAYS → 1.0 (full growth).
    """
    pop = population or 0
    food = food_stockpile or 0
    if pop <= 0:
        return 1.0  # no consumption, no constraint

    hourly_consumption = math.ceil(pop * abs(POPULATION_RATES['food']))
    daily_consumption = hourly_consumption * 24
    if daily_consumption <= 0:
        return 1.0

    days_of_food = food / daily_consumption

    if days_of_food < FOOD_STOCKPILE_MIN_DAYS:
        return 0.0
    if days_of_food >= FOOD_STOCKPILE_MAX_DAYS:
        return 1.0

    return (days_of_food - FOOD_STOCKPILE_MIN_DAYS) / (FOOD_STOCKPILE_MAX_DAYS - FOOD_STOCKPILE_MIN_DAYS)


def get_food_days(population, food_stockpile):
    """Return how many days of food the nation has stockpiled."""
    pop = population or 0
    food = food_stockpile or 0
    if pop <= 0:
        return 999.0
    hourly_consumption = math.ceil(pop * abs(POPULATION_RATES['food']))
    daily_consumption = hourly_consumption * 24
    if daily_consumption <= 0:
        return 999.0
    return food / daily_consumption


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

    Accounts for food limits, land capacity, and scaled starvation.
    Optional rate_override lets the caller preview a different growth rate.
    """
    pop = nation.population or 0
    food = nation.food or 0
    rate = rate_override if rate_override is not None else (nation.growth_rate or 0)
    cleared = nation.cleared_land or 0
    urban = nation.urban_areas or 0

    # Calculate hourly food consumption for population
    food_needed = math.ceil(pop * abs(POPULATION_RATES['food']))

    # Starvation when food can't cover population consumption
    if food_needed > 0 and food < food_needed:
        deficit_fraction = (food_needed - food) / food_needed
        return -max(1, int(pop * STARVATION_RATE * deficit_fraction))

    if rate <= 0:
        return 0

    if cleared <= 0 and urban <= 0:
        return 0

    # In auto mode, food abundance IS the effective rate (0–100%).
    # In manual mode, the user's rate is used directly.
    mode = getattr(nation, 'growth_mode', 'auto') or 'auto'
    if mode == 'auto':
        effective_rate = food_abundance_multiplier(pop, food) * 100
        if effective_rate <= 0:
            return 0
    else:
        effective_rate = rate

    # Food remaining after population consumption is available for growth
    remaining_food = food - food_needed
    new_pop = pop * (effective_rate / 100) * GROWTH_MULTIPLIER
    return _cap_growth(pop, new_pop, remaining_food, cleared, urban)


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

    # In auto mode, food abundance IS the effective rate (0–100%).
    # In manual mode, the user's rate is used directly.
    food_available = nation.food or 0
    mode = getattr(nation, 'growth_mode', 'auto') or 'auto'
    if mode == 'auto':
        effective_rate = food_abundance_multiplier(pop, food_available) * 100
        if effective_rate <= 0:
            return 0
    else:
        effective_rate = rate

    # Calculate desired new population, capped by food and land capacity
    new_pop = pop * (effective_rate / 100) * GROWTH_MULTIPLIER
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


def process_starvation(nation, deficit_fraction=1.0):
    """Apply population starvation scaled by food deficit.

    deficit_fraction: 0.0 = no deficit, 1.0 = total starvation (no food at all).
    For example, if population needs 25 food but only 23 are available,
    deficit_fraction = 2/25 = 0.08, so starvation = 0.08 * base rate.

    Returns the number of citizens lost (0 if no starvation).
    """
    if deficit_fraction <= 0:
        return 0

    pop = nation.population or 0
    if pop <= 0:
        return 0

    loss = int(pop * STARVATION_RATE * deficit_fraction)
    loss = max(1, loss)  # lose at least 1
    nation.population = max(0, pop - loss)
    return loss
