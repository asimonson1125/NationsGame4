import logging
from flask import render_template
from flask_mail import Message
from . import mailer

logger = logging.getLogger(__name__)


def _send(subject, recipients, html_template, txt_template, **kwargs):
    """Render and send an email; log but do not raise on failure."""
    try:
        msg = Message(
            subject=subject,
            recipients=recipients,
            html=render_template(html_template, **kwargs),
            body=render_template(txt_template, **kwargs),
        )
        mailer.send(msg)
    except Exception:
        logger.exception("Failed to send email to %s (subject: %s)", recipients, subject)


def send_verification_email(user, link):
    _send(
        subject='Verify your Nations Engine email',
        recipients=[user.email],
        html_template='email/verify_email.html',
        txt_template='email/verify_email.txt',
        user=user,
        link=link,
        expires_in='72 hours',
    )


def send_password_reset_email(user, link):
    _send(
        subject='Reset your Nations Engine password',
        recipients=[user.email],
        html_template='email/reset_password.html',
        txt_template='email/reset_password.txt',
        user=user,
        link=link,
        expires_in='1 hour',
    )


def send_email_change_email(user, new_email, link):
    _send(
        subject='Confirm your new Nations Engine email address',
        recipients=[new_email],
        html_template='email/email_change.html',
        txt_template='email/email_change.txt',
        user=user,
        link=link,
        expires_in='24 hours',
    )
