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
