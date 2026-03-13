import json
from functools import wraps
from datetime import datetime, timezone, timedelta
from flask import render_template, url_for, request, current_app, abort, jsonify, make_response
from flask_login import login_required, current_user
from .. import db, cache
from ..models import Nation, NationFactory, NaturalResource, Alliance, Division, Unit, RecruitmentQueue, FactoryBuildQueue, BuildingUpgradeQueue, NationBuilding
from ..helpers import error_response as _error_response, compute_total_upkeep
from ..game.population import (get_population_effects, estimate_pop_delta, FOOD_PER_CITIZEN,
                                food_abundance_multiplier, get_food_days,
                                FOOD_STOCKPILE_MIN_DAYS, FOOD_STOCKPILE_MAX_DAYS)
from ..game.factories import FACTORY_DEFS
from ..game.units import UNIT_DEFS
from . import main


def _nation_summary(nation):
    """Build summary data dict for nation profile display."""
    # Optimization: Use a single query for counts and use eager loading if possible
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

    # Buildings
    from ..game.buildings import BUILDING_DEFS
    nation_buildings = NationBuilding.query.filter_by(nation_id=nation.id).all()
    building_summary = sorted(
        [(BUILDING_DEFS[nb.building_key].name, nb.level) for nb in nation_buildings if nb.building_key in BUILDING_DEFS],
        key=lambda x: x[0]
    )

    # Natural resources
    natural_resources = NaturalResource.query.filter_by(nation_id=nation.id).filter(NaturalResource.amount > 0).order_by(NaturalResource.amount.desc()).all()

    # Military counts with type breakdown for preamble
    units_list = Unit.query.filter_by(nation_id=nation.id).with_entities(Unit.unit_key).all()
    total_units = len(units_list)
    unit_type_counts = {}
    for (unit_key,) in units_list:
        udef = UNIT_DEFS.get(unit_key)
        if udef and not udef.npc_only:
            unit_type_counts[udef.unit_type] = unit_type_counts.get(udef.unit_type, 0) + 1
    top_unit_type = max(unit_type_counts, key=unit_type_counts.get) if unit_type_counts else None
    total_divisions = Division.query.filter_by(nation_id=nation.id).count()

    return dict(
        total_factories=total_factories,
        factory_summary=factory_summary,
        building_summary=building_summary,
        natural_resources=natural_resources,
        total_units=total_units,
        unit_type_counts=unit_type_counts,
        top_unit_type=top_unit_type,
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


@main.route('/robots.txt')
@cache.cached(timeout=86400)
def robots_txt():
    """Serve robots.txt for search engine crawlers."""
    lines = [
        'User-agent: *',
        'Allow: /',
        'Disallow: /home',
        'Disallow: /admin/',
        'Disallow: /gp-breakdown',
        'Disallow: /resource-footer',
        'Disallow: /population-delta',
        'Disallow: /leaderboard/',
        f'Sitemap: {url_for("main.sitemap_xml", _external=True)}',
    ]
    resp = current_app.response_class('\n'.join(lines) + '\n', mimetype='text/plain')
    return resp


@main.route('/sitemap.xml')
@cache.cached(timeout=3600)
def sitemap_xml():
    """Serve sitemap.xml for search engine discovery."""
    pages = [
        (url_for('main.index', _external=True), '1.0', 'weekly'),
        (url_for('main.changelog_page', _external=True), '0.5', 'weekly'),
        (url_for('auth.login', _external=True), '0.3', 'monthly'),
        (url_for('auth.register', _external=True), '0.6', 'monthly'),
    ]
    xml_parts = ['<?xml version="1.0" encoding="UTF-8"?>']
    xml_parts.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
    for loc, priority, changefreq in pages:
        xml_parts.append('  <url>')
        xml_parts.append(f'    <loc>{loc}</loc>')
        xml_parts.append(f'    <priority>{priority}</priority>')
        xml_parts.append(f'    <changefreq>{changefreq}</changefreq>')
        xml_parts.append('  </url>')
    xml_parts.append('</urlset>')
    resp = current_app.response_class('\n'.join(xml_parts), mimetype='application/xml')
    return resp


@main.route('/')
@cache.cached(timeout=3600, unless=lambda: current_user.is_authenticated)
def index():
    """Landing / index page — always accessible."""
    return render_template('main/landing.html', layout='base.html')


@main.route('/changelog')
@cache.cached(timeout=3600, unless=lambda: current_user.is_authenticated)
def changelog_page():
    """Full version history — always accessible."""
    return render_template('main/changelog.html', layout='base.html')


@main.route('/home')
@login_required
def home():
    nation = current_user.nation
    summary = _nation_summary(nation) if nation else {}

    # Vacation cooldown: hours + minutes remaining (None if not on cooldown)
    vac_cooldown_remaining = None
    if not current_user.vacation_mode and current_user.vacation_disabled_at:
        cooldown_end = current_user.vacation_disabled_at + timedelta(hours=48)
        remaining = (cooldown_end - datetime.now(timezone.utc)).total_seconds()
        if remaining > 0:
            vac_cooldown_remaining = (int(remaining // 3600), int((remaining % 3600) // 60))

    return render_template('main/home.html', nation=nation, is_owner=True,
                           vac_cooldown_remaining=vac_cooldown_remaining,
                           **summary)


@main.route('/nation/<int:nation_id>')
@login_required
def nation_view(nation_id):
    nation = db.session.get(Nation, nation_id)
    if not nation:
        abort(404)
    summary = _nation_summary(nation)
    is_owner = current_user.nation and current_user.nation.id == nation_id
    return render_template('main/nation.html', nation=nation, is_owner=is_owner,
                           **summary)


@main.route('/gp-breakdown')
@login_required
def gp_breakdown():
    nation_id = request.args.get('nation_id', type=int)
    if nation_id:
        nation = db.session.get(Nation, nation_id)
        if not nation:
            abort(404)
    else:
        nation = current_user.nation
    return render_template('main/partials/gp_breakdown.html', nation=nation)


def _pop_delta_payload(nation):
    """Build population delta JSON payload for a nation."""
    delta = estimate_pop_delta(nation)
    food_days = round(get_food_days(nation.population, nation.food), 1)
    abundance = round(food_abundance_multiplier(nation.population, nation.food) * 100)
    # Determine growth blockers
    cleared = nation.cleared_land or 0
    urban = nation.urban_areas or 0
    pop = nation.population or 0
    from ..game.population import LAND_PER_POPULATION
    max_capacity = (urban + cleared) * LAND_PER_POPULATION
    if cleared <= 0 and urban <= 0:
        growth_block = 'no_land'
    elif pop >= max_capacity:
        growth_block = 'land_full'
    else:
        growth_block = ''
    return dict(delta=delta, food_days=food_days, abundance=abundance, growth_block=growth_block)


@main.route('/population-delta')
@login_required
def population_delta():
    nation = current_user.nation
    if not nation:
        return jsonify(delta=0, food_days=0, abundance=0, growth_block='')
    return jsonify(**_pop_delta_payload(nation))


@cache.memoize(timeout=60)
def _get_cached_upkeep(nation_id):
    return compute_total_upkeep(nation_id)


@main.route('/resource-footer')
@login_required
def resource_footer():
    nation = current_user.nation
    resource_data = []
    if nation:
        pop_effects = get_population_effects(nation.population)
        unit_upkeep = _get_cached_upkeep(nation.id)
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


@main.route('/update-banner', methods=['POST'])
@login_required
def update_banner():
    new_banner = request.form.get('new_banner', '').strip()
    if new_banner:
        IMAGE_EXTS = ('.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', '.svg',
                      '.tiff', '.tif', '.ico', '.avif', '.apng', '.jfif')
        path = new_banner.split('?')[0].split('#')[0].lower()
        if not any(path.endswith(ext) for ext in IMAGE_EXTS):
            resp = current_app.response_class(status=422)
            resp.headers['HX-Trigger'] = json.dumps(
                {'showMessage': {'message': 'Invalid banner URL. Must link to an image file.', 'type': 'error'}}
            )
            return resp
    current_user.nation.banner_url = new_banner
    db.session.commit()
    resp = current_app.response_class(status=204)
    resp.headers['HX-Trigger'] = json.dumps(
        {'showMessage': {'message': 'Banner updated successfully.', 'type': 'success'}}
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
    mode = request.form.get('growth_mode', '').strip()
    if mode not in ('off', 'auto', 'manual'):
        mode = 'manual' if rate > 0 else 'off'
    nation.growth_rate = rate
    nation.growth_mode = mode
    db.session.commit()
    resp = current_app.make_response(json.dumps(_pop_delta_payload(nation)))
    resp.headers['Content-Type'] = 'application/json'
    resp.headers['HX-Trigger'] = json.dumps(
        {'showMessage': {'message': f'Growth rate set to {rate}%.', 'type': 'success'},
         'refreshResourceFooter': True}
    )
    return resp


VALID_CONTINENTS = {'Westberg', 'Amarino', 'San Sebastian', 'Tind', 'Zaheria'}


@main.route('/leaderboard')
@login_required
def leaderboard():
    tab = request.args.get('tab', 'national').strip()
    return render_template('main/leaderboard.html', nation=current_user.nation, default_tab=tab)


@main.route('/leaderboard/table')
@login_required
def leaderboard_table():
    continent = request.args.get('continent', 'all').strip()
    lb_type = request.args.get('type', 'nation').strip()
    query = Nation.query.options(db.joinedload(Nation.alliance))
    continent_label = 'Global'
    if continent in VALID_CONTINENTS:
        query = query.filter(Nation.continent == continent)
        continent_label = continent
    if lb_type == 'military':
        nations = query.order_by(Nation.military_gp.desc()).limit(100).all()
    else:
        nations = query.order_by(Nation.total_gp.desc()).limit(100).all()
    return render_template('main/partials/leaderboard_table.html',
                           nations=nations, current_nation=current_user.nation,
                           continent_label=continent_label, lb_type=lb_type)


@main.route('/leaderboard/alliance-table')
@login_required
def leaderboard_alliance_table():
    from sqlalchemy import func
    from sqlalchemy.orm import joinedload
    results = (db.session.query(
        Alliance,
        func.count(Nation.id).label('member_count'),
        func.sum(Nation.total_gp).label('total_gp'),
        func.sum(Nation.population_gp).label('pop_gp'),
        func.sum(Nation.land_gp).label('land_gp'),
        func.sum(Nation.factory_gp).label('factory_gp'),
        func.sum(Nation.military_gp).label('military_gp'),
    ).join(Nation, Nation.alliance_id == Alliance.id)
     .group_by(Alliance.id)
     .order_by(func.sum(Nation.total_gp).desc())
     .limit(50).all())
    # Eagerly load founder for display
    alliance_ids = [r[0].id for r in results]
    if alliance_ids:
        Alliance.query.options(joinedload(Alliance.founder)).filter(Alliance.id.in_(alliance_ids)).all()
    return render_template('main/partials/leaderboard_alliance_table.html',
                           results=results, current_nation=current_user.nation)


@main.route('/leaderboard/alliance-search')
@login_required
def leaderboard_alliance_search():
    from sqlalchemy import func
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return render_template('main/partials/leaderboard_alliance_search.html', query='', results=[])
    results = (db.session.query(
        Alliance,
        func.count(Nation.id).label('member_count'),
        func.sum(Nation.total_gp).label('total_gp'),
    ).join(Nation, Nation.alliance_id == Alliance.id)
     .filter(Alliance.name.ilike(f'%{q}%'))
     .group_by(Alliance.id)
     .order_by(func.sum(Nation.total_gp).desc())
     .limit(20).all())
    return render_template('main/partials/leaderboard_alliance_search.html', query=q, results=results)


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
               .order_by(Nation.total_gp.desc())
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


_ADMIN_RESOURCE_GROUPS = [
    ('Commodities', [
        'money', 'food', 'power', 'building_materials', 'consumer_goods',
        'metal', 'ammunition', 'fuel', 'uranium', 'whz', 'loot_tokens'
    ]),
    ('Land', [
        'total_land', 'cleared_land', 'urban_areas', 'used_land',
        'forest', 'grassland', 'jungle', 'desert', 'mountain',
        'tundra', 'river', 'lake',
    ]),
    ('Other', [
        'population', 'growth_rate', 'tier',
        'population_gp', 'land_gp', 'factory_gp', 'building_gp', 'military_gp',
    ]),
]


def _admin_panel_context(nation):
    """Build template context for the admin panel partial."""
    queue = RecruitmentQueue.query.filter_by(nation_id=nation.id).order_by(RecruitmentQueue.completes_at).all()
    factory_queue = FactoryBuildQueue.query.filter_by(nation_id=nation.id).order_by(FactoryBuildQueue.completes_at).all()
    building_queue = BuildingUpgradeQueue.query.filter_by(nation_id=nation.id).order_by(BuildingUpgradeQueue.completes_at).all()
    res_values = {r: getattr(nation, r, 0) or 0 for r in ADMIN_RESOURCES}
    return dict(target=nation, queue=queue, factory_queue=factory_queue, building_queue=building_queue,
                resource_groups=_ADMIN_RESOURCE_GROUPS, res_values=res_values)


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

    # Auto-recalculate GP components if their source was edited
    if resource == 'total_land':
        nation.land_gp = (nation.total_land or 0) // 10
    elif resource == 'population':
        from ..game.population import compute_population_gp
        nation.population_gp = compute_population_gp(nation.population)

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

    entry = db.session.get(RecruitmentQueue, (entry_id, nation.id))
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


@main.route('/admin/nation/<int:nation_id>/complete-factory/<int:entry_id>', methods=['POST'])
@login_required
@require_admin
def admin_complete_factory_queue(nation_id, entry_id):
    from ..helpers import grant_factories
    nation = db.session.get(Nation, nation_id)
    if not nation:
        return _error_response('Nation not found.')

    entry = FactoryBuildQueue.query.filter_by(id=entry_id, nation_id=nation_id).first()
    if not entry:
        return _error_response('Queue entry not found.')

    fdef = FACTORY_DEFS.get(entry.factory_key)
    grant_factories(nation, [(entry.factory_key, entry.quantity)])
    db.session.delete(entry)
    db.session.commit()

    label = fdef.name if fdef else entry.factory_key
    resp = current_app.make_response(
        render_template('main/partials/admin_panel.html', **_admin_panel_context(nation))
    )
    resp.headers['HX-Trigger'] = json.dumps(
        {'showMessage': {'message': f'{label} build completed instantly.', 'type': 'success'}}
    )
    return resp


@main.route('/admin/nation/<int:nation_id>/complete-building/<int:entry_id>', methods=['POST'])
@login_required
@require_admin
def admin_complete_building_queue(nation_id, entry_id):
    from ..game.buildings import BUILDING_DEFS
    nation = db.session.get(Nation, nation_id)
    if not nation:
        return _error_response('Nation not found.')

    entry = BuildingUpgradeQueue.query.filter_by(id=entry_id, nation_id=nation_id).first()
    if not entry:
        return _error_response('Queue entry not found.')

    nb = NationBuilding.query.filter_by(nation_id=nation_id, building_key=entry.building_key).first()
    if nb:
        nb.level = entry.target_level
        bdef = BUILDING_DEFS.get(entry.building_key)
        if bdef and entry.target_level <= len(bdef.gp_per_level):
            nation.building_gp = (nation.building_gp or 0) + bdef.gp_per_level[entry.target_level - 1]
        label = bdef.name if bdef else entry.building_key
    else:
        label = entry.building_key

    db.session.delete(entry)
    db.session.commit()

    resp = current_app.make_response(
        render_template('main/partials/admin_panel.html', **_admin_panel_context(nation))
    )
    resp.headers['HX-Trigger'] = json.dumps(
        {'showMessage': {'message': f'{label} upgrade completed instantly.', 'type': 'success'}}
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

    from ..models import NationFactory
    from ..tasks import tick_nation

    # 1. Population + military tick
    grown, starved = tick_nation(nation)

    # 2. Factory production capacity (+1, cap 24)
    NationFactory.query.filter(
        NationFactory.nation_id == nation.id,
        NationFactory.count > 0,
        NationFactory.production_capacity < 24,
    ).update({'production_capacity': NationFactory.production_capacity + 1})

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
