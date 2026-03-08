import json
from flask import render_template, request, current_app
from flask_login import login_required, current_user
from .. import db
from ..models import NaturalResource
from ..game.discovery import roll_expansion, roll_colonization, EXPANSION_LAND_TOTAL
from ..game.factories import FACTORY_DEFS
from . import economy

CONTINENTS = ['Westberg', 'Amarino', 'San Sebastian', 'Tind', 'Zaheria']

EXPAND_COST = {
    'money': 7_500_000,
    'food': 1_500_000,
    'building_materials': 1_500_000,
    'consumer_goods': 375_000,
}

COLONIZE_COST = {
    'money': 37_500_000,
    'food': 7_500_000,
    'building_materials': 7_500_000,
    'consumer_goods': 1_875_000,
    'metal': 1_000,
    'fuel': 1_000,
}


def _error_response(message, status=422):
    resp = current_app.response_class(status=status)
    resp.headers['HX-Trigger'] = json.dumps(
        {'showMessage': {'message': message, 'type': 'error'}}
    )
    return resp


def _can_afford(nation, cost_dict):
    for resource, amount in cost_dict.items():
        if (getattr(nation, resource, 0) or 0) < amount:
            return False
    return True


def _deduct_cost(nation, cost_dict):
    for resource, amount in cost_dict.items():
        current = getattr(nation, resource, 0) or 0
        setattr(nation, resource, current - amount)


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


def _apply_land(nation, new_land):
    for land_type, amount in new_land.items():
        current = getattr(nation, land_type, 0) or 0
        setattr(nation, land_type, current + amount)
    nation.total_land = (nation.total_land or 0) + EXPANSION_LAND_TOTAL
    nation.land_gp = (nation.total_land or 0) // 10


def _apply_colonize_land(nation, new_land):
    colonize_total = EXPANSION_LAND_TOTAL * 5
    for land_type, amount in new_land.items():
        current = getattr(nation, land_type, 0) or 0
        setattr(nation, land_type, current + amount)
    nation.total_land = (nation.total_land or 0) + colonize_total
    nation.land_gp = (nation.total_land or 0) // 10


@economy.route('/land')
@login_required
def land():
    nation = current_user.nation
    return render_template(
        'economy/land.html',
        nation=nation,
        expand_cost=EXPAND_COST,
        colonize_cost=COLONIZE_COST,
        continents=CONTINENTS,
    )


@economy.route('/expand-borders', methods=['POST'])
@login_required
def expand_borders():
    nation = current_user.nation
    if not nation:
        return _error_response('No nation found.')
    if not _can_afford(nation, EXPAND_COST):
        return _error_response('Insufficient resources to expand borders.')

    _deduct_cost(nation, EXPAND_COST)
    continent = nation.continent or 'Westberg'
    new_land, discovered = roll_expansion(continent)
    _apply_land(nation, new_land)
    _upsert_resources(nation, discovered)
    db.session.commit()

    resp_html = render_template(
        'economy/partials/expansion_results.html',
        nation=nation,
        new_land=new_land,
        discovered=discovered,
        action='expand',
    )
    resp = current_app.response_class(resp_html, status=200, mimetype='text/html')
    resp.headers['HX-Trigger'] = json.dumps(
        {'showMessage': {'message': 'Borders expanded successfully!', 'type': 'success'}}
    )
    return resp


@economy.route('/colonize', methods=['POST'])
@login_required
def colonize():
    nation = current_user.nation
    if not nation:
        return _error_response('No nation found.')
    if (nation.tier or 1) < 6:
        return _error_response('Colonization requires Tier 6 or higher.')
    if not _can_afford(nation, COLONIZE_COST):
        return _error_response('Insufficient resources to colonize.')

    target_continent = request.form.get('continent', 'Westberg')
    if target_continent not in CONTINENTS:
        return _error_response('Invalid continent selected.')

    _deduct_cost(nation, COLONIZE_COST)
    new_land, discovered = roll_colonization(target_continent)
    _apply_colonize_land(nation, new_land)
    _upsert_resources(nation, discovered)
    db.session.commit()

    resp_html = render_template(
        'economy/partials/expansion_results.html',
        nation=nation,
        new_land=new_land,
        discovered=discovered,
        action='colonize',
    )
    resp = current_app.response_class(resp_html, status=200, mimetype='text/html')
    resp.headers['HX-Trigger'] = json.dumps(
        {'showMessage': {'message': f'Colonized {target_continent} successfully!', 'type': 'success'}}
    )
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
    resp.headers['HX-Trigger'] = json.dumps(
        {'showMessage': {'message': f'Purchased {amount:,} cleared land tiles.', 'type': 'success'}}
    )
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
    resp.headers['HX-Trigger'] = json.dumps(
        {'showMessage': {'message': f'Built {amount:,} urban area tiles.', 'type': 'success'}}
    )
    return resp


@economy.route('/industry')
@login_required
def industry():
    nation = current_user.nation
    factory_map = {}
    if nation:
        for nf in nation.factories:
            factory_map[nf.factory_key] = nf
    return render_template(
        'economy/industry.html',
        nation=nation,
        factory_defs=FACTORY_DEFS,
        factory_map=factory_map,
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

    if (nation.tier or 1) < fdef.tier:
        return _error_response(f'{fdef.name} requires Tier {fdef.tier}.')

    # Check land
    for land_type, per_factory in fdef.land_required.items():
        needed = qty * per_factory
        available = getattr(nation, land_type, 0) or 0
        if available < needed:
            label = land_type.replace('_', ' ').title()
            return _error_response(f'Insufficient {label}. Need {needed:,}, have {available:,}.')

    # Check resources
    total_cost = {res: qty * rate for res, rate in fdef.build_cost.items()}
    if not _can_afford(nation, total_cost):
        for res, needed in total_cost.items():
            if (getattr(nation, res, 0) or 0) < needed:
                return _error_response(
                    f'Insufficient {res.replace("_", " ")}. Need {needed:,}.'
                )

    # Deduct land
    for land_type, per_factory in fdef.land_required.items():
        current = getattr(nation, land_type, 0) or 0
        setattr(nation, land_type, current - qty * per_factory)
    nation.used_land = (nation.used_land or 0) + qty * sum(fdef.land_required.values())

    # Deduct build costs
    _deduct_cost(nation, total_cost)

    # Upsert factory record
    nf = NationFactory.query.filter_by(nation_id=nation.id, factory_key=factory_key).first()
    if nf:
        nf.count += qty
    else:
        nf = NationFactory(nation_id=nation.id, factory_key=factory_key, count=qty, production_capacity=0)
        db.session.add(nf)

    nation.factory_gp = (nation.factory_gp or 0) + qty * fdef.gp_value
    db.session.commit()

    factory_map = {nf_item.factory_key: nf_item for nf_item in nation.factories}
    resp_html = render_template(
        'economy/partials/industry_content.html',
        nation=nation,
        factory_defs=FACTORY_DEFS,
        factory_map=factory_map,
        default_tab='build',
    )
    resp = current_app.response_class(resp_html, status=200, mimetype='text/html')
    resp.headers['HX-Trigger'] = json.dumps({
        'showMessage': {'message': f'Built {qty}x {fdef.name}.', 'type': 'success'},
        'refreshResourceFooter': True,
    })
    return resp


@economy.route('/industry/collect/<factory_key>', methods=['POST'])
@login_required
def collect_factory(factory_key):
    from ..models import NationFactory
    nation = current_user.nation
    if not nation:
        return _error_response('No nation found.')

    fdef = FACTORY_DEFS.get(factory_key)
    if not fdef:
        return _error_response('Unknown factory type.')

    nf = NationFactory.query.filter_by(nation_id=nation.id, factory_key=factory_key).first()
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
        available = getattr(nation, resource, 0) or 0
        if available < needed:
            return _error_response(
                f'Insufficient {resource}. Need {needed:,.1f}, have {available:,.1f}.'
            )

    # Deduct inputs
    for resource, rate in fdef.inputs.items():
        needed = rate * nf.count * hours
        current = getattr(nation, resource, 0) or 0
        setattr(nation, resource, current - needed)

    # Add outputs
    for resource, rate in fdef.outputs.items():
        gained = rate * nf.count * hours
        current = getattr(nation, resource, 0) or 0
        setattr(nation, resource, current + gained)

    nf.production_capacity -= hours
    db.session.commit()

    resp = current_app.response_class(status=204)
    resp.headers['HX-Trigger'] = json.dumps({
        'showMessage': {'message': f'Collected {hours}h of {fdef.name} output.', 'type': 'success'},
        'refreshResourceFooter': True,
    })
    return resp
