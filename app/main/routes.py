import json
from flask import render_template, url_for, request, current_app
from flask_login import login_required, current_user
from .. import db
from . import main


@main.route('/')
@login_required
def home():
    return render_template('main/home.html', nation=current_user.nation)


@main.route('/gp-breakdown')
@login_required
def gp_breakdown():
    return render_template('main/partials/gp_breakdown.html', nation=current_user.nation)


@main.route('/resource-footer')
@login_required
def resource_footer():
    from ..game.factories import FACTORY_DEFS
    nation = current_user.nation
    net_income = {}
    if nation:
        for nf in nation.factories:
            fdef = FACTORY_DEFS.get(nf.factory_key)
            if fdef and nf.count > 0:
                for res, rate in fdef.inputs.items():
                    net_income[res] = net_income.get(res, 0) - rate * nf.count
                for res, rate in fdef.outputs.items():
                    net_income[res] = net_income.get(res, 0) + rate * nf.count
    return render_template('main/partials/resource_footer.html', nation=nation, net_income=net_income)


@main.route('/update-flag', methods=['POST'])
@login_required
def update_flag():
    new_flag = request.form.get('new_flag', '').strip()
    allowed = ('.jpg', '.jpeg', '.png', '.webp', '.gif')
    if not new_flag or not any(new_flag.lower().endswith(ext) for ext in allowed):
        resp = current_app.response_class(status=422)
        resp.headers['HX-Trigger'] = json.dumps(
            {'showMessage': {'message': 'Invalid flag URL. Must end with .jpg, .jpeg, .png, or .webp.', 'type': 'error'}}
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
        resp = current_app.response_class(status=422)
        resp.headers['HX-Trigger'] = json.dumps(
            {'showMessage': {'message': 'Description too long (max 5000 characters).', 'type': 'error'}}
        )
        return resp
    current_user.nation.description = new_desc
    db.session.commit()
    resp = current_app.response_class(status=204)
    resp.headers['HX-Trigger'] = json.dumps(
        {'showMessage': {'message': 'Description updated.', 'type': 'success'}}
    )
    return resp
