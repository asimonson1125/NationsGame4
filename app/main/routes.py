import json
from functools import wraps
from flask import render_template, url_for, request, current_app, abort, jsonify, make_response
from flask_login import login_required, current_user
from .. import db
from ..models import Nation, NationFactory, NaturalResource, Alliance, Division, Unit, RecruitmentQueue
from ..helpers import error_response as _error_response, compute_total_upkeep
from ..game.population import get_population_effects, estimate_pop_delta, FOOD_PER_CITIZEN
from ..game.factories import FACTORY_DEFS
from ..game.units import UNIT_DEFS
from . import main


def _nation_summary(nation):
    """Build summary data dict for nation profile display."""
    # Factory summary: list of (display_name, count) for factories with count > 0
    factories = NationFactory.query.filter_by(nation_id=nation.id).filter(NationFactory.count > 0).all()
    factory_summary = []
    total_factories = 0
    for f in factories:
        fdef = FACTORY_DEFS.get(f.factory_key)
        name = fdef.name if fdef else f.factory_key.replace('_', ' ').title()
        factory_summary.append((name, f.count))
        total_factories += f.count
    factory_summary.sort(key=lambda x: x[0])

    # Natural resources
    natural_resources = NaturalResource.query.filter_by(nation_id=nation.id).filter(NaturalResource.amount > 0).order_by(NaturalResource.amount.desc()).all()

    # Military counts
    total_units = Unit.query.filter_by(nation_id=nation.id).count()
    total_divisions = Division.query.filter_by(nation_id=nation.id).count()

    return dict(
        total_factories=total_factories,
        factory_summary=factory_summary,
        natural_resources=natural_resources,
        total_units=total_units,
        total_divisions=total_divisions,
    )


ADMIN_RESOURCES = {
    'money', 'food', 'power', 'building_materials', 'consumer_goods',
    'metal', 'fuel', 'ammunition', 'uranium', 'whz',
    'total_land', 'cleared_land', 'urban_areas', 'used_land',
    'forest', 'grassland', 'jungle', 'desert', 'mountain', 'tundra', 'river', 'lake',
    'population_gp', 'land_gp', 'factory_gp', 'building_gp', 'military_gp',
    'population', 'tier', 'growth_rate', 'loot_tokens',
}


@main.route('/')
def index():
    """Landing / index page — always accessible."""
    return render_template('main/landing.html', layout='base.html')


@main.route('/changelog')
def changelog_page():
    """Full version history — always accessible."""
    return render_template('main/changelog.html', layout='base.html')


@main.route('/home')
@login_required
def home():
    nation = current_user.nation
    summary = _nation_summary(nation) if nation else {}
    return render_template('main/home.html', nation=nation, is_owner=True,
                           **summary)


@main.route('/nation/<int:nation_id>')
@login_required
def nation_view(nation_id):
    nation = db.session.get(Nation, nation_id)
    if not nation:
        abort(404)
    summary = _nation_summary(nation)
    is_owner = current_user.nation and current_user.nation.id == nation_id
    return render_template('main/nation.html', nation=nation, is_owner=False,
                           **summary)


@main.route('/gp-breakdown')
@login_required
def gp_breakdown():
    return render_template('main/partials/gp_breakdown.html', nation=current_user.nation)


@main.route('/population-delta')
@login_required
def population_delta():
    nation = current_user.nation
    if not nation:
        return jsonify(delta=0)
    return jsonify(delta=estimate_pop_delta(nation))


@main.route('/resource-footer')
@login_required
def resource_footer():
    nation = current_user.nation
    resource_data = []
    if nation:
        pop_effects = get_population_effects(nation.population)
        unit_upkeep = compute_total_upkeep(nation.id)
        delta = estimate_pop_delta(nation)
        growth_food = max(0, delta) * FOOD_PER_CITIZEN

        resources_config = [
            ('money',              'Money',              'money_icon.png'),
            ('food',               'Food',               'food_icon.png'),
            ('power',              'Power',              'power_icon.png'),
            ('building_materials', 'Building Materials', 'building_materials_icon.png'),
            ('consumer_goods',     'Consumer Goods',     'consumer_goods_icon.png'),
            ('metal',              'Metal',              'metal_icon.png'),
            ('fuel',               'Fuel',               'fuel_icon.png'),
            ('ammunition',         'Ammunition',         'ammunition_icon.png'),
            ('uranium',            'Uranium',            'uranium_icon.png'),
            ('whz',                'WHZ',                'whz_icon.png'),
            ('loot_tokens',        'Loot Tokens',        'loot_token_icon.png'),
        ]

        for key, label, icon in resources_config:
            stockpile = getattr(nation, key, 0) or 0
            lines = []

            pop_rate = pop_effects.get(key, 0)
            if pop_rate > 0:
                lines.append(('Pop Tax', pop_rate))
            elif pop_rate < 0:
                lines.append(('Pop Usage', pop_rate))

            # Show growth food cost on the food row
            if key == 'food' and growth_food > 0:
                lines.append(('Pop Growth', -growth_food))

            upkeep = unit_upkeep.get(key, 0)
            if upkeep > 0:
                lines.append(('Unit Upkeep', -upkeep))

            net = sum(amt for _, amt in lines)

            resource_data.append({
                'key': key,
                'label': label,
                'icon': icon,
                'stockpile': stockpile,
                'lines': lines,
                'net': net,
            })

    return render_template('main/partials/resource_footer.html',
                           nation=nation, resource_data=resource_data)


@main.route('/update-flag', methods=['POST'])
@login_required
def update_flag():
    new_flag = request.form.get('new_flag', '').strip()
    IMAGE_EXTS = ('.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', '.svg',
                  '.tiff', '.tif', '.ico', '.avif', '.apng', '.jfif')
    # Strip query strings / fragments before checking extension
    path = new_flag.split('?')[0].split('#')[0].lower()
    if not new_flag or not any(path.endswith(ext) for ext in IMAGE_EXTS):
        resp = current_app.response_class(status=422)
        resp.headers['HX-Trigger'] = json.dumps(
            {'showMessage': {'message': 'Invalid flag URL. Must link to an image file.', 'type': 'error'}}
        )
        return resp
    current_user.nation.flag_url = new_flag
    db.session.commit()
    resp = current_app.response_class(status=204)
    resp.headers['HX-Trigger'] = json.dumps(
        {'showMessage': {'message': 'Flag updated successfully.', 'type': 'success'}}
    )
    return resp


@main.route('/update-description', methods=['POST'])
@login_required
def update_description():
    new_desc = request.form.get('new_description', '').strip()
    if len(new_desc) > 5000:
        return _error_response('Description too long (max 5000 characters).')
    current_user.nation.description = new_desc
    db.session.commit()
    resp = make_response(render_template(
        'main/partials/nation_description.html',
        nation=current_user.nation,
    ))
    resp.headers['HX-Trigger'] = json.dumps(
        {'showMessage': {'message': 'Description updated.', 'type': 'success'}}
    )
    return resp


@main.route('/update-growth-rate', methods=['POST'])
@login_required
def update_growth_rate():
    nation = current_user.nation
    if not nation:
        return _error_response('No nation found.')
    try:
        rate = int(request.form.get('growth_rate', 0))
    except (ValueError, TypeError):
        return _error_response('Invalid growth rate.')
    if rate < 0 or rate > 100:
        return _error_response('Growth rate must be between 0 and 100.')
    nation.growth_rate = rate
    db.session.commit()
    delta = estimate_pop_delta(nation)
    resp = current_app.make_response(json.dumps({'delta': delta}))
    resp.headers['Content-Type'] = 'application/json'
    resp.headers['HX-Trigger'] = json.dumps(
        {'showMessage': {'message': f'Growth rate set to {rate}%.', 'type': 'success'},
         'refreshResourceFooter': True}
    )
    return resp


VALID_CONTINENTS = {'Westberg', 'Amarino', 'San Sebastian', 'Tind', 'Zaheria'}

_GP_EXPR = (Nation.population_gp + Nation.land_gp + Nation.factory_gp
            + Nation.building_gp + Nation.military_gp)


@main.route('/leaderboard')
@login_required
def leaderboard():
    return render_template('main/leaderboard.html', nation=current_user.nation)


@main.route('/leaderboard/table')
@login_required
def leaderboard_table():
    continent = request.args.get('continent', 'all').strip()
    query = Nation.query.options(db.joinedload(Nation.alliance))
    continent_label = 'Global'
    if continent in VALID_CONTINENTS:
        query = query.filter(Nation.continent == continent)
        continent_label = continent
    nations = query.order_by(_GP_EXPR.desc()).limit(100).all()
    return render_template('main/partials/leaderboard_table.html',
                           nations=nations, current_nation=current_user.nation,
                           continent_label=continent_label)


@main.route('/leaderboard/search')
@login_required
def leaderboard_search():
    from ..helpers import nation_search_query
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return render_template('main/partials/leaderboard_search.html',
                               query='', results=[])
    results = (nation_search_query(q, search_leader=True)
               .options(db.joinedload(Nation.alliance))
               .order_by(_GP_EXPR.desc())
               .limit(50).all())
    return render_template('main/partials/leaderboard_search.html',
                           query=q, results=results)


# ── Admin helpers ──────────────────────────────────────────────────────

def require_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated


# ── Admin routes ───────────────────────────────────────────────────────

@main.route('/admin/search-nations')
@login_required
@require_admin
def admin_search_nations():
    from ..helpers import nation_search_query
    q = request.args.get('q', '').strip()
    if len(q) < 1:
        return jsonify([])
    nations = nation_search_query(q).limit(20).all()
    return jsonify([{'id': n.id, 'name': n.name} for n in nations])


def _admin_panel_context(nation):
    """Build template context for the admin panel partial."""
    queue = RecruitmentQueue.query.filter_by(nation_id=nation.id).order_by(RecruitmentQueue.completes_at).all()
    res_values = {r: getattr(nation, r, 0) or 0 for r in ADMIN_RESOURCES}
    return dict(target=nation, queue=queue, resources=sorted(ADMIN_RESOURCES), res_values=res_values)


@main.route('/admin/nation/<int:nation_id>')
@login_required
@require_admin
def admin_nation_panel(nation_id):
    nation = db.session.get(Nation, nation_id)
    if not nation:
        return _error_response('Nation not found.')
    return render_template('main/partials/admin_panel.html', **_admin_panel_context(nation))


@main.route('/admin/nation/<int:nation_id>/resource', methods=['POST'])
@login_required
@require_admin
def admin_edit_resource(nation_id):
    nation = db.session.get(Nation, nation_id)
    if not nation:
        return _error_response('Nation not found.')

    resource = request.form.get('resource', '').strip()
    mode = request.form.get('mode', '').strip()
    value_str = request.form.get('value', '').strip()

    if resource not in ADMIN_RESOURCES:
        return _error_response(f'Invalid resource: {resource}')
    if mode not in ('set', 'add', 'subtract'):
        return _error_response(f'Invalid mode: {mode}')
    try:
        value = float(value_str)
    except (ValueError, TypeError):
        return _error_response('Value must be a number.')

    current = getattr(nation, resource, 0) or 0
    if mode == 'set':
        setattr(nation, resource, value)
    elif mode == 'add':
        setattr(nation, resource, current + value)
    elif mode == 'subtract':
        setattr(nation, resource, current - value)

    db.session.commit()

    resp = current_app.make_response(
        render_template('main/partials/admin_panel.html', **_admin_panel_context(nation))
    )
    resp.headers['HX-Trigger'] = json.dumps(
        {'showMessage': {'message': f'{resource} updated ({mode} {value}).', 'type': 'success'}}
    )
    return resp


@main.route('/admin/nation/<int:nation_id>/complete-queue/<int:entry_id>', methods=['POST'])
@login_required
@require_admin
def admin_complete_queue(nation_id, entry_id):
    nation = db.session.get(Nation, nation_id)
    if not nation:
        return _error_response('Nation not found.')

    entry = db.session.get(RecruitmentQueue, entry_id)
    if not entry or entry.nation_id != nation.id:
        return _error_response('Queue entry not found.')

    udef = UNIT_DEFS.get(entry.unit_key)
    if not udef:
        db.session.delete(entry)
        db.session.commit()
        return _error_response('Unknown unit definition; entry removed.')

    unit = Unit.create_from_def(nation.id, entry.unit_key)
    db.session.add(unit)
    nation.military_gp = (nation.military_gp or 0) + udef.gp_value
    db.session.delete(entry)
    db.session.commit()

    resp = current_app.make_response(
        render_template('main/partials/admin_panel.html', **_admin_panel_context(nation))
    )
    resp.headers['HX-Trigger'] = json.dumps(
        {'showMessage': {'message': f'{udef.name} completed instantly.', 'type': 'success'}}
    )
    return resp


@main.route('/admin/nation/<int:nation_id>/tick', methods=['POST'])
@login_required
@require_admin
def admin_apply_tick(nation_id):
    """Apply one full hourly tick to a single nation."""
    nation = db.session.get(Nation, nation_id)
    if not nation:
        return _error_response('Nation not found.')

    from ..game.population import (get_population_effects, process_growth,
                                   process_starvation, compute_tier, compute_population_gp)
    from ..helpers import compute_total_upkeep
    from ..models import NationFactory, Unit

    # 1. Population effects (tax income + resource consumption)
    effects = get_population_effects(nation.population)
    for res, amount in effects.items():
        new_val = nation.get_resource(res) + amount
        setattr(nation, res, max(0, new_val))

    # 2. Population growth
    grown = process_growth(nation)

    # 3. Starvation
    starved = process_starvation(nation)

    # 4. Tier + population GP
    nation.tier = compute_tier(nation.population)
    nation.population_gp = compute_population_gp(nation.population)

    # 5. Factory production capacity (+1, cap 24)
    NationFactory.query.filter(
        NationFactory.nation_id == nation.id,
        NationFactory.count > 0,
        NationFactory.production_capacity < 24,
    ).update({'production_capacity': NationFactory.production_capacity + 1})

    # 6. Military upkeep
    units = Unit.query.filter_by(nation_id=nation.id).filter(Unit.hp > 0).all()
    if units:
        total_upkeep = compute_total_upkeep(nation.id)
        can_pay = all(nation.get_resource(r) >= a for r, a in total_upkeep.items())
        if can_pay:
            for res, amount in total_upkeep.items():
                nation.add_resource(res, -amount)
        else:
            for unit in units:
                attrition = max(1, unit.max_hp // 10)
                floor = unit.max_hp // 5
                if unit.hp > floor:
                    unit.hp = max(floor, unit.hp - attrition)

    db.session.commit()

    parts = ['Tick applied']
    if grown:
        parts.append(f'+{grown:,} pop')
    if starved:
        parts.append(f'-{starved:,} pop (starvation)')
    summary = '. '.join(parts) + '.'

    resp = current_app.make_response(
        render_template('main/partials/admin_panel.html', **_admin_panel_context(nation))
    )
    resp.headers['HX-Trigger'] = json.dumps(
        {'showMessage': {'message': summary, 'type': 'success'},
         'refreshResourceFooter': True}
    )
    return resp
