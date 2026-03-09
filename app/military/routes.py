import json
import random
from types import SimpleNamespace
from datetime import datetime, timezone, timedelta
from flask import redirect, render_template, request, url_for, current_app
from flask_login import login_required, current_user
from .. import db
from sqlalchemy import or_, and_
from ..models import Division, Unit, RecruitmentQueue, Battle, CombatReport, Nation, User, Equipment
from ..helpers import error_response as _error_response, can_afford as _can_afford, deduct_cost as _deduct_cost, compute_total_upkeep
from ..game.units import UNIT_DEFS
from ..game.equipment import EQUIPMENT_SLOTS, RARITY_COLORS, get_slot_category, BUFF_FILTER_OPTIONS, apply_buff_filter
from . import military


# ── OVERVIEW ──────────────────────────────────────────────────────────────

@military.route('/military')
@login_required
def overview():
    nation = current_user.nation
    divisions = Division.query.filter_by(nation_id=nation.id).order_by(Division.id).all()
    reserve_units = Unit.query.filter_by(nation_id=nation.id, division_id=None).order_by(Unit.id).all()
    queue = RecruitmentQueue.query.filter_by(nation_id=nation.id).order_by(
        RecruitmentQueue.completes_at
    ).all()

    total_upkeep = compute_total_upkeep(nation.id)

    return render_template(
        'military/overview.html',
        nation=nation,
        divisions=divisions,
        reserve_units=reserve_units,
        unit_defs=UNIT_DEFS,
        queue=queue,
        total_upkeep=total_upkeep,
        default_tab=request.args.get('tab', 'overview'),
        div_battles=_get_div_battles(nation.id),
    )


# ── DIVISION MANAGEMENT ──────────────────────────────────────────────────

@military.route('/military/division/create', methods=['POST'])
@login_required
def create_division():
    nation = current_user.nation
    count = Division.query.filter_by(nation_id=nation.id).count()
    if count >= 20:
        return _error_response('Maximum 20 divisions allowed.')
    name = request.form.get('name', '').strip() or f'Division {count + 1}'
    if len(name) > 120:
        name = name[:120]
    div = Division(nation_id=nation.id, name=name)
    db.session.add(div)
    db.session.commit()

    return _division_list_response(nation, f'Created division "{div.name}".')


@military.route('/military/division/<int:div_id>/rename', methods=['POST'])
@login_required
def rename_division(div_id):
    nation = current_user.nation
    div = Division.query.filter_by(id=div_id, nation_id=nation.id).first()
    if not div:
        return _error_response('Division not found.')
    name = request.form.get('name', '').strip()
    if not name:
        return _error_response('Name cannot be empty.')
    if len(name) > 120:
        name = name[:120]
    div.name = name
    db.session.commit()
    return _division_list_response(nation, f'Division renamed to "{name}".')


@military.route('/military/division/<int:div_id>/disband', methods=['POST'])
@login_required
def disband_division(div_id):
    nation = current_user.nation
    div = Division.query.filter_by(id=div_id, nation_id=nation.id).first()
    if not div:
        return _error_response('Division not found.')
    if div.in_combat:
        return _error_response('Cannot disband a division that is in combat.')
    # Move units to reserve
    Unit.query.filter_by(division_id=div.id).update({'division_id': None})
    db.session.delete(div)
    db.session.commit()
    return _division_list_response(nation, f'Division "{div.name}" disbanded.')


@military.route('/military/division/<int:div_id>/mobilize', methods=['POST'])
@login_required
def mobilize_division(div_id):
    nation = current_user.nation
    div = Division.query.filter_by(id=div_id, nation_id=nation.id).first()
    if not div:
        return _error_response('Division not found.')
    if div.mobilization_state == 'mobilized':
        return _error_response('Division is already mobilized.')
    div.mobilization_state = 'mobilized'
    db.session.commit()
    return _division_list_response(nation, f'"{div.name}" mobilized.')


@military.route('/military/division/<int:div_id>/demobilize', methods=['POST'])
@login_required
def demobilize_division(div_id):
    nation = current_user.nation
    div = Division.query.filter_by(id=div_id, nation_id=nation.id).first()
    if not div:
        return _error_response('Division not found.')
    if div.in_combat:
        return _error_response('Cannot demobilize a division in combat.')
    div.mobilization_state = 'demobilized'
    db.session.commit()
    return _division_list_response(nation, f'"{div.name}" demobilized.')


def _get_div_battles(nation_id):
    """Return dict mapping division_id -> battle_id for active battles."""
    active = Battle.query.filter_by(status='active').filter(
        or_(Battle.attacker_nation_id == nation_id, Battle.defender_nation_id == nation_id)
    ).all()
    div_battles = {}
    for b in active:
        if b.attacker_nation_id == nation_id:
            div_battles[b.attacker_division_id] = b.id
        if b.defender_nation_id == nation_id:
            div_battles[b.defender_division_id] = b.id
    return div_battles


def _division_list_response(nation, message):
    divisions = Division.query.filter_by(nation_id=nation.id).order_by(Division.id).all()
    reserve_units = Unit.query.filter_by(nation_id=nation.id, division_id=None).order_by(Unit.id).all()
    resp_html = render_template(
        'military/partials/division_content.html',
        nation=nation,
        divisions=divisions,
        reserve_units=reserve_units,
        unit_defs=UNIT_DEFS,
        div_battles=_get_div_battles(nation.id),
    )
    resp = current_app.response_class(resp_html, status=200, mimetype='text/html')
    resp.headers['HX-Trigger'] = json.dumps(
        {'showMessage': {'message': message, 'type': 'success'},
         'refreshResourceFooter': True}
    )
    return resp


@military.route('/military/divisions')
@login_required
def division_list():
    """Return the division content partial (used by refreshDivisionContent trigger)."""
    nation = current_user.nation
    divisions = Division.query.filter_by(nation_id=nation.id).order_by(Division.id).all()
    reserve_units = Unit.query.filter_by(nation_id=nation.id, division_id=None).order_by(Unit.id).all()
    return render_template(
        'military/partials/division_content.html',
        nation=nation,
        divisions=divisions,
        reserve_units=reserve_units,
        unit_defs=UNIT_DEFS,
        div_battles=_get_div_battles(nation.id),
    )


# ── UNIT MANAGEMENT ───────────────────────────────────────────────────────

@military.route('/military/unit/<int:unit_id>/move', methods=['POST'])
@login_required
def move_unit(unit_id):
    nation = current_user.nation
    unit = Unit.query.filter_by(id=unit_id, nation_id=nation.id).first()
    if not unit:
        return _error_response('Unit not found.')
    # Block moves out of mobilized/in-combat divisions
    if unit.division_id:
        source = db.session.get(Division, (unit.division_id, nation.id))
        if source and source.mobilization_state == 'mobilized':
            return _error_response('Cannot move units out of a mobilized division.')
    target_div_id = request.form.get('division_id', '').strip()
    if target_div_id == '' or target_div_id == 'none':
        unit.division_id = None
        unit.division_joined_at = None
    else:
        div = Division.query.filter_by(id=int(target_div_id), nation_id=nation.id).first()
        if not div:
            return _error_response('Target division not found.')
        if div.mobilization_state == 'mobilized':
            return _error_response('Cannot move units into a mobilized division.')
        unit.division_id = div.id
        unit.division_joined_at = datetime.now(timezone.utc)
    db.session.commit()
    return _division_list_response(nation, 'Unit moved.')


@military.route('/military/unit/<int:unit_id>/disband', methods=['POST'])
@login_required
def disband_unit(unit_id):
    nation = current_user.nation
    unit = Unit.query.filter_by(id=unit_id, nation_id=nation.id).first()
    if not unit:
        return _error_response('Unit not found.')
    if unit.division_id:
        div = db.session.get(Division, (unit.division_id, nation.id))
        if div and div.mobilization_state == 'mobilized':
            return _error_response('Cannot disband units in a mobilized division.')
    udef = UNIT_DEFS.get(unit.unit_key)
    name = udef.name if udef else unit.unit_key
    # Reduce military GP
    if udef:
        nation.military_gp = max(0, (nation.military_gp or 0) - udef.gp_value)
    db.session.delete(unit)
    db.session.commit()
    return _division_list_response(nation, f'{name} disbanded.')


@military.route('/military/unit/<int:unit_id>/rename', methods=['POST'])
@login_required
def rename_unit(unit_id):
    nation = current_user.nation
    unit = Unit.query.filter_by(id=unit_id, nation_id=nation.id).first()
    if not unit:
        return _error_response('Unit not found.')
    name = request.form.get('name', '').strip()
    if len(name) > 120:
        name = name[:120]
    unit.custom_name = name
    db.session.commit()
    return _division_list_response(nation, 'Unit renamed.')


# ── UNIT DETAIL POPUP ────────────────────────────────────────────────

def _compute_equipment_bonuses(unit):
    """Compute display bonuses and special abilities from equipped items."""
    bonuses = {
        'firepower': unit.effective_firepower - unit.firepower,
        'armour': unit.effective_armour - unit.armour,
        'maneuver': unit.effective_maneuver - unit.maneuver,
    }
    hp_mult = unit._eq_hp_multiplier()
    eq_abilities = []
    for eq in unit.equipment_items:
        for buff in eq.buffs:
            if buff.buff_type.startswith('FPvs_') or buff.buff_type.startswith('AllStats_'):
                eq_abilities.append(buff.description)
    return bonuses, hp_mult, eq_abilities


def render_unit_detail(unit, nation):
    """Render the unit detail popup partial. Shared by military and equipment routes."""
    udef = UNIT_DEFS.get(unit.unit_key)

    # Determine if equippable: reserve or in a demobilized division
    equippable = True
    if unit.division_id:
        div = db.session.get(Division, (unit.division_id, nation.id))
        if div and div.mobilization_state == 'mobilized':
            equippable = False

    bonuses, hp_mult, eq_abilities = _compute_equipment_bonuses(unit)
    hp_bonus = round(unit.max_hp * hp_mult) - unit.max_hp

    # Build slot info for display
    slots_info = []
    if udef:
        slot_types = EQUIPMENT_SLOTS.get(udef.unit_type, [])
        slot_names = ['weapon', 'accessory', 'armour']
        slot_labels = ['Weapon', 'Accessory', 'Armour']
        equipped_map = {
            'weapon': unit.weapon,
            'accessory': unit.accessory,
            'armour': unit.armour_eq,
        }

        for stype, sname, slabel in zip(slot_types, slot_names, slot_labels):
            slots_info.append({
                'name': sname,
                'label': slabel,
                'type': stype,
                'equipped': equipped_map.get(sname),
            })

    return render_template(
        'military/partials/_unit_detail_popup.html',
        unit=unit,
        udef=udef,
        equippable=equippable,
        bonuses=bonuses,
        hp_bonus=hp_bonus,
        hp_mult=hp_mult,
        eq_abilities=eq_abilities,
        slots_info=slots_info,
        rarity_colors=RARITY_COLORS,
    )


@military.route('/military/unit/<int:unit_id>/detail')
@login_required
def unit_detail(unit_id):
    nation = current_user.nation
    unit = Unit.query.filter_by(id=unit_id, nation_id=nation.id).first()
    if not unit:
        return _error_response('Unit not found.')
    return render_unit_detail(unit, nation)


@military.route('/military/unit/<int:unit_id>/equipment-picker/<slot>')
@login_required
def equipment_picker(unit_id, slot):
    """Return HTML for the equipment selection popup for a specific slot."""
    nation = current_user.nation
    unit = Unit.query.filter_by(id=unit_id, nation_id=nation.id).first()
    if not unit:
        return _error_response('Unit not found.')
    udef = UNIT_DEFS.get(unit.unit_key)
    if not udef:
        return _error_response('Unknown unit type.')

    slot_names = ['weapon', 'accessory', 'armour']
    if slot not in slot_names:
        return _error_response('Invalid slot.')

    slot_types = EQUIPMENT_SLOTS.get(udef.unit_type, [])
    idx = slot_names.index(slot)
    if idx >= len(slot_types):
        return _error_response('Invalid slot for this unit type.')
    eq_type = slot_types[idx]

    from ..helpers import build_equipped_counts
    eq_counts = build_equipped_counts(nation.id)

    equipped = getattr(unit, slot if slot != 'armour' else 'armour_eq')
    all_eq = Equipment.query.filter_by(
        nation_id=nation.id, equipment_type=eq_type
    ).all()
    compatible = []
    for eq in all_eq:
        available = eq.count - eq_counts.get(eq.id, 0)
        if equipped and eq.id == equipped.id:
            available += 1
        if available > 0:
            compatible.append((eq, available))

    buff_type = request.args.get('buff_type', '')
    buff_min  = request.args.get('buff_min', '')
    if buff_type:
        passing = {eq.id for eq in apply_buff_filter([eq for eq, _ in compatible], buff_type, buff_min)}
        compatible = [(eq, avail) for eq, avail in compatible if eq.id in passing]

    return render_template(
        'military/partials/_equipment_picker.html',
        unit=unit,
        udef=udef,
        slot=slot,
        slot_type=eq_type,
        compatible=compatible,
        rarity_colors=RARITY_COLORS,
        buff_filter_options=BUFF_FILTER_OPTIONS,
        buff_type=buff_type,
        buff_min=buff_min,
    )


# ── RECRUITMENT ───────────────────────────────────────────────────────────

@military.route('/military/recruitment')
@login_required
def recruitment():
    return redirect(url_for('military.overview', tab='recruitment'))


@military.route('/military/recruitment-queue')
@login_required
def recruitment_queue():
    """Return the recruitment queue partial (used by refreshRecruitmentQueue trigger)."""
    nation = current_user.nation
    queue = RecruitmentQueue.query.filter_by(nation_id=nation.id).order_by(
        RecruitmentQueue.completes_at
    ).all()
    return render_template(
        'military/partials/recruitment_queue.html',
        queue=queue,
        unit_defs=UNIT_DEFS,
    )


@military.route('/military/recruit', methods=['POST'])
@login_required
def recruit_unit():
    nation = current_user.nation
    unit_key = request.form.get('unit_key', '').strip()
    udef = UNIT_DEFS.get(unit_key)
    if not udef:
        return _error_response('Unknown unit type.')

    if (nation.tier or 1) < udef.tier:
        return _error_response(f'{udef.name} requires Tier {udef.tier}.')

    # Check queue limit (max 10)
    queue_count = RecruitmentQueue.query.filter_by(nation_id=nation.id).count()
    if queue_count >= 10:
        return _error_response('Recruitment queue is full (max 10).')

    if not _can_afford(nation, udef.recruit_cost):
        return _error_response('Insufficient resources to recruit this unit.')

    _deduct_cost(nation, udef.recruit_cost)

    now = datetime.now(timezone.utc)
    entry = RecruitmentQueue(
        nation_id=nation.id,
        unit_key=unit_key,
        started_at=now,
        completes_at=now + timedelta(seconds=udef.recruit_time),
    )
    db.session.add(entry)
    db.session.commit()

    resp = current_app.response_class('', status=200, mimetype='text/html')
    resp.headers['HX-Trigger'] = json.dumps({
        'showMessage': {'message': f'{udef.name} recruitment started!', 'type': 'success'},
        'refreshResourceFooter': True,
        'refreshRecruitmentQueue': True,
    })
    return resp


@military.route('/military/recruit/<int:queue_id>/cancel', methods=['POST'])
@login_required
def cancel_recruitment(queue_id):
    nation = current_user.nation
    entry = RecruitmentQueue.query.filter_by(id=queue_id, nation_id=nation.id).first()
    if not entry:
        return _error_response('Queue entry not found.')
    # Refund 50% of costs
    udef = UNIT_DEFS.get(entry.unit_key)
    if udef:
        for res, amount in udef.recruit_cost.items():
            nation.add_resource(res, amount * 0.5)
    db.session.delete(entry)
    db.session.commit()

    queue = RecruitmentQueue.query.filter_by(nation_id=nation.id).order_by(
        RecruitmentQueue.completes_at
    ).all()
    resp_html = render_template(
        'military/partials/recruitment_queue.html',
        queue=queue,
        unit_defs=UNIT_DEFS,
    )
    resp = current_app.response_class(resp_html, status=200, mimetype='text/html')
    resp.headers['HX-Trigger'] = json.dumps({
        'showMessage': {'message': 'Recruitment cancelled. 50% resources refunded.', 'type': 'success'},
        'refreshResourceFooter': True,
    })
    return resp


# ── BATTLE HISTORY ────────────────────────────────────────────────────────

@military.route('/military/battles')
@login_required
def battles():
    nation = current_user.nation
    mine = and_(
        or_(Battle.attacker_nation_id == nation.id, Battle.defender_nation_id == nation.id)
    )
    my_active = Battle.query.filter(mine, Battle.status == 'active').order_by(
        Battle.started_at.desc()
    ).all()
    my_history = Battle.query.filter(mine, Battle.status == 'finished').order_by(
        Battle.finished_at.desc()
    ).limit(50).all()
    global_active = Battle.query.filter_by(status='active').order_by(
        Battle.started_at.desc()
    ).all()
    return render_template(
        'military/battles.html',
        my_active=my_active,
        my_history=my_history,
        global_active=global_active,
        default_tab=request.args.get('tab', 'active'),
    )


# ── BATTLE ────────────────────────────────────────────────────────────────

def _snapshot_to_units(snapshot_json):
    """Convert a JSON snapshot string to list of SimpleNamespace objects for templates.

    New snapshots store base stats separately from effective stats.
    Old snapshots store effective values in the base stat fields — we detect
    this by checking for the ``effective_firepower`` key and add aliases.
    """
    if not snapshot_json:
        return []
    units = []
    for d in json.loads(snapshot_json):
        ns = SimpleNamespace(**d)
        # Old snapshots: base stat fields already contain effective values
        if not hasattr(ns, 'effective_firepower'):
            ns.effective_firepower = ns.firepower
            ns.effective_armour = ns.armour
            ns.effective_maneuver = ns.maneuver
            ns.effective_max_hp = ns.max_hp
        # Backward compat defaults for fields added over time
        if not hasattr(ns, 'level'):
            ns.level = 1
        if not hasattr(ns, 'xp'):
            ns.xp = 0
        if not hasattr(ns, 'hp_mult'):
            ns.hp_mult = 1.0
        if not hasattr(ns, 'eq_abilities'):
            ns.eq_abilities = []
        if not hasattr(ns, 'slots'):
            ns.slots = []
        units.append(ns)
    return units


def _get_battle_units(battle):
    """Return (attacker_units, defender_units) — snapshot for finished battles, live for active."""
    if battle.status == 'finished' and battle.attacker_snapshot:
        return (_snapshot_to_units(battle.attacker_snapshot),
                _snapshot_to_units(battle.defender_snapshot))
    return (Unit.query.filter_by(division_id=battle.attacker_division_id, nation_id=battle.attacker_nation_id).order_by(Unit.id).all(),
            Unit.query.filter_by(division_id=battle.defender_division_id, nation_id=battle.defender_nation_id).order_by(Unit.id).all())


@military.route('/military/battle/<int:battle_id>')
@login_required
def battle_view(battle_id):
    battle = Battle.query.filter_by(id=battle_id).first_or_404()
    reports = CombatReport.query.filter_by(
        battle_id=battle.id, attacker_nation_id=battle.attacker_nation_id
    ).order_by(CombatReport.id.desc()).limit(50).all()
    attacker_units, defender_units = _get_battle_units(battle)
    nation = current_user.nation
    return render_template(
        'military/battle.html',
        battle=battle,
        reports=reports,
        attacker_units=attacker_units,
        defender_units=defender_units,
        unit_defs=UNIT_DEFS,
        is_participant=nation and nation.id in (battle.attacker_nation_id, battle.defender_nation_id),
    )


# ── PEACEKEEPING ─────────────────────────────────────────────────────────

def _get_or_create_npc_nation():
    """Get (or create) the system NPC nation used for peacekeeping opponents."""
    npc_user = User.query.filter_by(username='_system_npc').first()
    if npc_user and npc_user.nation:
        return npc_user.nation

    if not npc_user:
        npc_user = User(username='_system_npc', is_admin=False)
        npc_user.set_password(random.randbytes(32).hex())
        db.session.add(npc_user)
        db.session.flush()

    npc_nation = Nation(user_id=npc_user.id, name='Insurgents')
    db.session.add(npc_nation)
    db.session.flush()
    return npc_nation


def _generate_peacekeeping_opponent(player_division, npc_nation_id):
    """Create a half-strength NPC division mirroring the player's units."""
    alive_units = Unit.query.filter_by(division_id=player_division.id, nation_id=player_division.nation_id).filter(Unit.hp > 0).all()

    total_strength = sum(u.effective_firepower + u.effective_armour + u.effective_maneuver for u in alive_units)
    target = total_strength / 2

    npc_div = Division(nation_id=npc_nation_id, name='Insurgent Forces',
                       mobilization_state='mobilized')
    db.session.add(npc_div)
    db.session.flush()

    unit_keys = [u.unit_key for u in alive_units]
    random.shuffle(unit_keys)

    current_strength = 0
    created = 0
    for key in unit_keys:
        if current_strength >= target and created >= 1:
            break
        udef = UNIT_DEFS.get(key)
        if not udef:
            continue
        unit = Unit.create_from_def(npc_nation_id, key, division_id=npc_div.id)
        db.session.add(unit)
        current_strength += udef.firepower + udef.armour + udef.maneuver
        created += 1

    return npc_div


@military.route('/military/division/<int:div_id>/peacekeeping', methods=['POST'])
@login_required
def deploy_peacekeeping(div_id):
    nation = current_user.nation
    div = Division.query.filter_by(id=div_id, nation_id=nation.id).first()
    if not div:
        return _error_response('Division not found.')
    if div.mobilization_state != 'mobilized':
        return _error_response('Division must be mobilized for peacekeeping.')
    if div.in_combat:
        return _error_response('Division is already in combat.')

    alive_count = Unit.query.filter_by(division_id=div.id).filter(Unit.hp > 0).count()
    if alive_count < 1:
        return _error_response('Division has no alive units.')

    npc_nation = _get_or_create_npc_nation()
    npc_div = _generate_peacekeeping_opponent(div, npc_nation.id)

    battle = Battle(
        attacker_division_id=div.id,
        defender_division_id=npc_div.id,
        attacker_division_name=div.name,
        defender_division_name=npc_div.name,
        attacker_nation_id=nation.id,
        defender_nation_id=npc_nation.id,
        battle_type='pve',
    )
    db.session.add(battle)
    div.in_combat = True
    npc_div.in_combat = True
    db.session.commit()

    return _division_list_response(nation, f'{div.name} deployed on peacekeeping!')


@military.route('/military/battle/<int:battle_id>/status')
@login_required
def battle_status(battle_id):
    battle = Battle.query.filter_by(id=battle_id).first_or_404()
    reports = CombatReport.query.filter_by(
        battle_id=battle.id, attacker_nation_id=battle.attacker_nation_id
    ).order_by(CombatReport.id.desc()).limit(50).all()
    attacker_units, defender_units = _get_battle_units(battle)
    return render_template(
        'military/partials/battle_status.html',
        battle=battle,
        reports=reports,
        attacker_units=attacker_units,
        defender_units=defender_units,
        unit_defs=UNIT_DEFS,
    )


@military.route('/military/battle/<int:battle_id>/unit/<side>/<int:index>')
@login_required
def battle_unit_detail(battle_id, side, index):
    """Unit detail popup for battle view — always renders from snapshot data."""
    battle = Battle.query.filter_by(id=battle_id).first_or_404()

    if side not in ('attacker', 'defender'):
        return _error_response('Invalid side.')

    attacker_units, defender_units = _get_battle_units(battle)
    units = attacker_units if side == 'attacker' else defender_units

    if index < 0 or index >= len(units):
        return _error_response('Unit not found.')

    unit = units[index]

    # For live Unit objects (active battles), snapshot on-the-fly so we
    # always render through the same code path as finished battles.
    if isinstance(unit, Unit):
        from ..game.combat import _snapshot_units
        snap = _snapshot_units([unit])[0]
    else:
        snap = vars(unit)

    return _render_snapshot_detail(snap)


def _render_snapshot_detail(snap):
    """Render the unit detail popup entirely from snapshot data."""
    udef = UNIT_DEFS.get(snap['unit_key'])

    # Build a SimpleNamespace with base stats for the template
    unit_ns = SimpleNamespace(
        unit_key=snap['unit_key'],
        custom_name=snap.get('custom_name', ''),
        level=snap.get('level', 1),
        xp=snap.get('xp', 0),
        hp=snap['hp'],
        max_hp=snap['max_hp'],
        firepower=snap.get('firepower', snap.get('effective_firepower', 0)),
        armour=snap.get('armour', snap.get('effective_armour', 0)),
        maneuver=snap.get('maneuver', snap.get('effective_maneuver', 0)),
    )

    # Equipment bonuses = effective - base
    eff_fp = snap.get('effective_firepower', unit_ns.firepower)
    eff_ar = snap.get('effective_armour', unit_ns.armour)
    eff_mn = snap.get('effective_maneuver', unit_ns.maneuver)
    bonuses = {
        'firepower': eff_fp - unit_ns.firepower,
        'armour': eff_ar - unit_ns.armour,
        'maneuver': eff_mn - unit_ns.maneuver,
    }

    hp_mult = snap.get('hp_mult', 1.0)
    hp_bonus = round(snap['max_hp'] * hp_mult) - snap['max_hp']
    eq_abilities = snap.get('eq_abilities', [])

    # Rebuild slots_info with SimpleNamespace equipment objects for the template
    slots_info = []
    for slot_data in snap.get('slots', []):
        eq_obj = None
        if slot_data.get('equipped'):
            eq_raw = slot_data['equipped']
            eq_obj = SimpleNamespace(
                equipment_type=eq_raw['equipment_type'],
                rarity=eq_raw['rarity'],
                is_foil=eq_raw.get('is_foil', False),
                buffs=[SimpleNamespace(**b) for b in eq_raw.get('buffs', [])],
            )
        slots_info.append({
            'name': '',
            'label': slot_data['label'],
            'type': slot_data['type'],
            'equipped': eq_obj,
        })

    return render_template(
        'military/partials/_unit_detail_popup.html',
        unit=unit_ns,
        udef=udef,
        equippable=False,
        bonuses=bonuses,
        hp_bonus=hp_bonus,
        hp_mult=hp_mult,
        eq_abilities=eq_abilities,
        slots_info=slots_info,
        rarity_colors=RARITY_COLORS,
    )
