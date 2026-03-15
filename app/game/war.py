"""War game logic — score computation, settlement resolution, peace."""
from datetime import datetime, timezone

RESOURCE_KEYS = [
    'money', 'food', 'power', 'building_materials', 'consumer_goods',
    'metal', 'fuel', 'ammunition', 'uranium', 'whz',
]

LAND_KEYS = [
    'total_land', 'cleared_land', 'urban_areas', 'used_land',
    'forest', 'grassland', 'jungle', 'desert', 'mountain', 'tundra',
    'river', 'lake',
]


def compute_war_scores(war):
    """Return dict describing score state and what each side can demand.

    Computed from live WarBattle + Battle records to stay accurate even if
    cached War.attacker_victories / defender_victories drift out of sync.
    """
    from ..models import WarBattle, Battle

    war_battles = WarBattle.query.filter_by(war_id=war.id).all()
    atk_v = 0
    def_v = 0
    for wb in war_battles:
        battle = Battle.query.filter_by(
            id=wb.battle_id, attacker_nation_id=wb.attacker_nation_id
        ).first()
        if not battle or battle.status != 'finished':
            continue
        if wb.side == 'attacker':
            if battle.winner == 'attacker':
                atk_v += 1
            else:
                def_v += 1
        else:
            if battle.winner == 'attacker':
                def_v += 1
            else:
                atk_v += 1

    atk_lead = atk_v - def_v
    def_lead = def_v - atk_v
    return {
        'attacker_victories': atk_v,
        'defender_victories': def_v,
        'attacker_can_demand': atk_lead >= 3,
        'defender_can_demand': def_lead >= 3,
        'attacker_lead': atk_lead,
        'defender_lead': def_lead,
    }


def count_offensive_victories(war, nation_id):
    """Count battles where nation_id was the deploying attacker and won."""
    from ..models import WarBattle, Battle
    side = 'attacker' if nation_id == war.attacker_nation_id else 'defender'
    war_battles = WarBattle.query.filter_by(war_id=war.id, side=side).all()
    count = 0
    for wb in war_battles:
        battle = Battle.query.filter_by(
            id=wb.battle_id, attacker_nation_id=wb.attacker_nation_id
        ).first()
        if battle and battle.winner == 'attacker':
            count += 1
    return count


def resolve_war_compensation(war, demanding_nation_id, db_session):
    """Transfer 35% of the losing nation's resource stockpiles to the winner.

    Returns {'winner_id': int, 'loser_id': int, 'transfers': {key: amount}}
    with only non-zero transfers included.
    """
    from ..models import Nation
    if demanding_nation_id == war.attacker_nation_id:
        winner_id, loser_id = war.attacker_nation_id, war.defender_nation_id
    else:
        winner_id, loser_id = war.defender_nation_id, war.attacker_nation_id

    winner = db_session.get(Nation, winner_id)
    loser = db_session.get(Nation, loser_id)
    transfers = {}
    for key in RESOURCE_KEYS:
        transfer = (getattr(loser, key) or 0.0) * 0.35
        if transfer > 0:
            setattr(loser, key, max(0.0, (getattr(loser, key) or 0.0) - transfer))
            setattr(winner, key, (getattr(winner, key) or 0.0) + transfer)
            transfers[key] = transfer

    war.status = 'compensated'
    war.ended_at = datetime.now(timezone.utc)
    return {'winner_id': winner_id, 'loser_id': loser_id, 'transfers': transfers}


def resolve_war_annexation(war, demanding_nation_id, db_session):
    """Transfer 20% of the losing nation's land and population to the winner.

    Returns {'winner_id': int, 'loser_id': int,
             'population': int, 'land': {key: amount}} with only non-zero values.
    """
    from ..models import Nation
    if demanding_nation_id == war.attacker_nation_id:
        winner_id, loser_id = war.attacker_nation_id, war.defender_nation_id
    else:
        winner_id, loser_id = war.defender_nation_id, war.attacker_nation_id

    winner = db_session.get(Nation, winner_id)
    loser = db_session.get(Nation, loser_id)

    pop_transfer = int((loser.population or 0) * 0.20)
    loser.population = max(0, (loser.population or 0) - pop_transfer)
    winner.population = (winner.population or 0) + pop_transfer

    land_transfers = {}
    for key in LAND_KEYS:
        transfer = int((getattr(loser, key) or 0) * 0.20)
        if transfer > 0:
            setattr(loser, key, max(0, (getattr(loser, key) or 0) - transfer))
            setattr(winner, key, (getattr(winner, key) or 0) + transfer)
            land_transfers[key] = transfer

    war.status = 'annexed'
    war.ended_at = datetime.now(timezone.utc)
    return {
        'winner_id': winner_id, 'loser_id': loser_id,
        'population': pop_transfer, 'land': land_transfers,
    }


def resolve_white_peace(war):
    """End the war with no transfers."""
    war.status = 'peace'
    war.ended_at = datetime.now(timezone.utc)


def credit_war_victory(war, war_battle, battle_winner):
    """Credit a battle outcome to the correct war participant's victory count.

    battle_winner: 'attacker' or 'defender' (from Battle.winner).
    war_battle.side: 'attacker' if war.attacker_nation sent this deployment,
                     'defender' if war.defender_nation sent it.
    """
    if war_battle.side == 'attacker':
        # War attacker sent this deployment; they were the battle attacker.
        if battle_winner == 'attacker':
            war.attacker_victories += 1
        else:
            war.defender_victories += 1
    else:
        # War defender sent this counter-deployment; they were the battle attacker.
        if battle_winner == 'attacker':
            war.defender_victories += 1
        else:
            war.attacker_victories += 1


def get_active_war(nation_a_id, nation_b_id):
    """Return the active War between two nations, or None."""
    from ..models import War
    from sqlalchemy import or_, and_
    return War.query.filter(
        War.status == 'active',
        or_(
            and_(War.attacker_nation_id == nation_a_id,
                 War.defender_nation_id == nation_b_id),
            and_(War.attacker_nation_id == nation_b_id,
                 War.defender_nation_id == nation_a_id),
        )
    ).first()


def get_nation_active_wars(nation_id):
    """Return all active wars involving a nation."""
    from ..models import War
    from sqlalchemy import or_
    return War.query.filter(
        War.status == 'active',
        or_(War.attacker_nation_id == nation_id,
            War.defender_nation_id == nation_id),
    ).order_by(War.declared_at.desc()).all()
