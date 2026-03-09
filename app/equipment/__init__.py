from flask import Blueprint
equipment = Blueprint('equipment', __name__)
from . import routes  # noqa
