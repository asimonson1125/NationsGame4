from flask import Blueprint
military = Blueprint('military', __name__)
from . import routes  # noqa
