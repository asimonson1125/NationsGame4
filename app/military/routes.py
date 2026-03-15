import json
import random
from types import SimpleNamespace
from datetime import datetime, timezone, timedelta
from flask import redirect, render_template, request, url_for, current_app
from flask_login import login_required, current_user
from .. import db
from sqlalchemy import or_, and_
from ..models import Division, Unit, RecruitmentQueue, Battle, CombatReport, Nation, User, Equipment, MissionOffer, MissionRecord, War
from ..helpers import error_response as _error_response, can_afford as _can_afford, deduct_cost as _deduct_cost, compute_total_upkeep
from ..game.units import UNIT_DEFS
from ..game.missions import MISSION_DEFS, roll_two_missions
from ..game.constants import CONTINENTS
from ..game.equipment import EQUIPMENT_SLOTS, RARITY_COLORS, get_slot_category, BUFF_FILTER_OPTIONS, apply_buff_filter
from . import military


# ── OVERVIEW ──────────────────────────────────────────────────────────────

def _building_lock_map(nation_id, unit_defs):
    """Return dict of unit_key -> {'name': str, 'level': int} for units locked by building prereqs."""
    from ..game.buildings import building_for_unit_type, required_level as _req_level, BUILDING_DEFS
    from ..models import NationBuilding
    nb_levels = {nb.building_key: nb.level for nb in NationBuilding.query.filter_by(nation_id=nation_id).all()}
    locks = {}
    for unit_key, udef in unit_defs.items():
        bkey = building_for_unit_type(udef.unit_type)
        if bkey:
            req_lvl = _req_level(bkey, udef.tier)
            if nb_levels.get(bkey, 0) < req_lvl:
                locks[unit_key] = {'name': BUILDING_DEFS[bkey].name, 'level': req_lvl}
    return locks


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

    player_unit_defs = {k: v for k, v in UNIT_DEFS.items() if not v.npc_only}
    return render_template(
        'military/overview.html',
        nation=nation,
        divisions=divisions,
        reserve_units=reserve_units,
        unit_defs=player_unit_defs,
        queue=queue,
        total_upkeep=total_upkeep,
        default_tab=request.args.get('tab', 'overview'),
        div_battles=_get_div_battles(nation.id),
        div_traveling=_get_div_traveling(nation.id),
        building_lock_map=_building_lock_map(nation.id, player_unit_defs),
        active_wars=_get_active_wars(nation.id),
        mission_offers=_get_available_missions(nation.id),
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
    from ..models import WarDeploymentQueue
    nation = current_user.nation
    div = Division.query.filter_by(id=div_id, nation_id=nation.id).first()
    if not div:
        return _error_response('Division not found.')
    if div.in_combat:
        return _error_response('Cannot disband a division that is in combat.')
    traveling = WarDeploymentQueue.query.filter_by(
        division_id=div.id, deploying_nation_id=nation.id, status='traveling'
    ).first()
    if traveling:
        return _error_response('Cannot disband a division that is en route to battle.')
    if div.is_defensive:
        div.is_defensive = False
    # Move units to reserve
    Unit.query.filter_by(division_id=div.id).update({'division_id': None})
    db.session.delete(div)
    db.session.commit()
    return _division_list_response(nation, f'Division "{div.name}" disbanded.')


@military.route('/military/division/<int:div_id>/mobilize', methods=['POST'])
@login_required
def mobilize_division(div_id):
    nation = current_user.nation
    if current_user.vacation_mode:
        return _error_response('Vacation mode is active. Disable it to deploy.')
    div = Division.query.filter_by(id=div_id, nation_id=nation.id).first()
    if not div:
        return _error_response('Division not found.')
    if div.mobilization_state == 'mobilized':
        return _error_response('Division is already mobilized.')

    # Consume 1 hour of upkeep for all units in this division
    div_units = Unit.query.filter_by(division_id=div.id, nation_id=nation.id).filter(Unit.hp > 0).all()
    upkeep_cost = {}
    for unit in div_units:
        udef = UNIT_DEFS.get(unit.unit_key)
        if udef:
            for res, rate in udef.upkeep.items():
                upkeep_cost[res] = upkeep_cost.get(res, 0) + rate

    if not _can_afford(nation, upkeep_cost):
        return _error_response('Not enough resources for 1 hour of mobilization upkeep.')

    _deduct_cost(nation, upkeep_cost)
    div.mobilization_state = 'mobilized'
    db.session.commit()
    return _division_list_response(nation, f'"{div.name}" mobilized.')


@military.route('/military/division/<int:div_id>/demobilize', methods=['POST'])
@login_required
def demobilize_division(div_id):
    from ..models import WarDeploymentQueue
    nation = current_user.nation
    div = Division.query.filter_by(id=div_id, nation_id=nation.id).first()
    if not div:
        return _error_response('Division not found.')
    if div.in_combat:
        return _error_response('Cannot demobilize a division in combat.')
    traveling = WarDeploymentQueue.query.filter_by(
        division_id=div.id, deploying_nation_id=nation.id, status='traveling'
    ).first()
    if traveling:
        return _error_response('Cannot demobilize a division that is en route to battle.')
    if div.is_defensive:
        return _error_response('Cannot demobilize your defensive division. Assign a different division to defense first.')
    div.mobilization_state = 'demobilized'
    db.session.commit()
    return _division_list_response(nation, f'"{div.name}" demobilized.')


@military.route('/military/set-defense', methods=['POST'])
@login_required
def set_defense():
    nation = current_user.nation
    div_id = request.form.get('division_id', type=int)

    if div_id is None:
        # Clear defensive designation
        Division.query.filter_by(nation_id=nation.id, is_defensive=True).update({'is_defensive': False})
        db.session.commit()
        return _division_list_response(nation, 'Defensive division cleared.')

    div = Division.query.filter_by(id=div_id, nation_id=nation.id).first()
    if not div:
        return _error_response('Division not found.')
    if div.mobilization_state != 'mobilized':
        return _error_response('Division must be mobilized to serve as a defensive division.')
    if div.in_combat:
        return _error_response('Cannot designate a division that is in combat.')
    traveling = _get_div_traveling(nation.id)
    if div.id in traveling:
        return _error_response('Cannot designate a division that is en route.')

    # Clear any previous defensive division for this nation
    Division.query.filter_by(nation_id=nation.id, is_defensive=True).update({'is_defensive': False})
    div.is_defensive = True
    db.session.commit()
    return _division_list_response(nation, f'"{div.name}" set as your defensive division.')


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


def _get_active_wars(nation_id):
    """Return active Wars where this nation is a participant."""
    return War.query.filter(
        War.status == 'active',
        or_(War.attacker_nation_id == nation_id, War.defender_nation_id == nation_id)
    ).order_by(War.declared_at.desc()).all()


def _get_div_traveling(nation_id):
    """Return dict mapping division_id -> WarDeploymentQueue for traveling deployments."""
    from ..models import WarDeploymentQueue
    entries = WarDeploymentQueue.query.filter_by(
        deploying_nation_id=nation_id, status='traveling'
    ).all()
    return {e.division_id: e for e in entries}


def _get_available_missions(nation_id):
    """Return list of {offer, mdef} for available mission offers."""
    offers = MissionOffer.query.filter_by(nation_id=nation_id, status='available').all()
    return [{'offer': o, 'mdef': MISSION_DEFS[o.mission_key]}
            for o in offers if o.mission_key in MISSION_DEFS]


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
        div_traveling=_get_div_traveling(nation.id),
        active_wars=_get_active_wars(nation.id),
        mission_offers=_get_available_missions(nation.id),
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
        div_traveling=_get_div_traveling(nation.id),
        active_wars=_get_active_wars(nation.id),
        mission_offers=_get_available_missions(nation.id),
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

    upkeep = udef.upkeep if udef else {}

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
        upkeep=upkeep,
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
    from ..game.levels import can_equip_rarity

    compatible = []
    for eq in all_eq:
        if not can_equip_rarity(unit.level, eq.rarity):
            continue
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

    # Check building prerequisite
    from ..game.buildings import building_for_unit_type, required_level as _building_req_level, BUILDING_DEFS
    from ..models import NationBuilding
    bkey = building_for_unit_type(udef.unit_type)
    if bkey:
        req_lvl = _building_req_level(bkey, udef.tier)
        nb = NationBuilding.query.filter_by(nation_id=nation.id, building_key=bkey).first()
        if not nb or nb.level < req_lvl:
            return _error_response(
                f'{udef.name} requires {BUILDING_DEFS[bkey].name} Lvl {req_lvl}.'
            )

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


@military.route('/military/training-league')
@login_required
def training_league():
    nation = current_user.nation
    return render_template('military/training_league.html', nation=nation)


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
    atk_units = Unit.query.filter_by(division_id=battle.attacker_division_id, nation_id=battle.attacker_nation_id).order_by(Unit.division_joined_at, Unit.id).all()
    if battle.defender_division_id is None:
        def_units = []
    else:
        def_units = Unit.query.filter_by(division_id=battle.defender_division_id, nation_id=battle.defender_nation_id).order_by(Unit.division_joined_at, Unit.id).all()
    return (atk_units, def_units)


@military.route('/military/battle/<int:battle_id>')
@login_required
def battle_view(battle_id):
    battle = Battle.query.filter_by(id=battle_id).first_or_404()
    reports = CombatReport.query.filter_by(
        battle_id=battle.id, attacker_nation_id=battle.attacker_nation_id
    ).order_by(CombatReport.id.desc()).limit(50).all()
    attacker_units, defender_units = _get_battle_units(battle)
    nation = current_user.nation

    battle_title = 'Peacekeeping Combat'
    if battle.battle_type == 'pve_mission' and battle.mission_offer_id:
        offer = MissionOffer.query.filter_by(id=battle.mission_offer_id).first()
        if offer:
            mdef = MISSION_DEFS.get(offer.mission_key)
            if mdef:
                battle_title = mdef.name
    elif battle.battle_type == 'pvp':
        battle_title = battle.name or 'Nation vs Nation'

    return render_template(
        'military/battle.html',
        battle=battle,
        reports=reports,
        attacker_units=attacker_units,
        defender_units=defender_units,
        unit_defs=UNIT_DEFS,
        is_participant=nation and nation.id in (battle.attacker_nation_id, battle.defender_nation_id),
        battle_title=battle_title,
    )


# ── PEACEKEEPING ─────────────────────────────────────────────────────────

# Random names for peacekeeping faux-nations and divisions
_PK_FACTION_NAMES = [
    'Local Insurgents', 'Separatist Movement', 'Rebel Coalition',
    'Militia Front', 'Liberation Army', 'People\'s Resistance',
    'Revolutionary Guard', 'Border Raiders', 'Provincial Militia',
    'Partisan Brigade', 'Rogue Garrison', 'Dissident Forces',
]
_PK_DIVISION_NAMES = [
    'Insurgent Cell', 'Rebel Detachment', 'Militia Squad',
    'Guerrilla Unit', 'Raider Column', 'Partisan Group',
    'Resistance Force', 'Hostile Patrol', 'Irregular Platoon',
]


def _random_peacekeeping_names():
    """Return (faction_name, division_name) for a peacekeeping encounter."""
    return random.choice(_PK_FACTION_NAMES), random.choice(_PK_DIVISION_NAMES)


def _get_or_create_npc_nation():
    """Get (or create) the system NPC nation used for PvE opponents."""
    npc_user = User.query.filter_by(username='_system_npc').first()
    if npc_user and npc_user.nation:
        return npc_user.nation

    if not npc_user:
        npc_user = User(username='_system_npc', is_admin=False, is_system=True, vacation_mode=True)
        npc_user.set_password(random.randbytes(32).hex())
        db.session.add(npc_user)
        db.session.flush()

    npc_nation = Nation(user_id=npc_user.id, name='NPC')
    db.session.add(npc_nation)
    db.session.flush()
    return npc_nation


def _generate_peacekeeping_opponent(player_division, npc_nation_id):
    """Create a half-strength NPC division of infantry units."""
    alive_units = Unit.query.filter_by(division_id=player_division.id, nation_id=player_division.nation_id).filter(Unit.hp > 0).all()

    total_strength = sum(u.effective_firepower + u.effective_armour + u.effective_maneuver for u in alive_units)
    target = total_strength / 2

    faction_name, div_name = _random_peacekeeping_names()
    npc_div = Division(nation_id=npc_nation_id, name=div_name,
                       mobilization_state='mobilized')
    npc_div._pk_faction_name = faction_name  # stash for the route to read
    db.session.add(npc_div)
    db.session.flush()

    # Build pool of infantry-only unit keys from the player's division
    infantry_keys = [u.unit_key for u in alive_units
                     if UNIT_DEFS.get(u.unit_key) and UNIT_DEFS[u.unit_key].unit_type == 'Infantry']
    if not infantry_keys:
        infantry_keys = ['infantry']
    random.shuffle(infantry_keys)

    current_strength = 0
    created = 0
    idx = 0
    while current_strength < target or created < 1:
        key = infantry_keys[idx % len(infantry_keys)]
        idx += 1
        udef = UNIT_DEFS.get(key)
        if not udef:
            continue
        unit = Unit.create_from_def(npc_nation_id, key, division_id=npc_div.id)
        db.session.add(unit)
        current_strength += udef.firepower + udef.armour + udef.maneuver
        created += 1
        # Safety cap: don't spawn more units than the player has × 2
        if created >= len(alive_units) * 2:
            break

    return npc_div


@military.route('/military/division/<int:div_id>/peacekeeping', methods=['POST'])
@login_required
def deploy_peacekeeping(div_id):
    nation = current_user.nation
    if current_user.vacation_mode:
        return _error_response('Vacation mode is active. Disable it to deploy.')
    div = Division.query.filter_by(id=div_id, nation_id=nation.id).first()
    if not div:
        return _error_response('Division not found.')
    if div.mobilization_state != 'mobilized':
        return _error_response('Division must be mobilized for peacekeeping.')
    if div.in_combat:
        return _error_response('Division is already in combat.')
    if div.is_defensive:
        return _error_response('Cannot deploy your defensive division.')
    traveling = _get_div_traveling(nation.id)
    if div.id in traveling:
        return _error_response('Division is currently en route to a war deployment.')

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
        attacker_nation_name=nation.name,
        defender_nation_name=getattr(npc_div, '_pk_faction_name', 'Local Insurgents'),
        battle_type='peacekeeping',
        location=random.choice(CONTINENTS),
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


# ── MISSIONS ──────────────────────────────────────────────────────────────

def _get_completed_mission_keys(nation_id):
    """Return set of mission keys permanently completed by this nation."""
    records = MissionRecord.query.filter_by(nation_id=nation_id).all()
    return {r.mission_key for r in records}


def _get_or_create_offers(nation):
    """Ensure the nation always has 2 MissionOffer rows. Refresh stale slots."""
    now = datetime.now(timezone.utc)
    offers = {o.slot: o for o in MissionOffer.query.filter_by(nation_id=nation.id).all()}
    completed_keys = _get_completed_mission_keys(nation.id)

    for slot in (1, 2):
        offer = offers.get(slot)

        if offer is None:
            # No offer exists for this slot — create one
            _create_offer(nation, slot, completed_keys, {o.mission_key for o in offers.values()})
            continue

        # completed/failed slots are refreshed only when the player collects/acknowledges

    db.session.flush()
    return MissionOffer.query.filter_by(nation_id=nation.id).order_by(MissionOffer.slot).all()


def _create_offer(nation, slot, completed_keys, exclude_keys):
    """Roll a new mission for a slot and upsert the MissionOffer row."""
    missions = roll_two_missions(
        nation_tier=nation.tier or 1,
        completed_keys=completed_keys,
        exclude_keys=exclude_keys,
    )
    if not missions:
        return

    mdef = missions[0]
    existing = MissionOffer.query.filter_by(nation_id=nation.id, slot=slot).first()
    if existing:
        existing.mission_key = mdef.key
        existing.offered_at = datetime.now(timezone.utc)  # noqa: F821 — imported at module top
        existing.status = 'available'
        existing.battle_id = None
        existing.completed_at = None
    else:
        db.session.add(MissionOffer(
            nation_id=nation.id,
            slot=slot,
            mission_key=mdef.key,
        ))


@military.route('/military/missions')
@login_required
def missions():
    """Return the missions tab partial (loaded by HTMX on tab click)."""
    nation = current_user.nation
    offers = _get_or_create_offers(nation)
    db.session.commit()

    divisions = Division.query.filter_by(nation_id=nation.id).order_by(Division.id).all()

    offer_data = []
    for offer in offers:
        mdef = MISSION_DEFS.get(offer.mission_key)
        offer_data.append({'offer': offer, 'mdef': mdef})

    return render_template(
        'military/partials/missions_content.html',
        offer_data=offer_data,
        divisions=divisions,
        unit_defs=UNIT_DEFS,
    )


@military.route('/military/mission/<int:offer_id>/deploy', methods=['POST'])
@login_required
def deploy_mission(offer_id):
    nation = current_user.nation
    if current_user.vacation_mode:
        return _error_response('Vacation mode is active. Disable it to deploy.')
    offer = MissionOffer.query.filter_by(
        id=offer_id, nation_id=nation.id, status='available'
    ).first()
    if not offer:
        return _error_response('Mission not available.')

    mdef = MISSION_DEFS.get(offer.mission_key)
    if not mdef:
        return _error_response('Mission definition not found.')

    div_id = request.form.get('division_id', type=int)
    div = Division.query.filter_by(id=div_id, nation_id=nation.id).first()
    if not div:
        return _error_response('Division not found.')
    if div.mobilization_state != 'mobilized':
        return _error_response('Division must be mobilized to deploy on a mission.')
    if div.in_combat:
        return _error_response('Division is already in combat.')
    if div.is_defensive:
        return _error_response('Cannot deploy your defensive division.')
    traveling = _get_div_traveling(nation.id)
    if div.id in traveling:
        return _error_response('Division is currently en route to a war deployment.')

    alive_count = Unit.query.filter_by(division_id=div.id).filter(Unit.hp > 0).count()
    if alive_count < 1:
        return _error_response('Division has no alive units.')

    npc_nation = _get_or_create_npc_nation()
    npc_div = _generate_mission_opponent(mdef, npc_nation.id)

    battle = Battle(
        attacker_division_id=div.id,
        defender_division_id=npc_div.id,
        attacker_division_name=div.name,
        defender_division_name=mdef.enemy_division_name,
        attacker_nation_id=nation.id,
        defender_nation_id=npc_nation.id,
        attacker_nation_name=nation.name,
        defender_nation_name=mdef.enemy_name,
        battle_type='pve_mission',
        mission_offer_id=offer.id,
        location=mdef.location,
    )
    db.session.add(battle)
    div.in_combat = True
    npc_div.in_combat = True
    offer.status = 'active'
    db.session.flush()

    offer.battle_id = battle.id
    db.session.commit()

    resp = current_app.response_class('', status=200, mimetype='text/html')
    resp.headers['HX-Trigger'] = json.dumps({
        'showMessage': {'message': f'"{div.name}" deployed on mission: {mdef.name}!', 'type': 'success'},
        'refreshDivisionContent': True,
        'refreshMissions': True,
        'refreshResourceFooter': True,
    })
    return resp


@military.route('/military/mission/<int:offer_id>/skip', methods=['POST'])
@login_required
def skip_mission(offer_id):
    nation = current_user.nation

    if (nation.mission_skips_today or 0) >= 5:
        return _error_response('You can only skip 5 missions per day tick.')

    offer = MissionOffer.query.filter_by(
        id=offer_id, nation_id=nation.id, status='available'
    ).first()
    if not offer:
        return _error_response('Mission not available or already active.')

    nation.mission_skips_today = (nation.mission_skips_today or 0) + 1

    completed_keys = _get_completed_mission_keys(nation.id)
    other_offers = MissionOffer.query.filter(
        MissionOffer.nation_id == nation.id,
        MissionOffer.id != offer.id,
    ).all()
    exclude = {o.mission_key for o in other_offers} | {offer.mission_key}

    _create_offer(nation, offer.slot, completed_keys, exclude)
    db.session.commit()

    resp = current_app.response_class('', status=200, mimetype='text/html')
    resp.headers['HX-Trigger'] = json.dumps({
        'showMessage': {'message': 'Mission skipped. A new one has been offered.', 'type': 'info'},
        'refreshMissions': True,
    })
    return resp


@military.route('/military/mission/<int:offer_id>/collect', methods=['POST'])
@login_required
def collect_mission(offer_id):
    """Grant rewards for a completed mission and roll a new offer for that slot."""
    nation = current_user.nation
    offer = MissionOffer.query.filter_by(
        id=offer_id, nation_id=nation.id, status='completed'
    ).first()
    if not offer:
        return _error_response('No completed mission to collect.')

    mdef = MISSION_DEFS.get(offer.mission_key)
    if not mdef:
        return _error_response('Mission definition not found.')

    for res, amount in mdef.rewards.items():
        nation.add_resource(res, amount)

    existing = MissionRecord.query.filter_by(
        nation_id=nation.id, mission_key=offer.mission_key
    ).first()
    if not existing:
        db.session.add(MissionRecord(
            nation_id=nation.id,
            mission_key=offer.mission_key,
            completed_at=offer.completed_at or datetime.now(timezone.utc),
        ))

    completed_keys = _get_completed_mission_keys(nation.id)
    other_offers = MissionOffer.query.filter(
        MissionOffer.nation_id == nation.id,
        MissionOffer.id != offer.id,
    ).all()
    _create_offer(nation, offer.slot, completed_keys,
                  {o.mission_key for o in other_offers})
    db.session.commit()

    resp = current_app.response_class('', status=200, mimetype='text/html')
    resp.headers['HX-Trigger'] = json.dumps({
        'showMessage': {'message': f'Rewards collected for "{mdef.name}"!', 'type': 'success'},
        'refreshMissions': True,
        'refreshResourceFooter': True,
    })
    return resp


@military.route('/military/mission/<int:offer_id>/acknowledge', methods=['POST'])
@login_required
def acknowledge_mission(offer_id):
    """Dismiss a failed mission and roll a new offer for that slot."""
    nation = current_user.nation
    offer = MissionOffer.query.filter_by(
        id=offer_id, nation_id=nation.id, status='failed'
    ).first()
    if not offer:
        return _error_response('No failed mission to acknowledge.')

    completed_keys = _get_completed_mission_keys(nation.id)
    other_offers = MissionOffer.query.filter(
        MissionOffer.nation_id == nation.id,
        MissionOffer.id != offer.id,
    ).all()
    _create_offer(nation, offer.slot, completed_keys,
                  {o.mission_key for o in other_offers})
    db.session.commit()

    resp = current_app.response_class('', status=200, mimetype='text/html')
    resp.headers['HX-Trigger'] = json.dumps({
        'showMessage': {'message': 'Mission acknowledged. A new one has been offered.', 'type': 'info'},
        'refreshMissions': True,
    })
    return resp


def _generate_mission_opponent(mdef, npc_nation_id):
    """Create an NPC division populated according to the mission enemy composition."""
    npc_div = Division(
        nation_id=npc_nation_id,
        name=mdef.enemy_division_name,
        mobilization_state='mobilized',
    )
    db.session.add(npc_div)
    db.session.flush()

    count = random.randint(*mdef.enemy_count)
    keys = list(mdef.enemy_composition.keys())
    weights = [mdef.enemy_composition[k] for k in keys]

    for _ in range(count):
        unit_key = random.choices(keys, weights=weights, k=1)[0]
        unit = Unit.create_from_def(npc_nation_id, unit_key, division_id=npc_div.id)
        db.session.add(unit)

    return npc_div
