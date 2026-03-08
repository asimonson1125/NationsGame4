from flask import Blueprint
economy = Blueprint('economy', __name__)
from . import routes  # noqa
