"""Shared HTMX response helpers and game utility functions."""

import json
from collections import Counter
from flask import current_app


# ── Nation search ────────────────────────────────────────────────────────

def nation_search_query(q, *, exclude_id=None, search_leader=False):
    """Return a filtered Nation.query for the given search string.

    Callers apply .limit(), .order_by(), .options() etc. themselves.

    Args:
        q: search string (caller is responsible for min-length guard)
        exclude_id: omit this nation ID from results (e.g. current user's nation)
        search_leader: also match against Nation.leader column
    """
    from .models import Nation
    from . import db
    if search_leader:
        name_filter = db.or_(Nation.name.ilike(f'%{q}%'), Nation.leader.ilike(f'%{q}%'))
    else:
        name_filter = Nation.name.ilike(f'%{q}%')
    query = Nation.query.filter(name_filter)
    if exclude_id is not None:
        query = query.filter(Nation.id != exclude_id)
    return query


# ── HTMX response builders ──────────────────────────────────────────────

def htmx_response(html='', message='', msg_type='success', status=200,
                  extra_triggers=None):
    """Build a Flask response with HX-Trigger containing showMessage and
    refreshResourceFooter, plus any extra trigger keys."""
    resp = current_app.make_response(html)
    resp.status_code = status
    triggers = {}
    if message:
        triggers['showMessage'] = {'message': message, 'type': msg_type}
    triggers['refreshResourceFooter'] = True
    if extra_triggers:
        triggers.update(extra_triggers)
    resp.headers['HX-Trigger'] = json.dumps(triggers)
    return resp


def error_response(message, status=422):
    resp = current_app.response_class(status=status)
    resp.headers['HX-Trigger'] = json.dumps(
        {'showMessage': {'message': message, 'type': 'error'}}
    )
    return resp


def success_response(message, html='', status=200, extra_triggers=None):
    return htmx_response(html=html, message=message, msg_type='success',
                         status=status, extra_triggers=extra_triggers)


# ── Resource affordability helpers ───────────────────────────────────────

def can_afford(nation, cost_dict):
    for resource, amount in cost_dict.items():
        if nation.get_resource(resource) < amount:
            return False
    return True


def deduct_cost(nation, cost_dict):
    for resource, amount in cost_dict.items():
        nation.add_resource(resource, -amount)


# ── Factory helpers ──────────────────────────────────────────────────────

def grant_factories(nation, factories, production_capacity=0):
    """Upsert NationFactory rows and credit factory_gp.

    factories: iterable of (factory_key, count) tuples
    """
    from .models import NationFactory
    from .game.factories import FACTORY_DEFS

    for factory_key, count in factories:
        fdef = FACTORY_DEFS.get(factory_key)
        if not fdef:
            continue
        nf = NationFactory.query.filter_by(
            nation_id=nation.id, factory_key=factory_key
        ).first()
        if nf:
            nf.count += count
        else:
            from . import db
            nf = NationFactory(
                nation_id=nation.id,
                factory_key=factory_key,
                count=count,
                production_capacity=production_capacity,
            )
            db.session.add(nf)
        nation.factory_gp = (nation.factory_gp or 0) + count * fdef.gp_value


# ── Military helpers ─────────────────────────────────────────────────────

def compute_total_upkeep(nation_id):
    """Sum hourly upkeep across all alive units for a nation.

    Demobilized units (in a demobilized division or unassigned) only pay
    their money upkeep — all other resource costs are waived.
    """
    from .models import Unit, Division
    from .game.units import UNIT_DEFS
    from . import db
    from sqlalchemy import func, case

    upkeep = {}

    # Label each unit as mobilized or not based on its division's state.
    # Units without a division are treated as demobilized.
    is_mobilized = case(
        (Division.mobilization_state.in_(['mobilized', 'mobilizing']), True),
        else_=False,
    )

    groups = (
        db.session.query(Unit.unit_key, is_mobilized, func.count(Unit.id))
        .outerjoin(Division, db.and_(
            Division.id == Unit.division_id,
            Division.nation_id == Unit.nation_id,
        ))
        .filter(Unit.nation_id == nation_id, Unit.hp > 0)
        .group_by(Unit.unit_key, is_mobilized)
        .all()
    )

    for unit_key, mobilized, count in groups:
        udef = UNIT_DEFS.get(unit_key)
        if not udef:
            continue
        if mobilized:
            for res, rate in udef.upkeep.items():
                upkeep[res] = upkeep.get(res, 0) + (rate * count)
        else:
            # Demobilized: money upkeep only
            money_rate = udef.upkeep.get('money', 0)
            if money_rate:
                upkeep['money'] = upkeep.get('money', 0) + (money_rate * count)
    return upkeep


def build_equipped_counts(nation_id):
    """Build a dict mapping equipment_id -> number of units using that equipment."""
    from .models import Unit
    from . import db
    from sqlalchemy import func

    counts = Counter()
    # Query weapons, accessories, and armour separately and sum them
    # This is much faster than loading all Unit objects into memory
    for field in (Unit.weapon_id, Unit.accessory_id, Unit.armour_eq_id):
        results = db.session.query(field, func.count(Unit.id)).filter(
            Unit.nation_id == nation_id,
            field != None
        ).group_by(field).all()
        for eid, count in results:
            counts[eid] += count

    return dict(counts)
