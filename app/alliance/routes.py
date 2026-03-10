import json
from flask import render_template, request, redirect, url_for, jsonify
from flask_login import login_required, current_user
from .. import db
from ..models import Alliance, Nation
from ..helpers import error_response as _error_response
from . import alliance


IMAGE_EXTS = ('.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', '.svg',
              '.tiff', '.tif', '.ico', '.avif', '.apng', '.jfif')


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
    return render_template('alliance/alliance_view.html',
                           alliance=ally, members=members,
                           total_gp=total_gp, is_founder=is_founder,
                           is_member=is_member, nation=nation)


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


@alliance.route('/alliance/join', methods=['POST'])
@login_required
def join_alliance():
    nation = current_user.nation
    if not nation:
        return _error_response('No nation found.')
    if nation.alliance_id:
        return _error_response('You are already in an alliance.')
    alliance_id = request.form.get('alliance_id', type=int)
    if not alliance_id:
        return _error_response('Please select an alliance to join.')
    ally = db.session.get(Alliance, alliance_id)
    if not ally:
        return _error_response('Alliance not found.')
    nation.alliance_id = ally.id
    db.session.commit()
    return _success_redirect(f'Joined "{ally.name}"!')


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
