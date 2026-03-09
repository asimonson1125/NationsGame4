from flask import Blueprint
trade = Blueprint('trade', __name__)
from . import routes  # noqa
