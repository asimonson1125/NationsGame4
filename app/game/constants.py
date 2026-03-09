"""Shared game constants used across factory, unit, and equipment definitions."""

# Resource key aliases — short names for use in factory/unit definitions
_M  = 'money'
_P  = 'power'
_F  = 'food'
_BM = 'building_materials'
_CG = 'consumer_goods'
_ME = 'metal'
_AM = 'ammunition'
_FU = 'fuel'
_UR = 'uranium'
_WH = 'whz'

# Playable continents
CONTINENTS = ['Westberg', 'Amarino', 'San Sebastian', 'Tind', 'Zaheria']

# Trade system
TRADE_FEE_PERCENT = 5  # 5% fee deducted from seller proceeds

TRADEABLE_COMMODITIES = [
    'food', 'power', 'building_materials', 'consumer_goods',
    'metal', 'fuel', 'ammunition', 'uranium', 'whz',
]

TRADEABLE_NATURAL_RESOURCES = [
    'coal', 'iron', 'uraninite', 'petroleum', 'marble', 'copper', 'lead',
    'silver', 'gold', 'platinum', 'silicon', 'sulfur', 'rubber_tree',
    'cocoa', 'cow', 'sheep', 'goat', 'salmon', 'elephant',
    'apple_tree', 'oak_tree', 'cactus',
]
