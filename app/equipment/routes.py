import json
from flask import redirect, render_template, request, url_for as flask_url_for, current_app
from flask_login import login_required, current_user
from .. import db
from ..models import Equipment, Unit
from ..helpers import error_response as _error_response, success_response as _success_response, build_equipped_counts as _build_equipped_counts
from ..game.equipment import (
    EQUIPMENT_SLOTS, UNIT_CATEGORIES, RARITY_ORDER, RARITY_COLORS,
    CRATE_SIZES, TRADE_IN_VALUES, BUFF_FILTER_OPTIONS,
    generate_crate_contents, get_slot_category,
    compute_buff_hash, serialize_buffs, apply_buff_filter,
)
from ..game.units import UNIT_DEFS
from . import equipment


# ── EQUIPMENT INVENTORY ──────────────────────────────────────────────────


@equipment.route('/equipment')
@login_required
def inventory():
    nation = current_user.nation
    items = Equipment.query.filter_by(nation_id=nation.id).order_by(Equipment.created_at.desc()).all()

    equipped_counts = _build_equipped_counts(nation.id)
    default_tab = request.args.get('tab', 'inventory')

    return render_template(
        'equipment/equipment.html',
        nation=nation,
        items=items,
        equipped_counts=equipped_counts,
        rarity_order=RARITY_ORDER,
        rarity_colors=RARITY_COLORS,
        equipment_slots=EQUIPMENT_SLOTS,
        trade_in_values=TRADE_IN_VALUES,
        unit_categories=UNIT_CATEGORIES,
        crate_sizes=CRATE_SIZES,
        default_tab=default_tab,
        buff_filter_options=BUFF_FILTER_OPTIONS,
    )


@equipment.route('/equipment/grid')
@login_required
def equipment_grid():
    nation = current_user.nation
    items = Equipment.query.filter_by(nation_id=nation.id).order_by(Equipment.created_at.desc()).all()

    # Filters
    type_filter     = request.args.get('type', '')
    rarity_filter   = request.args.get('rarity', '')
    foil_filter     = request.args.get('foil', '')
    equipped_filter = request.args.get('equipped', '')
    buff_type       = request.args.get('buff_type', '')
    buff_min        = request.args.get('buff_min', '')

    equipped_counts = _build_equipped_counts(nation.id)

    if type_filter:
        items = [i for i in items if i.equipment_type == type_filter]
    if rarity_filter:
        items = [i for i in items if i.rarity == rarity_filter]
    if foil_filter == 'yes':
        items = [i for i in items if i.is_foil]
    elif foil_filter == 'no':
        items = [i for i in items if not i.is_foil]
    if equipped_filter == 'yes':
        items = [i for i in items if equipped_counts.get(i.id, 0) > 0]
    elif equipped_filter == 'no':
        items = [i for i in items if equipped_counts.get(i.id, 0) == 0]
    if buff_type:
        items = apply_buff_filter(items, buff_type, buff_min)

    return render_template(
        'equipment/partials/equipment_grid.html',
        items=items,
        equipped_counts=equipped_counts,
        rarity_colors=RARITY_COLORS,
        trade_in_values=TRADE_IN_VALUES,
    )


# ── LOOT CRATE SHOP ─────────────────────────────────────────────────────

@equipment.route('/equipment/loot-crates')
@login_required
def loot_crates():
    return redirect(flask_url_for('equipment.inventory', tab='crates'))


@equipment.route('/equipment/buy-crate', methods=['POST'])
@login_required
def buy_crate():
    nation = current_user.nation
    size = request.form.get('size', '').strip()
    category = request.form.get('category', '').strip()

    if size not in CRATE_SIZES:
        return _error_response('Invalid crate size.')
    if category not in UNIT_CATEGORIES:
        return _error_response('Invalid unit category.')

    cost = CRATE_SIZES[size]['cost']
    tokens = nation.loot_tokens or 0
    if tokens < cost:
        return _error_response(f'Not enough loot tokens. Need {cost}, have {int(tokens)}.')

    nation.loot_tokens = tokens - cost

    # Generate items
    generated = generate_crate_contents(size, category)

    # Group generated items by dedup key to handle in-batch duplicates
    batch = {}  # (type, rarity, foil, hash) -> (count, buff_json)
    for item_data in generated:
        buff_hash = compute_buff_hash(item_data['buffs'])
        buff_json_str = serialize_buffs(item_data['buffs'])
        key = (item_data['equipment_type'], item_data['rarity'],
               item_data['is_foil'], buff_hash)
        if key in batch:
            batch[key] = (batch[key][0] + 1, batch[key][1])
        else:
            batch[key] = (1, buff_json_str)

    # Merge with existing DB rows
    for (eq_type, rarity, is_foil, buff_hash), (add_count, buff_json_str) in batch.items():
        existing = Equipment.query.filter_by(
            nation_id=nation.id,
            equipment_type=eq_type,
            rarity=rarity,
            is_foil=is_foil,
            buff_hash=buff_hash,
        ).first()

        if existing:
            existing.count += add_count
        else:
            eq = Equipment(
                nation_id=nation.id,
                equipment_type=eq_type,
                rarity=rarity,
                is_foil=is_foil,
                buff_hash=buff_hash,
                buff_json=buff_json_str,
                count=add_count,
            )
            db.session.add(eq)

    db.session.commit()

    # Pass raw generated dicts to the template for display
    html = render_template(
        'equipment/partials/crate_results.html',
        items=generated,
        rarity_colors=RARITY_COLORS,
        crate_size=size,
        category=category,
    )
    resp = current_app.make_response(html)
    resp.headers['HX-Trigger'] = json.dumps({
        'refreshResourceFooter': True,
        'updateTokenBalance': {'tokens': int(nation.loot_tokens or 0)},
    })
    return resp


# ── TRADE-IN ─────────────────────────────────────────────────────────────

@equipment.route('/equipment/trade-in', methods=['POST'])
@login_required
def trade_in():
    nation = current_user.nation
    ids_str = request.form.get('ids', '')
    try:
        eq_ids = [int(x) for x in ids_str.split(',') if x.strip()]
    except ValueError:
        return _error_response('Invalid equipment selection.')

    if not eq_ids:
        return _error_response('No equipment selected.')

    equipped_counts = _build_equipped_counts(nation.id)

    items = Equipment.query.filter(
        Equipment.id.in_(eq_ids),
        Equipment.nation_id == nation.id,
    ).all()

    total_tokens = 0
    total_traded = 0
    for item in items:
        equipped = equipped_counts.get(item.id, 0)
        available = item.count - equipped
        if available <= 0:
            continue
        total_tokens += TRADE_IN_VALUES.get(item.rarity, 0) * available
        total_traded += available
        if equipped == 0:
            db.session.delete(item)
        else:
            item.count = equipped

    if total_traded == 0:
        return _error_response('No tradeable items selected (equipped items cannot be traded).')

    nation.loot_tokens = (nation.loot_tokens or 0) + total_tokens
    db.session.commit()

    return _success_response(f'Traded {total_traded} item(s) for {total_tokens} loot token(s).')


# ── EQUIP / UNEQUIP ─────────────────────────────────────────────────────

@equipment.route('/equipment/equip', methods=['POST'])
@login_required
def equip_item():
    nation = current_user.nation
    eq_id = request.form.get('equipment_id', type=int)
    unit_id = request.form.get('unit_id', type=int)

    if not eq_id or not unit_id:
        return _error_response('Missing equipment or unit ID.')

    eq = db.session.get(Equipment, (eq_id, nation.id))
    unit = db.session.get(Unit, (unit_id, nation.id))

    if not eq or eq.nation_id != nation.id:
        return _error_response('Equipment not found.')
    if not unit or unit.nation_id != nation.id:
        return _error_response('Unit not found.')

    # Check available count (count - already equipped)
    equipped_counts = _build_equipped_counts(nation.id)
    equipped = equipped_counts.get(eq.id, 0)
    if eq.count - equipped <= 0:
        return _error_response('No available copies of this equipment (all are equipped).')

    # Check compatibility: equipment type must match unit category
    udef = UNIT_DEFS.get(unit.unit_key)
    if not udef:
        return _error_response('Unknown unit type.')

    compatible_slots = EQUIPMENT_SLOTS.get(udef.unit_type, [])
    if eq.equipment_type not in compatible_slots:
        return _error_response(f'{eq.equipment_type} is not compatible with {udef.unit_type} units.')

    # Level requirement for rarity tiers
    from ..game.levels import can_equip_rarity, RARITY_LEVEL_REQ
    if not can_equip_rarity(unit.level, eq.rarity):
        req = RARITY_LEVEL_REQ.get(eq.rarity, 1)
        return _error_response(f'{eq.rarity} equipment requires unit Lv.{req}+')

    # Determine which slot this goes into
    slot_cat = get_slot_category(eq.equipment_type, udef.unit_type)

    # Assign equipment to slot
    if slot_cat == 'weapon':
        unit.weapon_id = eq.id
    elif slot_cat == 'accessory':
        unit.accessory_id = eq.id
    elif slot_cat == 'armour':
        unit.armour_eq_id = eq.id

    # Heal to new effective max HP (equipment may boost HP)
    db.session.flush()  # ensure relationships are updated before computing effective stats
    unit.hp = unit.effective_max_hp

    db.session.commit()

    if request.form.get('from_unit_detail') == '1':
        from ..military.routes import render_unit_detail
        html = render_unit_detail(unit, nation)
        resp = current_app.make_response(html)
        resp.headers['HX-Trigger'] = json.dumps({'refreshDivisionContent': True})
        return resp

    return _success_response(f'Equipped {eq.equipment_type} to {udef.name}.')


@equipment.route('/equipment/unequip/<int:unit_id>/<slot>', methods=['POST'])
@login_required
def unequip_item(unit_id, slot):
    nation = current_user.nation
    unit = db.session.get(Unit, (unit_id, nation.id))

    if not unit or unit.nation_id != nation.id:
        return _error_response('Unit not found.')

    if slot == 'weapon':
        unit.weapon_id = None
    elif slot == 'accessory':
        unit.accessory_id = None
    elif slot == 'armour':
        unit.armour_eq_id = None
    else:
        return _error_response('Invalid slot.')

    # Clamp HP to new effective max (removing HP-boosting equipment lowers cap)
    db.session.flush()
    if unit.hp > unit.effective_max_hp:
        unit.hp = unit.effective_max_hp

    db.session.commit()

    if request.form.get('from_unit_detail') == '1':
        from ..military.routes import render_unit_detail
        html = render_unit_detail(unit, nation)
        resp = current_app.make_response(html)
        resp.headers['HX-Trigger'] = json.dumps({'refreshDivisionContent': True})
        return resp

    return _success_response('Equipment removed.')
