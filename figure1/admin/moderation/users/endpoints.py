from flask import Blueprint, request, abort
from flask.json import jsonify
from flask_jwt_extended import jwt_required

bp = Blueprint('moderation_users', __name__)


@bp.route('/moderation/user/create', methods=['POST'])
def create_moderation_user():
    pass


def update_user_type():
    pass
