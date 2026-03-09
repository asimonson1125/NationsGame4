# Population effects per capita per hour.
# Positive = nation gains resources; negative = nation loses resources.
# Rates expressed as 1/N where N = people per unit per hour.
POPULATION_RATES = {
    'money':           1/100,   # 100 people per tax dollar
    'food':           -1/2000, # 2000 people per food
    'power':          -1/2500, # 2500 people per power
    'consumer_goods': -1/5000, # 5000 people per consumer goods
}


def get_population_effects(population):
    """Returns dict of resource -> hourly amount for the given population."""
    pop = population or 0
    return {res: pop * rate for res, rate in POPULATION_RATES.items()}
