"""Shared HTMX response helpers and game utility functions."""

import json
from collections import Counter
from flask import current_app


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


# ── Military helpers ─────────────────────────────────────────────────────

def compute_total_upkeep(nation_id):
    """Sum hourly upkeep across all alive units for a nation."""
    from .models import Unit
    from .game.units import UNIT_DEFS

    upkeep = {}
    for unit in Unit.query.filter_by(nation_id=nation_id).filter(Unit.hp > 0):
        udef = UNIT_DEFS.get(unit.unit_key)
        if not udef:
            continue
        for res, rate in udef.upkeep.items():
            upkeep[res] = upkeep.get(res, 0) + rate
    return upkeep


def build_equipped_counts(nation_id):
    """Build a dict mapping equipment_id -> number of units using that equipment."""
    from .models import Unit

    counts = Counter()
    units = Unit.query.filter_by(nation_id=nation_id).all()
    for u in units:
        for eid in (u.weapon_id, u.accessory_id, u.armour_eq_id):
            if eid:
                counts[eid] += 1
    return dict(counts)
