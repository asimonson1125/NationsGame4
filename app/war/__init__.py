from flask import Blueprint

war = Blueprint('war', __name__)

from . import routes  # noqa: F401, E402
