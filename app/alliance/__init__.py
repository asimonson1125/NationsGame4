from flask import Blueprint
alliance = Blueprint('alliance', __name__)
from . import routes  # noqa
