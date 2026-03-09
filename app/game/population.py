# Population effects per capita per hour.
# Positive = nation gains resources; negative = nation loses resources.
POPULATION_RATES = {
    'money': 0.002,            # tax income
    'food': -0.0005,           # food consumption
    'consumer_goods': -0.0001, # consumer goods usage
    'power': -0.0002,          # power usage
}


def get_population_effects(population):
    """Returns dict of resource -> hourly amount for the given population."""
    pop = population or 0
    return {res: pop * rate for res, rate in POPULATION_RATES.items()}
