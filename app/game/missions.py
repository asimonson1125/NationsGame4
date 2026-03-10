"""Mission definitions for NG4.

Each MissionDef specifies:
  enemy_count  — (min, max) total NPC units spawned
  enemy_composition — unit_key → integer percent chance (must sum to 100)

Enemy composition follows the MISSIONS_DATA reference: percent chance determines
which unit type each of the N spawned units will be.
"""
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class MissionDef:
    key: str
    name: str
    rarity: str                          # common|uncommon|rare|epic|legendary
    description: str
    location: str
    rewards: Dict[str, float]            # resource_key -> amount
    enemy_count: Tuple[int, int]         # (min, max) total units to spawn
    enemy_composition: Dict[str, int]    # unit_key -> percent (sum = 100)
    tier_required: int = 1
    cooldown_hours: int = 24
    chapter_requires: Optional[str] = None   # mission key that must be completed first


# Rarity weights for random selection
RARITY_WEIGHTS = {
    'common':    50,
    'uncommon':  30,
    'rare':      12,
    'epic':       6,
    'legendary':  2,
}

RARITY_COOLDOWNS = {
    'common':    12,
    'uncommon':  24,
    'rare':      48,
    'epic':      72,
    'legendary': 168,   # 7 days
}


def _m(**kwargs) -> MissionDef:
    """Shorthand constructor — fills cooldown_hours from rarity."""
    rarity = kwargs['rarity']
    kwargs.setdefault('cooldown_hours', RARITY_COOLDOWNS[rarity])
    return MissionDef(**kwargs)


MISSION_DEFS: Dict[str, MissionDef] = {

    # ── COMMON ──────────────────────────────────────────────────────────────

    'its_the_least_we_can_do': _m(
        key='its_the_least_we_can_do',
        name="It's The Least We Can Do",
        rarity='common',
        description=(
            "The Union of Nations is expecting us to contribute in the fight "
            "against the Bihadj Terrorists."
        ),
        location='Zaheria',
        rewards={'money': 1000, 'ammunition': 20},
        enemy_count=(8, 12),
        enemy_composition={'infantry': 70, 'rpg_infantry': 25, 'm1a1_abrahms': 5},
    ),

    'foreign_affairs': _m(
        key='foreign_affairs',
        name='Foreign Affairs',
        rarity='common',
        description=(
            "Hey! Look over there, Mr. President! *Boom!* *Boom!* "
            "Take the cash and run, dammit!"
        ),
        location='Westberg',
        rewards={'money': 1500},
        enemy_count=(9, 11),
        enemy_composition={'secret_agent': 100},
    ),

    'suppressing_khev_minosk': _m(
        key='suppressing_khev_minosk',
        name='Suppressing the Khev Minosk',
        rarity='common',
        description=(
            "We need to stop the advancements of the terror group Khev Minosk. "
            "Strike with force."
        ),
        location='Westberg',
        rewards={'money': 1000, 'ammunition': 50},
        enemy_count=(8, 12),
        enemy_composition={'infantry': 80, 'rpg_infantry': 20},
    ),

    'riot_control': _m(
        key='riot_control',
        name='Riot Control',
        rarity='common',
        description=(
            "A Westberg member of The Union of Nations is facing serious riot problems "
            "after a shady election, and it is your duty to help them."
        ),
        location='Westberg',
        rewards={'money': 3000},
        enemy_count=(10, 15),
        enemy_composition={'rioter': 100},
    ),

    'chapter_1': _m(
        key='chapter_1',
        name='Chapter 1: Scouting the Bleak Horizon',
        rarity='common',
        description=(
            "Threats are looming, my leader. This world hasn't seen a force this "
            "aggressive in a long, long time. We should send some troops on a scouting "
            "mission before it's too late."
        ),
        location='San Sebastian',
        rewards={'money': 2000},
        enemy_count=(8, 12),
        enemy_composition={'infantry': 50, 'mg_infantry': 30, 'm2_bradley': 20},
        tier_required=6,
    ),

    # ── UNCOMMON ────────────────────────────────────────────────────────────

    'arctic_drill': _m(
        key='arctic_drill',
        name='Arctic Drill',
        rarity='uncommon',
        description=(
            "Every now and then, The Union of Nations hosts a military exercise in the "
            "northernmost regions of Tind. Even though it's infamous for accidental deaths, "
            "joining will strengthen our relations with the Union."
        ),
        location='Tind',
        rewards={'money': 2000},
        enemy_count=(8, 12),
        enemy_composition={'fsk': 40, 'infantry': 30, 'm2_bradley': 30},
    ),

    'dul_kaddir_convoy': _m(
        key='dul_kaddir_convoy',
        name='Dul Kaddir Convoy Interception',
        rarity='uncommon',
        description=(
            "A heavily armed Dul Kaddir convoy is expected to pass through the T'el valley, "
            "opening up an opportunity for us to strike and intercept."
        ),
        location='Zaheria',
        rewards={'metal': 500},
        enemy_count=(6, 10),
        enemy_composition={'volvo_repair_truck': 15, 'm1a1_abrahms': 45, 'm2_bradley': 40},
    ),

    'homeland_offense': _m(
        key='homeland_offense',
        name='Homeland Offense',
        rarity='uncommon',
        description=(
            "To be frank, we don't like Oldenburg. It's an irrelevant little nation on "
            "the continent of Westberg, and its mere existence is annoying. We should attack them a bit."
        ),
        location='Westberg',
        rewards={'money': 2000, 'food': 500},
        enemy_count=(8, 12),
        enemy_composition={'medic': 10, 'national_guard': 90},
    ),

    'rumble_in_the_jungle': _m(
        key='rumble_in_the_jungle',
        name='Rumble In The... Never Mind',
        rarity='uncommon',
        description=(
            "Have you ever been to the jungle? I have heard it's supposed to be warm, "
            "sometimes wet, and full of unpleasant wildlife. We could send a delegation "
            "to steal some of their panthers."
        ),
        location='Amarino',
        rewards={'money': 3000},
        enemy_count=(8, 12),
        enemy_composition={'navy_seals': 95, 'a10_thunderbolt': 5},
    ),

    'supply_raid': _m(
        key='supply_raid',
        name='Supply Raid',
        rarity='uncommon',
        description=(
            "Strategically attacking supply depots of Bihadj outposts can prove valuable."
        ),
        location='Zaheria',
        rewards={'metal': 300, 'ammunition': 200, 'fuel': 200},
        enemy_count=(8, 12),
        enemy_composition={'rpg_infantry': 40, 'infantry': 30, 'm1a1_abrahms': 30},
    ),

    'norrland_wall': _m(
        key='norrland_wall',
        name='The Impenetrable Norrland Wall',
        rarity='uncommon',
        description=(
            "The Norrland conflict has recently escalated and taking the fight to them "
            "may be the only way to make them yield."
        ),
        location='Tind',
        rewards={'metal': 1000, 'building_materials': 500},
        enemy_count=(8, 12),
        enemy_composition={
            'national_guard': 50,
            'concrete_bunker': 20,
            'fortified_bunker': 20,
            '2k22_tunguska': 10,
        },
    ),

    'mortar_rain': _m(
        key='mortar_rain',
        name='The Mortar Rain of Alba Nera',
        rarity='uncommon',
        description=(
            "Exploding hail falling from the skies. Alba Nera neighbours tremble. "
            "Literally. We have to stop this."
        ),
        location='San Sebastian',
        rewards={'ammunition': 500},
        enemy_count=(8, 12),
        enemy_composition={'mortar_infantry': 90, 'medic': 10},
    ),

    'venland_airspace': _m(
        key='venland_airspace',
        name='Venland Airspace Violations',
        rarity='uncommon',
        description=(
            "Oldenburg is constantly harassing Venland with unprecedented airspace violations. "
            "As a Union of Nations member we have been called upon to teach Oldenburg a lesson."
        ),
        location='Westberg',
        rewards={'metal': 500, 'fuel': 500},
        enemy_count=(6, 10),
        enemy_composition={'f_35_lightning_ii': 80, 'a10_thunderbolt': 20},
    ),

    'chapter_2': _m(
        key='chapter_2',
        name='Chapter 2: The Missing Envoy',
        rarity='uncommon',
        description=(
            "Scouting mission?! More like a bear stumbling across a weirdly displaced jar of honey! "
            "Shots fired! The envoy is missing, but his briefcase was left on the scene. "
            "Send some units to fetch it."
        ),
        location='San Sebastian',
        rewards={'money': 3000},
        enemy_count=(8, 12),
        enemy_composition={'infantry': 70, 'navy_seals': 10, 'mq_9_reaper': 20},
        chapter_requires='chapter_1',
    ),

    # ── RARE ────────────────────────────────────────────────────────────────

    'song_of_ice_and_firepower': _m(
        key='song_of_ice_and_firepower',
        name='A Song of Ice and Firepower',
        rarity='rare',
        description=(
            "A rebel state on the continent of Tind has started attacking its neighbors. "
            "This, of course, is not a pleasant situation, and they should be handled with force."
        ),
        location='Tind',
        rewards={'money': 8000},
        enemy_count=(10, 15),
        enemy_composition={'infantry': 50, 'mortar_infantry': 30, 'fsk': 20},
    ),

    'temperate_terrorists': _m(
        key='temperate_terrorists',
        name='Temperate Terrorists',
        rarity='rare',
        description=(
            "The eastern nations of Westberg are experiencing frequent raids by the "
            "terrorist group Khev Minosk, known for their tanks. The mission is to "
            "capture some of their tanks."
        ),
        location='Westberg',
        rewards={'money': 8000, 'metal': 800},
        enemy_count=(10, 15),
        enemy_composition={'infantry': 45, 'rpg_infantry': 25, 'm1a1_abrahms': 30},
    ),

    'jungle_fever': _m(
        key='jungle_fever',
        name='Jungle Fever',
        rarity='rare',
        description=(
            "The feared Followers of Black Horn is one of the reasons why southern Amarino "
            "is in such an unstable state. They are deadly when confronted in the jungle, "
            "but they have to be stopped."
        ),
        location='Amarino',
        rewards={'money': 8000},
        enemy_count=(12, 18),
        enemy_composition={'black_horns': 100},
    ),

    'chapter_3': _m(
        key='chapter_3',
        name='Chapter 3: Neighbouring Nations Tremble',
        rarity='rare',
        description=(
            "This briefcase... This is bad. The Union of Nations inspectors never found "
            "anything like this. We're not prepared. A weapon like this needs a particular "
            "resource to function. We should stop them. For the stability of this world!"
        ),
        location='San Sebastian',
        rewards={'money': 10000, 'uranium': 50},
        enemy_count=(10, 15),
        enemy_composition={
            'national_guard': 25,
            'leopard_2': 20,
            'f_22_raptor': 20,
            'fortified_bunker': 20,
            'concrete_bunker': 10,
            'combat_engineer': 5,
        },
        chapter_requires='chapter_2',
    ),

    # ── EPIC ────────────────────────────────────────────────────────────────

    'ace_of_spades': _m(
        key='ace_of_spades',
        name='Ace of Spades',
        rarity='epic',
        description=(
            'Francesco, the "Ace of Spades," is a legendary mobster with a deep love for '
            "card games. The mission involves attacking his estate to steal the funds "
            "he uses for his card games."
        ),
        location='San Sebastian',
        rewards={'money': 15000},
        enemy_count=(12, 18),
        enemy_composition={'mobster': 80, 'francisco_ace_of_spades': 20},
    ),

    'overseas_investments': _m(
        key='overseas_investments',
        name='Overseas Investments',
        rarity='epic',
        description=(
            "A promising investment opportunity in Dul Kaddir is opposed by the local "
            "government. The mission is to install a new, more friendly government."
        ),
        location='Zaheria',
        rewards={'money': 15000, 'fuel': 1000},
        enemy_count=(12, 18),
        enemy_composition={'infantry': 40, 'rpg_infantry': 30, 'm1a1_abrahms': 30},
    ),

    'the_desert_fox': _m(
        key='the_desert_fox',
        name='The Desert Fox',
        rarity='epic',
        description=(
            'The mission is to eliminate "The Desert Fox," a Bihadj Leader residing in '
            "western Zaheria, to cripple his organization."
        ),
        location='Zaheria',
        rewards={'ammunition': 2000, 'money': 10000},
        enemy_count=(12, 18),
        enemy_composition={'infantry': 55, 'm1a1_abrahms': 25, 'desert_fox_bodyguard': 20},
    ),

    'chapter_4': _m(
        key='chapter_4',
        name='Chapter 4: Preemptive Strike',
        rarity='epic',
        description=(
            "After finding the Yiel uranium facilities empty, the mission is to go for the "
            "snake's head and make Alba Nera burn for their misguided ambitions."
        ),
        location='San Sebastian',
        rewards={'money': 25000, 'uranium': 200},
        enemy_count=(12, 18),
        enemy_composition={
            'national_guard': 20,
            'fortified_bunker': 20,
            'tyz_uav_engineer': 20,
            'a10_thunderbolt': 20,
            'mq_20_avenger': 20,
        },
        chapter_requires='chapter_3',
    ),

    # ── LEGENDARY ───────────────────────────────────────────────────────────

    'thats_not_a_meteorite': _m(
        key='thats_not_a_meteorite',
        name="That's Not a Meteorite",
        rarity='legendary',
        description=(
            "Investigate a strange light near eastern Westberg, initially thought to be a "
            "meteorite, due to reports of heavy fighting."
        ),
        location='Westberg',
        rewards={'money': 50000, 'whz': 5},
        enemy_count=(15, 20),
        enemy_composition={'sectoid': 70, 'sectopod': 30},
    ),

    'chapter_5': _m(
        key='chapter_5',
        name='Chapter 5: The Black Hounds of Alba',
        rarity='legendary',
        description=(
            "After the Alba Nera garrison crumbles, a series of metallic footsteps indicates "
            'a new threat: "The Black Hounds of Alba."'
        ),
        location='San Sebastian',
        rewards={'money': 60000, 'metal': 5000},
        enemy_count=(10, 15),
        enemy_composition={'gearhound_prototype': 70, 'gearhound_warhead': 30},
        chapter_requires='chapter_4',
    ),
}


def get_eligible_missions(nation_tier: int, completed_keys: set) -> List[MissionDef]:
    """Return missions the nation is eligible to see, filtered by tier and chapter chain."""
    eligible = []
    for mdef in MISSION_DEFS.values():
        if mdef.tier_required > nation_tier:
            continue
        if mdef.chapter_requires and mdef.chapter_requires not in completed_keys:
            continue
        eligible.append(mdef)
    return eligible


def roll_two_missions(
    nation_tier: int,
    completed_keys: set,
    exclude_keys: set,
) -> List[MissionDef]:
    """Pick up to 2 distinct eligible missions, weighted by rarity."""
    pool = [m for m in get_eligible_missions(nation_tier, completed_keys)
            if m.key not in exclude_keys]
    if not pool:
        # Fallback: ignore exclusions but still respect tier/chapter
        pool = get_eligible_missions(nation_tier, completed_keys)
    if not pool:
        return []

    weights = [RARITY_WEIGHTS[m.rarity] for m in pool]
    count = min(2, len(pool))
    chosen = []
    remaining_pool = list(pool)
    remaining_weights = list(weights)

    for _ in range(count):
        if not remaining_pool:
            break
        pick = random.choices(remaining_pool, weights=remaining_weights, k=1)[0]
        chosen.append(pick)
        idx = remaining_pool.index(pick)
        remaining_pool.pop(idx)
        remaining_weights.pop(idx)

    return chosen
