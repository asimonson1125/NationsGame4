import json
from datetime import datetime, timezone, timedelta
from flask import render_template, request, url_for, redirect, current_app
from flask_login import login_required, current_user
from sqlalchemy import or_

from .. import db
from ..models import Nation, War, WarBattle, WarDeploymentQueue, Division, Message, Battle, Unit
from ..helpers import error_response as _error_response
from ..game.war import (
    compute_war_scores, count_offensive_victories,
    resolve_war_compensation, resolve_war_annexation, resolve_white_peace,
    get_active_war,
)
from . import war


# ── Helpers ────────────────────────────────────────────────────────────────

def _war_participant(war_obj):
    """Return the current user's nation_id if they are a participant, else None."""
    nation = current_user.nation
    if not nation:
        return None
    if nation.id in (war_obj.attacker_nation_id, war_obj.defender_nation_id):
        return nation.id
    return None


def _send_war_mail(recipient_id, subject, body):
    db.session.add(Message(
        sender_id=None,
        recipient_id=recipient_id,
        subject=subject,
        body=body,
        message_type='system',
    ))


def _rescind_peace_mail(war_obj):
    """If a peace offer is pending, send a rescission mail to the waiting party."""
    if not war_obj.peace_offered_by:
        return
    waiting_id = (
        war_obj.defender_nation_id
        if war_obj.peace_offered_by == war_obj.attacker_nation_id
        else war_obj.attacker_nation_id
    )
    link = f'<a href="/war/{war_obj.id}" class="text-amber-400 hover:text-amber-300 underline">View War</a>'
    _send_war_mail(
        waiting_id,
        f'White Peace Offer Rescinded — {war_obj.name}',
        f'The white peace offer has been rescinded.\n\n{link}',
    )


def _war_response(message, msg_type='success', redirect_url=None):
    """Return an HTMX-friendly response for war actions."""
    if redirect_url:
        resp = current_app.response_class('', status=200)
        resp.headers['HX-Redirect'] = redirect_url
        resp.headers['HX-Trigger'] = json.dumps(
            {'showMessage': {'message': message, 'type': msg_type}}
        )
        return resp
    resp = current_app.response_class('', status=200)
    resp.headers['HX-Trigger'] = json.dumps(
        {'showMessage': {'message': message, 'type': msg_type}}
    )
    return resp


# ── Wars list (HTMX partial) ───────────────────────────────────────────────

@war.route('/war/wars')
@login_required
def wars_list():
    nation = current_user.nation
    my_wars = War.query.filter(
        or_(War.attacker_nation_id == nation.id,
            War.defender_nation_id == nation.id)
    ).order_by(War.declared_at.desc()).all()

    active = [w for w in my_wars if w.status == 'active']
    history = [w for w in my_wars if w.status != 'active']

    return render_template(
        'war/partials/wars_list.html',
        active_wars=active,
        war_history=history,
        nation=nation,
    )


# ── Declare war ────────────────────────────────────────────────────────────

@war.route('/war/declare/<int:nation_id>', methods=['GET', 'POST'])
@login_required
def declare_war(nation_id):
    my_nation = current_user.nation
    target = Nation.query.get_or_404(nation_id)

    if target.id == my_nation.id:
        return _error_response('You cannot declare war on yourself.')
    if current_user.vacation_mode:
        return _error_response('Vacation mode is active.')
    if (my_nation.tier or 1) < 2:
        return _error_response('War is unlocked at Tier 2.')
    if (target.tier or 1) < (my_nation.tier or 1):
        return _error_response('You cannot declare war on a nation of lower tier than yours.')

    existing = get_active_war(my_nation.id, target.id)
    if existing:
        return _error_response('An active war already exists between these nations.')

    if request.method == 'GET':
        return render_template('war/declare.html', target=target, nation=my_nation)

    # POST — process declaration
    name = request.form.get('war_name', '').strip()
    casus_belli = request.form.get('casus_belli', '').strip()

    if not name:
        return _error_response('War name is required.')
    if len(name) > 200:
        return _error_response('War name must be 200 characters or fewer.')
    if not casus_belli:
        return _error_response('Casus belli is required.')
    if len(casus_belli) > 2000:
        return _error_response('Casus belli must be 2000 characters or fewer.')

    new_war = War(
        attacker_nation_id=my_nation.id,
        defender_nation_id=target.id,
        name=name,
        casus_belli=casus_belli,
    )
    db.session.add(new_war)
    db.session.flush()

    link = f'<a href="/war/{new_war.id}" class="text-amber-400 hover:text-amber-300 underline">View War</a>'
    _send_war_mail(
        my_nation.id,
        f'War Declared — {name}',
        f'You have declared war on {target.name}.\n\nCasus belli: {casus_belli}\n\n{link}',
    )
    _send_war_mail(
        target.id,
        f'War Declared! — {name}',
        f'{my_nation.name} has declared war on you.\n\nCasus belli: {casus_belli}\n\n{link}',
    )
    db.session.commit()

    return redirect(url_for('war.war_detail', war_id=new_war.id))


# ── War detail ─────────────────────────────────────────────────────────────

@war.route('/war/<int:war_id>')
@login_required
def war_detail(war_id):
    war_obj = War.query.get_or_404(war_id)
    nation = current_user.nation

    my_nation_id = _war_participant(war_obj)
    is_participant = my_nation_id is not None
    is_attacker = is_participant and my_nation_id == war_obj.attacker_nation_id

    scores = compute_war_scores(war_obj)

    # Deployments in-flight for current user
    active_deploy = None
    active_deploy_div = None
    if is_participant:
        active_deploy = WarDeploymentQueue.query.filter_by(
            war_id=war_obj.id,
            deploying_nation_id=my_nation_id,
            status='traveling',
        ).first()
        if active_deploy:
            active_deploy_div = Division.query.filter_by(
                id=active_deploy.division_id, nation_id=my_nation_id
            ).first()

    # All traveling division IDs for this nation (any war)
    traveling_div_ids = {
        e.division_id for e in WarDeploymentQueue.query.filter_by(
            deploying_nation_id=my_nation_id, status='traveling'
        ).all()
    } if is_participant else set()

    # My mobilized, non-defensive, non-traveling, non-combat divisions
    my_divisions = []
    if is_participant:
        candidates = Division.query.filter_by(
            nation_id=my_nation_id,
            mobilization_state='mobilized',
            is_defensive=False,
        ).filter(Division.in_combat == False).all()
        my_divisions = [d for d in candidates if d.id not in traveling_div_ids]

    # Current defensive division (nation-level)
    my_defensive_div = None
    if is_participant:
        my_defensive_div = Division.query.filter_by(
            nation_id=my_nation_id,
            is_defensive=True,
        ).first()

    # Resolved battles for this war
    war_battles = war_obj.battles.all()
    resolved_battles = []
    for wb in war_battles:
        b = Battle.query.filter_by(
            id=wb.battle_id, attacker_nation_id=wb.attacker_nation_id
        ).first()
        if b:
            resolved_battles.append((wb, b))
    resolved_battles.sort(key=lambda t: t[1].started_at, reverse=True)

    # Annexation eligibility
    my_offensive_wins = count_offensive_victories(war_obj, my_nation_id) if is_participant else 0

    return render_template(
        'war/war_detail.html',
        war=war_obj,
        nation=nation,
        is_participant=is_participant,
        is_attacker=is_attacker,
        my_nation_id=my_nation_id,
        scores=scores,
        active_deploy=active_deploy,
        active_deploy_div=active_deploy_div,
        my_divisions=my_divisions,
        my_defensive_div=my_defensive_div,
        resolved_battles=resolved_battles,
        my_offensive_wins=my_offensive_wins,
    )


# ── Deploy attack (24-hour travel) ─────────────────────────────────────────

@war.route('/war/<int:war_id>/deploy', methods=['POST'])
@login_required
def deploy_attack(war_id):
    war_obj = War.query.get_or_404(war_id)
    my_nation_id = _war_participant(war_obj)
    if not my_nation_id:
        return _error_response('You are not a participant in this war.')
    if war_obj.status != 'active':
        return _error_response('This war has already ended.')
    if current_user.vacation_mode:
        return _error_response('Vacation mode is active.')

    # Check no existing travel for this nation in this war
    existing = WarDeploymentQueue.query.filter_by(
        war_id=war_obj.id,
        deploying_nation_id=my_nation_id,
        status='traveling',
    ).first()
    if existing:
        return _error_response('You already have a division en route.')

    div_id = request.form.get('division_id', type=int)
    if not div_id:
        return _error_response('No division selected.')

    div = Division.query.filter_by(id=div_id, nation_id=my_nation_id).first()
    if not div:
        return _error_response('Division not found.')
    if div.mobilization_state != 'mobilized':
        return _error_response('Division must be mobilized to deploy.')
    if div.in_combat:
        return _error_response('Division is already in combat.')
    if div.is_defensive:
        return _error_response('Cannot deploy your defensive division offensively.')

    alive = Unit.query.filter_by(division_id=div.id, nation_id=my_nation_id).filter(
        Unit.hp > 0
    ).count()
    if alive < 1:
        return _error_response('Division has no alive units.')

    now = datetime.now(timezone.utc)
    entry = WarDeploymentQueue(
        war_id=war_obj.id,
        deploying_nation_id=my_nation_id,
        division_id=div.id,
        arrives_at=now + timedelta(hours=24),
    )
    db.session.add(entry)
    db.session.commit()

    resp = current_app.response_class('', status=200)
    resp.headers['HX-Redirect'] = url_for('war.war_detail', war_id=war_id)
    resp.headers['HX-Trigger'] = json.dumps(
        {'showMessage': {'message': f'"{div.name}" is en route — arrives in 24 hours.', 'type': 'success'}}
    )
    return resp


# ── Cancel deployment ──────────────────────────────────────────────────────

@war.route('/war/<int:war_id>/cancel-deploy/<int:queue_id>', methods=['POST'])
@login_required
def cancel_deploy(war_id, queue_id):
    war_obj = War.query.get_or_404(war_id)
    my_nation_id = _war_participant(war_obj)
    if not my_nation_id:
        return _error_response('Not a participant.')

    entry = WarDeploymentQueue.query.filter_by(
        id=queue_id, war_id=war_id, deploying_nation_id=my_nation_id, status='traveling'
    ).first()
    if not entry:
        return _error_response('Deployment not found or already arrived.')

    now = datetime.now(timezone.utc)
    arrives = entry.arrives_at
    if arrives.tzinfo is None:
        arrives = arrives.replace(tzinfo=timezone.utc)
    if arrives <= now:
        return _error_response('Deployment has already arrived.')

    entry.status = 'cancelled'
    db.session.commit()

    resp = current_app.response_class('', status=200)
    resp.headers['HX-Redirect'] = url_for('war.war_detail', war_id=war_id)
    resp.headers['HX-Trigger'] = json.dumps(
        {'showMessage': {'message': 'Deployment cancelled.', 'type': 'success'}}
    )
    return resp


# ── Peace offers ───────────────────────────────────────────────────────────

@war.route('/war/<int:war_id>/offer-peace', methods=['POST'])
@login_required
def offer_peace(war_id):
    war_obj = War.query.get_or_404(war_id)
    my_nation_id = _war_participant(war_obj)
    if not my_nation_id:
        return _error_response('Not a participant.')
    if war_obj.status != 'active':
        return _error_response('This war has already ended.')

    war_obj.peace_offered_by = my_nation_id
    opponent_id = (war_obj.defender_nation_id
                   if my_nation_id == war_obj.attacker_nation_id
                   else war_obj.attacker_nation_id)
    my_nation = current_user.nation
    link = f'<a href="/war/{war_obj.id}" class="text-amber-400 hover:text-amber-300 underline">View War</a>'
    _send_war_mail(
        opponent_id,
        f'White Peace Offered — {war_obj.name}',
        f'{my_nation.name} has offered unconditional white peace.\n\n{link}',
    )
    db.session.commit()

    resp = current_app.response_class('', status=200)
    resp.headers['HX-Redirect'] = url_for('war.war_detail', war_id=war_id)
    resp.headers['HX-Trigger'] = json.dumps(
        {'showMessage': {'message': 'White peace offered.', 'type': 'success'}}
    )
    return resp


@war.route('/war/<int:war_id>/cancel-peace', methods=['POST'])
@login_required
def cancel_peace(war_id):
    war_obj = War.query.get_or_404(war_id)
    my_nation_id = _war_participant(war_obj)
    if not my_nation_id:
        return _error_response('Not a participant.')
    if war_obj.peace_offered_by != my_nation_id:
        return _error_response('No active peace offer to cancel.')

    _rescind_peace_mail(war_obj)
    war_obj.peace_offered_by = None
    db.session.commit()

    resp = current_app.response_class('', status=200)
    resp.headers['HX-Redirect'] = url_for('war.war_detail', war_id=war_id)
    resp.headers['HX-Trigger'] = json.dumps(
        {'showMessage': {'message': 'Peace offer withdrawn.', 'type': 'success'}}
    )
    return resp


@war.route('/war/<int:war_id>/accept-peace', methods=['POST'])
@login_required
def accept_peace(war_id):
    war_obj = War.query.get_or_404(war_id)
    my_nation_id = _war_participant(war_obj)
    if not my_nation_id:
        return _error_response('Not a participant.')
    if war_obj.status != 'active':
        return _error_response('This war has already ended.')
    if war_obj.peace_offered_by == my_nation_id or war_obj.peace_offered_by is None:
        return _error_response('No peace offer to accept.')

    resolve_white_peace(war_obj)
    opponent_id = war_obj.peace_offered_by
    link = f'<a href="/war/{war_obj.id}" class="text-amber-400 hover:text-amber-300 underline">View War</a>'
    _send_war_mail(
        opponent_id,
        f'White Peace Accepted — {war_obj.name}',
        f'Your white peace offer was accepted. The war is over.\n\n{link}',
    )
    db.session.commit()

    resp = current_app.response_class('', status=200)
    resp.headers['HX-Redirect'] = url_for('war.war_detail', war_id=war_id)
    resp.headers['HX-Trigger'] = json.dumps(
        {'showMessage': {'message': 'White peace accepted. The war is over.', 'type': 'success'}}
    )
    return resp


# ── War settlements ────────────────────────────────────────────────────────

@war.route('/war/<int:war_id>/demand-compensation', methods=['POST'])
@login_required
def demand_compensation(war_id):
    war_obj = War.query.get_or_404(war_id)
    my_nation_id = _war_participant(war_obj)
    if not my_nation_id:
        return _error_response('Not a participant.')
    if war_obj.status != 'active':
        return _error_response('This war has already ended.')

    scores = compute_war_scores(war_obj)
    if my_nation_id == war_obj.attacker_nation_id and not scores['attacker_can_demand']:
        return _error_response('You need a lead of 3+ victories to demand compensation.')
    if my_nation_id == war_obj.defender_nation_id and not scores['defender_can_demand']:
        return _error_response('You need a lead of 3+ victories to demand compensation.')

    loser_id = (war_obj.defender_nation_id
                if my_nation_id == war_obj.attacker_nation_id
                else war_obj.attacker_nation_id)
    _rescind_peace_mail(war_obj)
    resolve_war_compensation(war_obj, my_nation_id, db.session)

    link = f'<a href="/war/{war_obj.id}" class="text-amber-400 hover:text-amber-300 underline">View War</a>'
    _send_war_mail(
        loser_id,
        f'War Reparations Demanded — {war_obj.name}',
        f'35% of your resource stockpiles have been taken as war reparations.\n\n{link}',
    )
    db.session.commit()

    resp = current_app.response_class('', status=200)
    resp.headers['HX-Redirect'] = url_for('war.war_detail', war_id=war_id)
    resp.headers['HX-Trigger'] = json.dumps(
        {'showMessage': {'message': 'War compensation claimed.', 'type': 'success'},
         'refreshResourceFooter': True}
    )
    return resp


@war.route('/war/<int:war_id>/demand-annexation', methods=['POST'])
@login_required
def demand_annexation(war_id):
    war_obj = War.query.get_or_404(war_id)
    my_nation_id = _war_participant(war_obj)
    if not my_nation_id:
        return _error_response('Not a participant.')
    if war_obj.status != 'active':
        return _error_response('This war has already ended.')

    scores = compute_war_scores(war_obj)
    can_demand = (scores['attacker_can_demand'] if my_nation_id == war_obj.attacker_nation_id
                  else scores['defender_can_demand'])
    if not can_demand:
        my_lead = (scores['attacker_lead'] if my_nation_id == war_obj.attacker_nation_id
                   else scores['defender_lead'])
        return _error_response(
            f'Annexation requires a lead of 3+ total victories (currently {my_lead}).'
        )

    offensive_wins = count_offensive_victories(war_obj, my_nation_id)
    if offensive_wins < 3:
        return _error_response(
            f'Annexation requires 3 offensive victories. You have {offensive_wins}.'
        )

    loser_id = (war_obj.defender_nation_id
                if my_nation_id == war_obj.attacker_nation_id
                else war_obj.attacker_nation_id)
    _rescind_peace_mail(war_obj)
    resolve_war_annexation(war_obj, my_nation_id, db.session)

    link = f'<a href="/war/{war_obj.id}" class="text-amber-400 hover:text-amber-300 underline">View War</a>'
    _send_war_mail(
        loser_id,
        f'Annexed — {war_obj.name}',
        f'20% of your land and population have been annexed as a result of the war.\n\n{link}',
    )
    db.session.commit()

    resp = current_app.response_class('', status=200)
    resp.headers['HX-Redirect'] = url_for('war.war_detail', war_id=war_id)
    resp.headers['HX-Trigger'] = json.dumps(
        {'showMessage': {'message': 'Annexation complete.', 'type': 'success'},
         'refreshResourceFooter': True}
    )
    return resp
