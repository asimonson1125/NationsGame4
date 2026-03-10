import json
from datetime import datetime, timedelta, timezone
from flask import render_template, request, current_app
from flask_login import login_required, current_user
from .. import db
from ..models import NaturalResource, FactoryBuildQueue
from ..helpers import error_response as _error_response, can_afford as _can_afford, deduct_cost as _deduct_cost
from ..game.constants import CONTINENTS
from ..game.discovery import roll_expansion, roll_colonization
from ..game.factories import FACTORY_DEFS
from . import economy

_EXPAND_COOLDOWN = 60       # seconds between expand attempts
_COLONIZE_COOLDOWN = 60    # seconds between colonize attempts
_MAX_LAND_TX = 10_000      # tiles per buy/build transaction
_MAX_BUILD_QTY = 100       # factories per build transaction


def get_expand_cost(population):
    pop = population or 0
    return {
        'money': pop / 10,
        'food': pop / 50,
        'building_materials': pop / 50,
        'consumer_goods': pop / 200,
    }


def get_colonize_cost(population):
    pop = population or 0
    return {
        'money': (pop / 10) * 5,
        'food': (pop / 50) * 5,
        'building_materials': (pop / 50) * 5,
        'consumer_goods': (pop / 200) * 5,
        'metal': 1000,
        'fuel': 1000,
    }


def _upsert_resources(nation, discovered):
    for resource_key, amount in discovered.items():
        nr = NaturalResource.query.filter_by(
            nation_id=nation.id, resource_key=resource_key
        ).first()
        if nr:
            nr.amount += amount
        else:
            nr = NaturalResource(nation_id=nation.id, resource_key=resource_key, amount=amount)
            db.session.add(nr)


def _apply_land(nation, new_land, total_gained):
    for land_type, amount in new_land.items():
        nation.add_resource(land_type, amount)
    nation.total_land = (nation.total_land or 0) + total_gained
    nation.land_gp = (nation.total_land or 0) // 10


@economy.route('/land')
@login_required
def land():
    nation = current_user.nation
    natural_resources = NaturalResource.query.filter_by(nation_id=nation.id).order_by(NaturalResource.amount.desc()).all()
    return render_template(
        'economy/land.html',
        nation=nation,
        expand_cost=get_expand_cost(nation.population),
        colonize_cost=get_colonize_cost(nation.population),
        continents=CONTINENTS,
        natural_resources=natural_resources,
    )


@economy.route('/expand-borders', methods=['POST'])
@login_required
def expand_borders():
    nation = current_user.nation
    if not nation:
        return _error_response('No nation found.')

    if nation.last_expanded_at:
        elapsed = (datetime.utcnow() - nation.last_expanded_at).total_seconds()
        if elapsed < _EXPAND_COOLDOWN:
            remaining = int(_EXPAND_COOLDOWN - elapsed)
            return _error_response(f'Please wait {remaining}s before expanding again.')

    cost = get_expand_cost(nation.population)
    if not _can_afford(nation, cost):
        return _error_response('Insufficient resources to expand borders.')

    _deduct_cost(nation, cost)
    nation.last_expanded_at = datetime.utcnow()
    continent = nation.continent or 'Westberg'
    new_land, discovered, total_gained = roll_expansion(continent, nation.population)
    _apply_land(nation, new_land, total_gained)
    _upsert_resources(nation, discovered)
    db.session.commit()

    resp_html = render_template(
        'economy/partials/expansion_results.html',
        nation=nation,
        new_land=new_land,
        discovered=discovered,
        action='expand',
        total_gained=total_gained,
    )
    resp = current_app.response_class(resp_html, status=200, mimetype='text/html')
    resp.headers['HX-Trigger'] = json.dumps({
        'showMessage': {'message': 'Borders expanded successfully!', 'type': 'success'},
        'refreshResourceFooter': True,
        'showExpansionModal': True,
    })
    return resp


@economy.route('/colonize', methods=['POST'])
@login_required
def colonize():
    nation = current_user.nation
    if not nation:
        return _error_response('No nation found.')
    if (nation.tier or 1) < 6:
        return _error_response('Colonization requires Tier 6 or higher.')

    if nation.last_colonized_at:
        elapsed = (datetime.utcnow() - nation.last_colonized_at).total_seconds()
        if elapsed < _COLONIZE_COOLDOWN:
            remaining = int(_COLONIZE_COOLDOWN - elapsed)
            return _error_response(f'Please wait {remaining}s before colonizing again.')

    cost = get_colonize_cost(nation.population)
    if not _can_afford(nation, cost):
        return _error_response('Insufficient resources to colonize.')

    target_continent = request.form.get('continent', 'Westberg')
    if target_continent not in CONTINENTS:
        return _error_response('Invalid continent selected.')

    _deduct_cost(nation, cost)
    nation.last_colonized_at = datetime.utcnow()
    new_land, discovered, total_gained = roll_colonization(target_continent, nation.population)
    _apply_land(nation, new_land, total_gained)
    _upsert_resources(nation, discovered)
    db.session.commit()

    resp_html = render_template(
        'economy/partials/expansion_results.html',
        nation=nation,
        new_land=new_land,
        discovered=discovered,
        action='colonize',
        total_gained=total_gained,
    )
    resp = current_app.response_class(resp_html, status=200, mimetype='text/html')
    resp.headers['HX-Trigger'] = json.dumps({
        'showMessage': {'message': f'Colonized {target_continent} successfully!', 'type': 'success'},
        'refreshResourceFooter': True,
        'showExpansionModal': True,
    })
    return resp


@economy.route('/buy-cleared-land', methods=['POST'])
@login_required
def buy_cleared_land():
    nation = current_user.nation
    if not nation:
        return _error_response('No nation found.')
    try:
        amount = int(request.form.get('buy_amount', 0))
    except (ValueError, TypeError):
        return _error_response('Invalid amount.')
    if amount <= 0:
        return _error_response('Amount must be greater than zero.')
    if amount > _MAX_LAND_TX:
        return _error_response(f'Cannot purchase more than {_MAX_LAND_TX:,} tiles at once.')

    cost = amount * 1000
    if (nation.money or 0) < cost:
        return _error_response(f'Insufficient money. Need {cost:,} money.')

    nation.money = (nation.money or 0) - cost
    nation.cleared_land = (nation.cleared_land or 0) + amount
    nation.total_land = (nation.total_land or 0) + amount
    nation.land_gp = (nation.total_land or 0) // 10
    db.session.commit()

    land_panel_html = render_template('economy/partials/land_panel.html', nation=nation)
    resp = current_app.response_class(land_panel_html, status=200, mimetype='text/html')
    resp.headers['HX-Trigger'] = json.dumps({
        'showMessage': {'message': f'Purchased {amount:,} cleared land tiles.', 'type': 'success'},
        'refreshResourceFooter': True,
    })
    return resp


@economy.route('/build-urban-areas', methods=['POST'])
@login_required
def build_urban_areas():
    nation = current_user.nation
    if not nation:
        return _error_response('No nation found.')
    try:
        amount = int(request.form.get('build_amount', 0))
    except (ValueError, TypeError):
        return _error_response('Invalid amount.')
    if amount <= 0:
        return _error_response('Amount must be greater than zero.')
    if amount > _MAX_LAND_TX:
        return _error_response(f'Cannot build more than {_MAX_LAND_TX:,} urban tiles at once.')

    cleared = nation.cleared_land or 0
    if cleared < amount:
        return _error_response(f'Not enough cleared land. Have {cleared:,}, need {amount:,}.')

    cost = amount * 500
    if (nation.money or 0) < cost:
        return _error_response(f'Insufficient money. Need {cost:,} money.')

    nation.money = (nation.money or 0) - cost
    nation.cleared_land = cleared - amount
    nation.urban_areas = (nation.urban_areas or 0) + amount
    db.session.commit()

    land_panel_html = render_template('economy/partials/land_panel.html', nation=nation)
    resp = current_app.response_class(land_panel_html, status=200, mimetype='text/html')
    resp.headers['HX-Trigger'] = json.dumps({
        'showMessage': {'message': f'Built {amount:,} urban area tiles.', 'type': 'success'},
        'refreshResourceFooter': True,
    })
    return resp


@economy.route('/convert-to-cleared-land', methods=['POST'])
@login_required
def convert_to_cleared_land():
    nation = current_user.nation
    if not nation:
        return _error_response('No nation found.')

    land_type = request.form.get('land_type')
    valid_types = ['forest', 'grassland', 'jungle', 'mountain', 'desert', 'tundra']
    if land_type not in valid_types:
        return _error_response('Invalid land type.')

    try:
        amount = int(request.form.get('convert_amount', 0))
    except (ValueError, TypeError):
        return _error_response('Invalid amount.')

    if amount <= 0:
        return _error_response('Amount must be greater than zero.')
    if amount > _MAX_LAND_TX:
        return _error_response(f'Cannot convert more than {_MAX_LAND_TX:,} tiles at once.')

    current_tiles = getattr(nation, land_type, 0)
    if current_tiles < amount:
        return _error_response(f'Not enough {land_type.replace("_", " ")}. Have {current_tiles:,}, need {amount:,}.')

    cost = amount * 100
    if (nation.money or 0) < cost:
        return _error_response(f'Insufficient money. Need {cost:,} money.')

    # Deduct cost and land, add to cleared_land
    nation.money = (nation.money or 0) - cost
    setattr(nation, land_type, current_tiles - amount)
    nation.cleared_land = (nation.cleared_land or 0) + amount
    db.session.commit()

    land_panel_html = render_template('economy/partials/land_panel.html', nation=nation)
    resp = current_app.response_class(land_panel_html, status=200, mimetype='text/html')
    resp.headers['HX-Trigger'] = json.dumps({
        'showMessage': {'message': f'Converted {amount:,} {land_type} tiles to cleared land.', 'type': 'success'},
        'refreshResourceFooter': True,
    })
    return resp


@economy.route('/industry')
@login_required
def industry():
    nation = current_user.nation
    factory_map = {}
    build_queue = []
    if nation:
        for nf in nation.factories:
            factory_map[nf.factory_key] = nf
        build_queue = FactoryBuildQueue.query.filter_by(nation_id=nation.id).all()
    # Build a map of factory_key -> list of queue entries for template use
    queue_map = {}
    for entry in build_queue:
        queue_map.setdefault(entry.factory_key, []).append(entry)
    return render_template(
        'economy/industry.html',
        nation=nation,
        factory_defs=FACTORY_DEFS,
        factory_map=factory_map,
        build_queue=build_queue,
        queue_map=queue_map,
    )


@economy.route('/industry/build', methods=['POST'])
@login_required
def build_factory():
    from ..models import NationFactory
    nation = current_user.nation
    if not nation:
        return _error_response('No nation found.')

    factory_key = request.form.get('factory_key', '').strip()
    fdef = FACTORY_DEFS.get(factory_key)
    if not fdef:
        return _error_response('Unknown factory type.')

    try:
        qty = int(request.form.get('amount', 1))
    except (ValueError, TypeError):
        return _error_response('Invalid amount.')
    if qty < 1:
        return _error_response('Amount must be at least 1.')
    if qty > _MAX_BUILD_QTY:
        return _error_response(f'Cannot build more than {_MAX_BUILD_QTY} factories at once.')

    if (nation.tier or 1) < fdef.tier:
        return _error_response(f'{fdef.name} requires Tier {fdef.tier}.')

    # Check land
    for land_type, per_factory in fdef.land_required.items():
        needed = qty * per_factory
        available = nation.get_resource(land_type)
        if available < needed:
            label = land_type.replace('_', ' ').title()
            return _error_response(f'Insufficient {label}. Need {needed:,}, have {available:,}.')

    # Check resources
    total_cost = {res: qty * rate for res, rate in fdef.build_cost.items()}
    if not _can_afford(nation, total_cost):
        for res, needed in total_cost.items():
            if nation.get_resource(res) < needed:
                return _error_response(
                    f'Insufficient {res.replace("_", " ")}. Need {needed:,}.'
                )

    # Deduct land
    for land_type, per_factory in fdef.land_required.items():
        nation.add_resource(land_type, -qty * per_factory)
    nation.used_land = (nation.used_land or 0) + qty * sum(fdef.land_required.values())

    # Deduct build costs
    _deduct_cost(nation, total_cost)

    # Queue the build instead of instant completion
    now = datetime.now(timezone.utc)
    new_completes_at = now + timedelta(minutes=fdef.build_time)

    # Check for existing queue entry of same type completing within 5 min
    existing = FactoryBuildQueue.query.filter_by(
        nation_id=nation.id, factory_key=factory_key
    ).filter(
        FactoryBuildQueue.completes_at >= new_completes_at - timedelta(minutes=5),
        FactoryBuildQueue.completes_at <= new_completes_at + timedelta(minutes=5),
    ).first()

    if existing:
        existing.quantity += qty
        if new_completes_at > existing.completes_at:
            existing.completes_at = new_completes_at
    else:
        entry = FactoryBuildQueue(
            nation_id=nation.id,
            factory_key=factory_key,
            quantity=qty,
            completes_at=new_completes_at,
        )
        db.session.add(entry)

    db.session.commit()

    factory_map = {nf_item.factory_key: nf_item for nf_item in nation.factories}
    build_queue = FactoryBuildQueue.query.filter_by(nation_id=nation.id).all()
    queue_map = {}
    for e in build_queue:
        queue_map.setdefault(e.factory_key, []).append(e)
    resp_html = render_template(
        'economy/partials/industry_content.html',
        nation=nation,
        factory_defs=FACTORY_DEFS,
        factory_map=factory_map,
        build_queue=build_queue,
        queue_map=queue_map,
        default_tab='build',
    )
    resp = current_app.response_class(resp_html, status=200, mimetype='text/html')
    resp.headers['HX-Trigger'] = json.dumps({
        'showMessage': {'message': f'Queued {qty}x {fdef.name} — completes in {_format_duration(fdef.build_time)}.', 'type': 'success'},
        'refreshResourceFooter': True,
    })
    return resp


def _format_duration(minutes):
    """Format minutes into a human-readable duration string."""
    if minutes < 60:
        return f'{minutes}m'
    hours = minutes // 60
    mins = minutes % 60
    if hours < 24:
        return f'{hours}h {mins}m' if mins else f'{hours}h'
    days = hours // 24
    remaining_hours = hours % 24
    if remaining_hours:
        return f'{days}d {remaining_hours}h'
    return f'{days}d'


@economy.route('/industry/collect/<factory_key>', methods=['POST'])
@login_required
def collect_factory(factory_key):
    from ..models import NationFactory
    nation = current_user.nation
    if not nation:
        return _error_response('No nation found.')
    if current_user.vacation_mode:
        return _error_response('Vacation mode is active. Disable it to collect.')

    fdef = FACTORY_DEFS.get(factory_key)
    if not fdef:
        return _error_response('Unknown factory type.')

    nf = NationFactory.query.filter_by(
        nation_id=nation.id, factory_key=factory_key
    ).with_for_update().first()
    if not nf or nf.count == 0:
        return _error_response('You do not have this factory.')

    if nf.production_capacity == 0:
        return _error_response('No production capacity available. Wait for it to regenerate.')

    try:
        hours = int(request.form.get('hours', fdef.max_collect_hours))
    except (ValueError, TypeError):
        hours = fdef.max_collect_hours

    hours = max(1, min(hours, fdef.max_collect_hours, nf.production_capacity))

    # Check inputs
    for resource, rate in fdef.inputs.items():
        needed = rate * nf.count * hours
        available = nation.get_resource(resource)
        if available < needed:
            return _error_response(
                f'Insufficient {resource}. Need {needed:,.1f}, have {available:,.1f}.'
            )

    # Deduct inputs
    for resource, rate in fdef.inputs.items():
        nation.add_resource(resource, -(rate * nf.count * hours))

    # Add outputs
    for resource, rate in fdef.outputs.items():
        nation.add_resource(resource, rate * nf.count * hours)

    nf.production_capacity -= hours
    db.session.commit()

    resp = current_app.response_class(status=204)
    resp.headers['HX-Trigger'] = json.dumps({
        'showMessage': {'message': f'Collected {hours}h of {fdef.name} output.', 'type': 'success'},
        'refreshResourceFooter': True,
        'collect-success': {'factoryKey': factory_key, 'collected': hours, 'newCapacity': nf.production_capacity},
    })
    return resp
