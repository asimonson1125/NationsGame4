import json
from flask import render_template, request, current_app, jsonify
from flask_login import login_required, current_user
from markupsafe import escape
from .. import db
from ..models import Message, Nation
from ..helpers import error_response
from . import mail


@mail.route('/mail')
@login_required
def inbox():
    nation = current_user.nation
    tab = request.args.get('tab', 'notifications')
    return render_template('mail/inbox.html', nation=nation, active_tab=tab)


@mail.route('/mail/messages')
@login_required
def message_list():
    nation = current_user.nation
    tab = request.args.get('tab', 'notifications')

    if tab == 'notifications':
        messages = Message.query.filter_by(
            recipient_id=nation.id, message_type='system'
        ).order_by(Message.created_at.desc()).limit(50).all()
    elif tab == 'inbox':
        messages = Message.query.filter_by(
            recipient_id=nation.id, message_type='player'
        ).order_by(Message.created_at.desc()).limit(50).all()
    elif tab == 'sent':
        messages = Message.query.filter_by(
            sender_id=nation.id, message_type='player'
        ).order_by(Message.created_at.desc()).limit(50).all()
    else:
        messages = []

    return render_template(
        'mail/partials/message_list.html',
        messages=messages,
        tab=tab,
    )


@mail.route('/mail/read/<int:message_id>')
@login_required
def read_message(message_id):
    nation = current_user.nation
    msg = db.session.get(Message, message_id)

    if not msg:
        return error_response('Message not found.')
    # Allow reading if you're the recipient or the sender
    if msg.recipient_id != nation.id and msg.sender_id != nation.id:
        return error_response('Message not found.')

    if msg.recipient_id == nation.id and not msg.is_read:
        msg.is_read = True
        db.session.commit()

    return render_template('mail/message.html', nation=nation, msg=msg)


@mail.route('/mail/compose')
@login_required
def compose():
    nation = current_user.nation
    to_nation_id = request.args.get('to', type=int)
    reply_subject = request.args.get('subject', '')
    to_nation = None
    if to_nation_id:
        to_nation = db.session.get(Nation, to_nation_id)
    return render_template(
        'mail/compose.html',
        nation=nation,
        to_nation=to_nation,
        reply_subject=reply_subject,
    )


@mail.route('/mail/send', methods=['POST'])
@login_required
def send_message():
    nation = current_user.nation

    recipient_name = request.form.get('recipient', '').strip()
    subject = request.form.get('subject', '').strip()
    body = request.form.get('body', '').strip()

    if not recipient_name:
        return error_response('Recipient is required.')
    if not subject:
        return error_response('Subject is required.')
    if not body:
        return error_response('Message body is required.')
    if len(subject) > 200:
        return error_response('Subject must be 200 characters or less.')
    if len(body) > 5000:
        return error_response('Message body must be 5000 characters or less.')

    recipient = Nation.query.filter(
        db.func.lower(Nation.name) == recipient_name.lower()
    ).first()
    if not recipient:
        return error_response(f'Nation "{escape(recipient_name)}" not found.')
    if recipient.id == nation.id:
        return error_response('You cannot send a message to yourself.')

    msg = Message(
        sender_id=nation.id,
        recipient_id=recipient.id,
        subject=subject,
        body=body,
        message_type='player',
    )
    db.session.add(msg)
    db.session.commit()

    resp = current_app.response_class('', status=200)
    resp.headers['HX-Trigger'] = json.dumps({
        'showMessage': {'message': f'Message sent to {recipient.name}.', 'type': 'success'},
    })
    resp.headers['HX-Redirect'] = '/mail?tab=sent'
    return resp


@mail.route('/mail/delete/<int:message_id>', methods=['POST'])
@login_required
def delete_message(message_id):
    nation = current_user.nation
    msg = db.session.get(Message, message_id)

    if not msg:
        return error_response('Message not found.')
    if msg.recipient_id != nation.id:
        return error_response('Message not found.')

    db.session.delete(msg)
    db.session.commit()

    resp = current_app.response_class('', status=200)
    resp.headers['HX-Trigger'] = json.dumps({
        'showMessage': {'message': 'Message deleted.', 'type': 'success'},
    })
    resp.headers['HX-Redirect'] = '/mail'
    return resp


@mail.route('/mail/unread-count')
@login_required
def unread_count():
    nation = current_user.nation
    count = Message.query.filter_by(
        recipient_id=nation.id, is_read=False
    ).count()
    return jsonify({'count': count})


@mail.route('/mail/search-nations')
@login_required
def search_nations():
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return jsonify([])
    from ..helpers import nation_search_query
    nations = nation_search_query(q, exclude_id=current_user.nation.id).limit(10).all()
    return jsonify([{'id': n.id, 'name': n.name} for n in nations])
