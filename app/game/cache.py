"""Cached accessors for static game data.

These wrap the module-level dicts (already fast singletons) with
Flask-Caching so the pattern is established for future DB-backed caches
(e.g. leaderboard, market listings).
"""

from app import cache


@cache.cached(timeout=0, key_prefix='factory_defs')
def get_factory_defs():
    from .factories import FACTORY_DEFS
    return FACTORY_DEFS


@cache.cached(timeout=0, key_prefix='unit_defs')
def get_unit_defs():
    from .units import UNIT_DEFS
    return UNIT_DEFS


@cache.cached(timeout=0, key_prefix='land_weights')
def get_land_weights():
    from .discovery import LAND_WEIGHTS
    return LAND_WEIGHTS


@cache.cached(timeout=0, key_prefix='resource_weights')
def get_resource_weights():
    from .discovery import RESOURCE_WEIGHTS
    return RESOURCE_WEIGHTS
