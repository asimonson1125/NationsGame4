import json
from flask import render_template, request, redirect, url_for, jsonify
from flask_login import login_required, current_user
from .. import db
from ..models import Alliance, AllianceApplication, Message, Nation
from ..helpers import error_response as _error_response
from . import alliance


IMAGE_EXTS = ('.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', '.svg',
              '.tiff', '.tif', '.ico', '.avif', '.apng', '.jfif')


def _notify_founder_of_application(ally, applicant_nation):
    """Send a system notification to the alliance founder about a new application."""
    if not ally.founder_id:
        return
    nation_url = url_for('main.nation_view', nation_id=applicant_nation.id)
    body = (
        f'<a href="{nation_url}" class="text-amber-400 hover:text-amber-300 font-medium">'
        f'{applicant_nation.name}</a> has applied to join <strong>{ally.name}</strong>.\n\n'
        f'Visit your <a href="{url_for("alliance.alliance_view", id=ally.id)}" '
        f'class="text-amber-400 hover:text-amber-300">alliance page</a> to review applications.'
    )
    msg = Message(
        sender_id=None,
        recipient_id=ally.founder_id,
        subject=f'New application to {ally.name}',
        body=body,
        message_type='system',
    )
    db.session.add(msg)


def _success_redirect(message):
    """Return an HX-Redirect response with a toast trigger."""
    from flask import current_app
    resp = current_app.response_class(status=200)
    resp.headers['HX-Redirect'] = url_for('alliance.my_alliance')
    resp.headers['HX-Trigger'] = json.dumps(
        {'showMessage': {'message': message, 'type': 'success'}}
    )
    return resp


@alliance.route('/alliance')
@login_required
def my_alliance():
    nation = current_user.nation
    if not nation:
        return redirect(url_for('main.index'))
    if nation.alliance_id:
        ally = db.session.get(Alliance, nation.alliance_id)
        if ally:
            return redirect(url_for('alliance.alliance_view', id=ally.id))
    return render_template('alliance/alliance_unallied.html', nation=nation)


@alliance.route('/alliance/<int:id>')
@login_required
def alliance_view(id):
    nation = current_user.nation
    ally = db.session.get(Alliance, id)
    if not ally:
        return redirect(url_for('alliance.my_alliance'))
    members = Nation.query.filter_by(alliance_id=ally.id).order_by(Nation.total_gp.desc()).all()
    total_gp = sum(m.total_gp or 0 for m in members)
    is_founder = nation and ally.founder_id == nation.id
    is_member = nation and nation.alliance_id == ally.id
    applications = []
    pending_application = None
    if is_founder:
        applications = (AllianceApplication.query
                        .filter_by(alliance_id=ally.id, status='pending')
                        .options(db.joinedload(AllianceApplication.nation))
                        .order_by(AllianceApplication.created_at)
                        .all())
    elif nation and not is_member and not nation.alliance_id:
        pending_application = AllianceApplication.query.filter_by(
            alliance_id=ally.id, nation_id=nation.id, status='pending'
        ).first()
    return render_template('alliance/alliance_view.html',
                           alliance=ally, members=members,
                           total_gp=total_gp, is_founder=is_founder,
                           is_member=is_member, nation=nation,
                           applications=applications,
                           pending_application=pending_application)


@alliance.route('/alliance/create', methods=['POST'])
@login_required
def create_alliance():
    nation = current_user.nation
    if not nation:
        return _error_response('No nation found.')
    if nation.alliance_id:
        return _error_response('You are already in an alliance.')
    name = request.form.get('name', '').strip()
    if not name or len(name) < 2:
        return _error_response('Alliance name must be at least 2 characters.')
    if len(name) > 60:
        return _error_response('Alliance name must be 60 characters or fewer.')
    existing = Alliance.query.filter(db.func.lower(Alliance.name) == name.lower()).first()
    if existing:
        return _error_response('An alliance with that name already exists.')
    ally = Alliance(name=name, founder_id=nation.id)
    db.session.add(ally)
    db.session.flush()
    nation.alliance_id = ally.id
    db.session.commit()
    return _success_redirect(f'Alliance "{name}" created!')


@alliance.route('/alliance/apply', methods=['POST'])
@login_required
def apply_to_alliance():
    nation = current_user.nation
    if not nation:
        return _error_response('No nation found.')
    if nation.alliance_id:
        return _error_response('You are already in an alliance.')
    alliance_id = request.form.get('alliance_id', type=int)
    if not alliance_id:
        return _error_response('No alliance specified.')
    ally = db.session.get(Alliance, alliance_id)
    if not ally:
        return _error_response('Alliance not found.')
    existing = AllianceApplication.query.filter_by(
        alliance_id=ally.id, nation_id=nation.id
    ).first()
    if existing:
        if existing.status == 'pending':
            return _error_response('You already have a pending application.')
        # Reopen a previously rejected application
        from datetime import datetime, timezone
        existing.status = 'pending'
        existing.created_at = datetime.now(timezone.utc)
    else:
        db.session.add(AllianceApplication(alliance_id=ally.id, nation_id=nation.id))
    _notify_founder_of_application(ally, nation)
    db.session.commit()
    from flask import current_app
    resp = current_app.response_class(status=204)
    resp.headers['HX-Trigger'] = json.dumps(
        {'showMessage': {'message': f'Application to "{ally.name}" submitted.', 'type': 'success'}}
    )
    return resp


@alliance.route('/alliance/kick/<int:nation_id>', methods=['POST'])
@login_required
def kick_member(nation_id):
    nation = current_user.nation
    if not nation or not nation.alliance_id:
        return _error_response('You are not in an alliance.')
    ally = db.session.get(Alliance, nation.alliance_id)
    if not ally or ally.founder_id != nation.id:
        return _error_response('Only the founder can kick members.')
    if nation_id == nation.id:
        return _error_response('You cannot kick yourself.')
    target = db.session.get(Nation, nation_id)
    if not target or target.alliance_id != ally.id:
        return _error_response('That nation is not in your alliance.')
    target.alliance_id = None
    db.session.commit()
    from flask import current_app
    resp = current_app.response_class(status=204)
    resp.headers['HX-Trigger'] = json.dumps(
        {'showMessage': {'message': f'{target.name} has been removed from the alliance.', 'type': 'success'}}
    )
    return resp


@alliance.route('/alliance/application/<int:id>/approve', methods=['POST'])
@login_required
def approve_application(id):
    nation = current_user.nation
    app_entry = db.session.get(AllianceApplication, id)
    if not app_entry or app_entry.status != 'pending':
        return _error_response('Application not found.')
    ally = db.session.get(Alliance, app_entry.alliance_id)
    if not ally or ally.founder_id != nation.id:
        return _error_response('Only the founder can approve applications.')
    applicant = db.session.get(Nation, app_entry.nation_id)
    if not applicant:
        return _error_response('Applicant nation not found.')
    if applicant.alliance_id:
        app_entry.status = 'rejected'
        db.session.commit()
        return _error_response('That nation has already joined another alliance.')
    app_entry.status = 'approved'
    applicant.alliance_id = ally.id
    # Clear any other pending applications for this nation
    AllianceApplication.query.filter(
        AllianceApplication.nation_id == applicant.id,
        AllianceApplication.id != app_entry.id,
        AllianceApplication.status == 'pending'
    ).update({'status': 'rejected'})
    db.session.commit()
    from flask import current_app
    resp = current_app.response_class(status=204)
    resp.headers['HX-Trigger'] = json.dumps(
        {'showMessage': {'message': f'{applicant.name} approved and added to the alliance.', 'type': 'success'}}
    )
    return resp


@alliance.route('/alliance/application/<int:id>/reject', methods=['POST'])
@login_required
def reject_application(id):
    nation = current_user.nation
    app_entry = db.session.get(AllianceApplication, id)
    if not app_entry or app_entry.status != 'pending':
        return _error_response('Application not found.')
    ally = db.session.get(Alliance, app_entry.alliance_id)
    if not ally or ally.founder_id != nation.id:
        return _error_response('Only the founder can reject applications.')
    app_entry.status = 'rejected'
    db.session.commit()
    from flask import current_app
    resp = current_app.response_class(status=204)
    resp.headers['HX-Trigger'] = json.dumps(
        {'showMessage': {'message': 'Application rejected.', 'type': 'success'}}
    )
    return resp


@alliance.route('/alliance/leave', methods=['POST'])
@login_required
def leave_alliance():
    nation = current_user.nation
    if not nation or not nation.alliance_id:
        return _error_response('You are not in an alliance.')
    ally = db.session.get(Alliance, nation.alliance_id)
    if not ally:
        nation.alliance_id = None
        db.session.commit()
        return _success_redirect('Left alliance.')
    if ally.founder_id == nation.id:
        # Transfer founder to next member, or disband if last
        other = Nation.query.filter(
            Nation.alliance_id == ally.id,
            Nation.id != nation.id
        ).order_by(Nation.total_gp.desc()).first()
        if other:
            ally.founder_id = other.id
            nation.alliance_id = None
            db.session.commit()
            return _success_redirect(f'Left alliance. Leadership transferred to {other.name}.')
        else:
            # Last member — disband
            nation.alliance_id = None
            db.session.delete(ally)
            db.session.commit()
            return _success_redirect('Alliance disbanded (you were the last member).')
    nation.alliance_id = None
    db.session.commit()
    return _success_redirect(f'Left "{ally.name}".')


@alliance.route('/alliance/disband', methods=['POST'])
@login_required
def disband_alliance():
    nation = current_user.nation
    if not nation or not nation.alliance_id:
        return _error_response('You are not in an alliance.')
    ally = db.session.get(Alliance, nation.alliance_id)
    if not ally:
        return _error_response('Alliance not found.')
    if ally.founder_id != nation.id:
        return _error_response('Only the founder can disband the alliance.')
    Nation.query.filter_by(alliance_id=ally.id).update({'alliance_id': None})
    AllianceApplication.query.filter_by(alliance_id=ally.id).delete()
    db.session.delete(ally)
    db.session.commit()
    return _success_redirect('Alliance disbanded.')


@alliance.route('/alliance/update-flag', methods=['POST'])
@login_required
def update_flag():
    nation = current_user.nation
    if not nation or not nation.alliance_id:
        return _error_response('You are not in an alliance.')
    ally = db.session.get(Alliance, nation.alliance_id)
    if not ally or ally.founder_id != nation.id:
        return _error_response('Only the founder can update the flag.')
    new_flag = request.form.get('new_flag', '').strip()
    path = new_flag.split('?')[0].split('#')[0].lower()
    if not new_flag or not any(path.endswith(ext) for ext in IMAGE_EXTS):
        return _error_response('Invalid flag URL. Must link to an image file.')
    ally.flag_url = new_flag
    db.session.commit()
    from flask import current_app
    resp = current_app.response_class(status=204)
    resp.headers['HX-Trigger'] = json.dumps(
        {'showMessage': {'message': 'Alliance flag updated.', 'type': 'success'}}
    )
    return resp


@alliance.route('/alliance/update-description', methods=['POST'])
@login_required
def update_description():
    nation = current_user.nation
    if not nation or not nation.alliance_id:
        return _error_response('You are not in an alliance.')
    ally = db.session.get(Alliance, nation.alliance_id)
    if not ally or ally.founder_id != nation.id:
        return _error_response('Only the founder can update the description.')
    new_desc = request.form.get('new_description', '').strip()
    if len(new_desc) > 5000:
        return _error_response('Description too long (max 5000 characters).')
    ally.description = new_desc
    db.session.commit()
    from flask import current_app
    resp = current_app.response_class(status=204)
    resp.headers['HX-Trigger'] = json.dumps(
        {'showMessage': {'message': 'Alliance description updated.', 'type': 'success'}}
    )
    return resp


@alliance.route('/alliance/search')
@login_required
def search_alliances():
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return jsonify([])
    results = (Alliance.query
               .filter(Alliance.name.ilike(f'%{q}%'))
               .order_by(Alliance.name)
               .limit(10).all())
    return jsonify([{'id': a.id, 'name': a.name} for a in results])
