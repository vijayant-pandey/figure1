import logging

from elasticsearch.exceptions import NotFoundError as ElasticSearchNotFound
from flask import Blueprint
from flask.json import jsonify
from pydantic import EmailError
from pydantic import ValidationError
from sqlalchemy.exc import DatabaseError

from figure1.exceptions import CaseNotFound
from figure1.exceptions import CommentNotFound
from figure1.exceptions import ContentNotFound
from figure1.exceptions import DuplicateUser
from figure1.exceptions import FoundNotAllowedWord
from figure1.exceptions import UserNotFound
from .lock import TooManyRequests
from .user import UserDeleted

logger = logging.getLogger(__name__)
bp = Blueprint('general_exceptions', __name__)

"""
Exceptions placed here should be relevant across multiple packages. Exceptions that are specific to the package
they are raised in should be maintained there.
For example - Feed exceptions are handled within the feed package while a user not being found is relevant across
many packages.
"""


@bp.app_errorhandler(FoundNotAllowedWord)
def word_not_allowed(e):
    logger.exception("Word not allowed")
    return jsonify(dict=e.as_dict()), e.rc


@bp.app_errorhandler(ElasticSearchNotFound)
def elasticsearch_not_found(e):
    logger.exception("Elasticsearch Not Found")
    return jsonify(str(e)), e.status_code


@bp.app_errorhandler(UserNotFound)
def user_not_found(e):
    logger.exception("%s", e.msg)
    return jsonify(e.as_dict()), e.rc


@bp.app_errorhandler(UserDeleted)
def user_deleted(e):
    logger.exception("%s", e.msg)
    return jsonify(e.as_dict()), e.rc


@bp.app_errorhandler(DuplicateUser)
def user_duplicated(e):
    logger.exception("%s", e.msg)
    return jsonify(e.as_dict(), e.rc)


@bp.app_errorhandler(DatabaseError)
def user_database_error(e):
    logger.exception("Database error")
    return jsonify({"message": "Database Error",
                    "params": e.params,
                    "statement": e.statement,
                    "postgres_error": str(e.orig.pgerror)}), 500


@bp.app_errorhandler(ValidationError)
def generic_validation_error(e):
    logger.exception("Model validation failed")
    return e.json(), 422


@bp.app_errorhandler(CaseNotFound)
def case_not_found(e):
    logger.exception("Case Not Found")
    return jsonify(e.as_dict()), e.rc


@bp.app_errorhandler(ContentNotFound)
def content_not_found(e):
    logger.exception("Content Not Found")
    return jsonify(e.as_dict()), e.rc


@bp.app_errorhandler(CommentNotFound)
def comment_not_found(e):
    logger.exception("Comment Not Found")
    return jsonify(e.as_dict()), e.rc


@bp.app_errorhandler(TooManyRequests)
def too_many_requests_ex(e):
    logger.exception("Too many requests")
    resp = jsonify(e.as_dict())
    if e.retry_after:
        resp.retry_after = e.retry_after
    return resp, e.return_code


@bp.app_errorhandler(EmailError)
def handle_email_validation_error(e):
    logger.exception("%s", e)
    return jsonify({'msg': 'Invalid Email'}), 422
