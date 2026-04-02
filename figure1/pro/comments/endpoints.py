import logging

from flask import Blueprint
from flask import request
from flask import abort
from flask.json import jsonify
from flask_jwt_extended import jwt_required
from jsonschema import ValidationError
from figure1.common.models.validator import Validate
from figure1.common.types import ReportReason
from figure1.core import managed_session
from .domain import get_all_comments
from .domain import get_one_comment
from .domain import do_post_comment
from .domain import do_report_comment
from .domain import do_delete_comment
from .domain import do_edit_comment
from .domain import do_translate_comment
from .domain import add_or_remove_accepted_answer
from figure1.exceptions import CommentError
from figure1.exceptions import InsufficientPermissions
from figure1.exceptions import AcceptedAnswerError

bp = Blueprint('pro_comment_endpoint', __name__)
logger = logging.getLogger('figure1.comments')


@managed_session
def resync_comment_with_mentions(comment_uuid, session=None):
    """
    Re-sync a comment to Firestore after mentions have been added.
    This ensures the mentions array is included in the Firestore document.
    """
    from figure1.common.models.db import Comment
    from figure1.events.comment_events import handle_comment_updated

    comment = session.query(Comment).get(comment_uuid)
    if comment:
        handle_comment_updated(comment=comment, session=session)
        logger.info(f"Re-synced comment {comment_uuid} to Firestore with mentions")
        return True
    else:
        logger.warning(f"Comment {comment_uuid} not found for re-sync")
        return False


@bp.app_errorhandler(CommentError)
def comment_error(e):
    logger.exception(e.msg)
    return jsonify(e.as_dict()), e.rc


@bp.errorhandler(InsufficientPermissions)
def insufficient_permissions(e):
    logger.exception(e.msg)
    return jsonify(e.as_dict()), e.rc


@bp.errorhandler(AcceptedAnswerError)
def insufficient_permissions(e):
    logger.exception(e.msg)
    return jsonify(e.as_dict()), e.rc


@bp.route('/comment/<content_uuid>', methods=["POST"])
@jwt_required()
def post_comment(content_uuid):
    """
    Post a comment to a content item
    ---
    tags:
     - comments
    produces:
      - application/json
    parameters:
      - name: content_uuid
        in: path
        required: true
      - name: body
        in: body
        required: true
        schema:
          properties:
            user_uid:
              type: string
              required: true
              description: The uid for the user submitting/deleting the comment
            comment_text:
              type: string
              description: comment text
            parent_comment_uuid:
              type: string
              description: The comment_uuid of the comment being replied to, may be empty

          example:
            user_uid: sOSe6ll4fUMPCMgRliuo4r3SoKC3
            comment_text: "Say something nice"
    responses:
      default:
        description: Unexpected Failure
      '200':
        description: OK
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    if request.json:
        post_body = request.json
        user_uid = post_body.get('user_uid')
        comment_text = post_body.get('comment_text')
        parent_comment_uuid = post_body.get('parent_comment_uuid')
        r = do_post_comment(user_uid=user_uid,
                            content_uuid=content_uuid,
                            comment_text=comment_text,
                            parent_comment_uuid=parent_comment_uuid)
        if 'error' in r:
            return jsonify(r), 500
        else:
            return jsonify(r), 200
    else:
        return jsonify({}), 422


@bp.route('/comment/translate/<comment_uuid>', methods=['POST'])
def translate_comment_endpoint(comment_uuid):
    """
    Translate a comment
    ---
    tags:
     - comments
    produces:
      - application/json
    parameters:
      - name: comment_uuid
        in: path
        required: true
      - name: body
        in: body
        required: true
        schema:
          properties:
            target_language:
              type: string
              description: The short code of the language to translate too
          example:
            target_language: "pt"
    responses:
      default:
        description: Unexpected Failure
      '200':
        description: OK
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    resp = do_translate_comment(comment_uuid=comment_uuid, target_language=request.json.get('target_language'))
    return jsonify(resp), 200


@bp.route('/comment/<comment_uuid>', methods=["put"])
@jwt_required()
def edit_comment(comment_uuid):
    """
    Edit a comment
    Only supported for cases which do not have the comment queue enabled.
    ---
    tags:
     - comments
    produces:
      - application/json
    parameters:
      - name: comment_uuid
        in: path
        required: true
      - name: body
        in: body
        required: true
        schema:
          properties:
            user_uid:
              type: string
              required: true
              description: The uid for the user submitting/deleting the comment
            comment_text:
              type: string
              description: comment text
          example:
            user_uid: uid
            comment_text: "Updated comment text"
    responses:
      default:
        description: Unexpected Failure
      '200':
        description: OK
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    body = request.json
    user_uid = body.get('user_uid', '')
    comment_text = body.get('comment_text', '')

    res = do_edit_comment(user_uid=user_uid,
                          comment_uuid=comment_uuid,
                          comment_text=comment_text)
    return jsonify(res)


@bp.route('/comment/<comment_uuid>/report', methods=["POST"])
@jwt_required()
def report_comment(comment_uuid):
    """
    Report a comment
    ---
    tags:
     - comments
    produces:
      - application/json
    parameters:
      - name: comment_uuid
        in: path
        required: true
      - name: body
        in: body
        required: true
        schema:
          properties:
            reporting_user_uid:
              type: string
              description: The reporting users uid
            report_reason:
              type: enum
              items: ['OTHER', 'DISRESPECTFUL', 'PRIVACY', 'LACK_EVIDENCE']
            text:
              type: string
              required: true
              description: Why the comment was reported

          example:
            reporting_user_uid: sOSe6ll4fUMPCMgRliuo4r3SoKC3
            text: "Say something nice"
            report_reason: 'OTHER'
    responses:
      default:
        description: Unexpected Failure
      '200':
        description: OK
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    v = Validate()
    try:
        v.validate(json_data=request.json, json_schema='comment_report')
    except ValidationError as ve:
        logging.error(f"Validation failed for comment report: {ve}")
        return abort(422, f'Invalid request body')

    post_body = request.json
    reporting_user_uid = post_body.get('reporting_user_uid')
    report_reason = post_body.get('report_reason')
    text = post_body.get('text')
    if hasattr(ReportReason, report_reason):
        report_reason = ReportReason[report_reason]
    else:
        report_reason = ReportReason.OTHER
    r = do_report_comment(reporting_user_uid=reporting_user_uid,
                          report_reason=report_reason,
                          text=text,
                          comment_uuid=comment_uuid)
    if 'error' in r:
        return jsonify(r), 500

    return jsonify(r), 200


@bp.route('/comment/<comment_uuid>', methods=["DELETE"])
@jwt_required()
def delete_comment(comment_uuid):
    """
    Delete a comment - the user_uid must match the user who created the comment
    ---
    tags:
     - comments
    produces:
      - application/json
    parameters:
      - name: comment_uuid
        in: path
        required: true
      - name: body
        in: body
        required: true
        schema:
          properties:
            user_uid:
              type: string
              required: true
              description: The user_uid of the user deleting the comment
          example:
            user_uid: sOSe6ll4fUMPCMgRliuo4r3SoKC3

    responses:
      default:
        description: Unexpected Failure
      '200':
        description: OK
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    r = do_delete_comment(comment_uuid=comment_uuid)
    if 'error' in r:
        return jsonify(r), 500
    else:
        return jsonify(r), 200


@bp.route('/comment/<comment_uuid>/comment', methods=["GET"])
@jwt_required()
def find_comment(comment_uuid):
    """
    Get a comment by comment_uuid
    ---
    tags:
     - comments
    produces:
      - application/json
    parameters:
      - name: comment_uuid
        in: path
        required: true

    responses:
      default:
        description: Unexpected Failure
      '200':
        description: OK
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    c = get_one_comment(comment_uuid=comment_uuid)
    if 'error' in c:
        return jsonify(c), 500
    return jsonify(c), 200


@bp.route('/comment/<content_uuid>/content', methods=["GET"])
@jwt_required()
def update_comment_tree_by_content(content_uuid):
    """
    Get the comment tree by content_uuid
    ---
    tags:
     - comments
    produces:
      - application/json
    parameters:
      - name: content_uuid
        in: path
        required: true
    responses:
      default:
        description: Unexpected Failure
      '200':
        description: OK
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    t = get_all_comments(content_uuid=content_uuid)
    return jsonify(t), 200


@bp.route('/comment/<case_uuid>/case', methods=["GET"])
@jwt_required()
def update_comment_tree_by_case(case_uuid):
    """
    Update comment tree in firestore by case_uuid
    ---
    tags:
     - comments
    produces:
      - application/json
    parameters:
      - name: case_uuid
        in: path
        required: true
    responses:
      default:
        description: Unexpected Failure
      '200':
        description: OK
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    return jsonify({}), 200


@bp.route('/comment/<comment_uuid>/accepted_answer', methods=['POST'])
def update_accepted_answer(comment_uuid):
    """
    Sets or remove a comment as the accepted answer.
    ---
    tags:
     - comments
    produces:
      - application/json
    parameters:
      - name: comment_uuid
        in: path
        required: true
      - name: body
        in: body
        required: true
        schema:
          properties:
            user_uid:
              type: string
              description: The uid of the user making the update
            is_accepted_answer:
              type: boolean
              required: true
              description: True if the comment is selected as accepted, false if it's removed
          example:
            user_uid: <user_uid>
            is_accepted_answer: true
    responses:
      default:
        description: Unexpected Failure
      '200':
        description: OK
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    if 'user_uid' not in request.json:
        return abort(422, 'missing user_uid')

    if 'is_accepted_answer' not in request.json:
        return abort(422, 'missing is_accepted_answer')

    user_uid = request.json.get('user_uid')
    is_accepted_answer = request.json.get('is_accepted_answer')

    res = add_or_remove_accepted_answer(is_accepted_answer=is_accepted_answer,
                                        comment_uuid=comment_uuid,
                                        user_uid=user_uid)

    return jsonify(res), 200


# ============================================================================
# MENTION-ENABLED ENDPOINTS
# ============================================================================
# NOTE: The following endpoints are temporary additions to support mentions functionality.
# These are extra steps due to lack of discovery around existing consumption by the frontend
# and to avoid breaking existing flows that don't include mentions.
#
# TODO: Once there is more time and confidence in frontend usage patterns, these should be
# deprecated and merged into the main endpoints above, OR the main endpoints should be
# updated to handle mentions if the field is present in the request.
# ============================================================================


@bp.route('/comment/<content_uuid>/with-mentions', methods=["POST"])
@jwt_required()
def post_comment_with_mentions(content_uuid):
    """
    Post a comment to a content item with user mentions
    ---
    tags:
     - mentions
    produces:
      - application/json
    parameters:
      - name: content_uuid
        in: path
        required: true
      - name: body
        in: body
        required: true
        schema:
          properties:
            user_uid:
              type: string
              required: true
              description: The uid for the user submitting the comment
            comment_text:
              type: string
              description: comment text
            parent_comment_uuid:
              type: string
              description: The comment_uuid of the comment being replied to, may be empty
            mentions:
              type: array
              description: Array of mentioned users
              items:
                type: object
                properties:
                  username:
                    type: string
                  userUuid:
                    type: string
                  userUid:
                    type: string
                  displayName:
                    type: string

          example:
            user_uid: sOSe6ll4fUMPCMgRliuo4r3SoKC3
            comment_text: "Great case @john_doe!"
            mentions:
              - username: "john_doe"
                userUuid: "abc-123-def-456"
                userUid: "xyz789"
                displayName: "John Doe"
    responses:
      default:
        description: Unexpected Failure
      '200':
        description: OK
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    if request.json:
        post_body = request.json
        user_uid = post_body.get('user_uid')
        comment_text = post_body.get('comment_text')
        parent_comment_uuid = post_body.get('parent_comment_uuid')
        mentions = post_body.get('mentions', [])

        logger.info(f"Creating comment with {len(mentions)} mentions")

        # Create the comment first
        r = do_post_comment(user_uid=user_uid,
                            content_uuid=content_uuid,
                            comment_text=comment_text,
                            parent_comment_uuid=parent_comment_uuid)

        if 'error' in r:
            return jsonify(r), 500

        # Process and store mentions if comment was created successfully
        if mentions and 'uuid' in r:
            try:
                from figure1.pro.mentions.domain import process_and_store_mentions

                comment_uuid = r['uuid']
                mention_uuids = process_and_store_mentions(
                    mentions=mentions,
                    text=comment_text,
                    mentioning_user_uid=user_uid,
                    comment_uuid=comment_uuid,
                    content_uuid=content_uuid,
                    case_uuid=None  # Comments don't directly link to cases
                )

                # Add mention info to response
                r['mentions_created'] = len(mention_uuids)
                r['mention_uuids'] = mention_uuids

                logger.info(f"Stored {len(mention_uuids)} mentions for comment {comment_uuid}")

                # Re-sync comment to Firestore to include mentions
                try:
                    resync_comment_with_mentions(comment_uuid=comment_uuid)
                except Exception as sync_error:
                    logger.exception(f"Failed to re-sync comment to Firestore: {sync_error}")
                    # Don't fail the request if re-sync fails

                # TODO: Trigger notification system for each mention
                # This should send notifications to mentioned users

            except Exception as e:
                logger.exception(f"Error processing mentions for comment: {e}")
                # Don't fail the whole request if mention processing fails
                r['mention_error'] = str(e)
                r['mentions_created'] = 0

        return jsonify(r), 200
    else:
        return jsonify({}), 422


@bp.route('/comment/<comment_uuid>/with-mentions', methods=["PUT"])
@jwt_required()
def edit_comment_with_mentions(comment_uuid):
    """
    Edit a comment with user mentions
    Only supported for cases which do not have the comment queue enabled.
    ---
    tags:
     - mentions
    produces:
      - application/json
    parameters:
      - name: comment_uuid
        in: path
        required: true
      - name: body
        in: body
        required: true
        schema:
          properties:
            user_uid:
              type: string
              required: true
              description: The uid for the user submitting/deleting the comment
            comment_text:
              type: string
              description: comment text
            mentions:
              type: array
              description: Array of mentioned users
              items:
                type: object
                properties:
                  username:
                    type: string
                  userUuid:
                    type: string
                  userUid:
                    type: string
                  displayName:
                    type: string
          example:
            user_uid: uid
            comment_text: "Updated comment with @jane_doe"
            mentions:
              - username: "jane_doe"
                userUuid: "def-456-ghi-789"
                userUid: "abc123"
                displayName: "Jane Doe"
    responses:
      default:
        description: Unexpected Failure
      '200':
        description: OK
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    body = request.json
    user_uid = body.get('user_uid', '')
    comment_text = body.get('comment_text', '')
    mentions = body.get('mentions', [])

    logger.info(f"Editing comment with {len(mentions)} mentions")

    # Edit the comment first
    res = do_edit_comment(user_uid=user_uid,
                          comment_uuid=comment_uuid,
                          comment_text=comment_text)

    if 'error' not in res and mentions:
        try:
            from figure1.pro.mentions.domain import process_and_store_mentions
            from figure1.common.models.db import Mention, Comment
            from figure1.core import managed_session

            # Delete existing mentions for this comment
            # (editing replaces mentions, doesn't append)
            with managed_session() as session:
                session.query(Mention).filter(
                    Mention.comment_uuid == comment_uuid
                ).delete()
                session.commit()

            # Get content_uuid from the comment
            content_uuid = None
            with managed_session() as session:
                comment = session.query(Comment).get(comment_uuid)
                if comment:
                    content_uuid = comment.content_uuid

            # Create new mentions based on edited text
            mention_uuids = process_and_store_mentions(
                mentions=mentions,
                text=comment_text,
                mentioning_user_uid=user_uid,
                comment_uuid=comment_uuid,
                content_uuid=content_uuid,
                case_uuid=None
            )

            res['mentions_updated'] = len(mention_uuids)
            res['mention_uuids'] = mention_uuids

            logger.info(f"Updated mentions for comment {comment_uuid}: {len(mention_uuids)} mentions")

            # TODO: Trigger notification system for newly mentioned users
            # Should notify users who are newly mentioned but not users whose mentions were removed

        except Exception as e:
            logger.exception(f"Error processing mentions for comment edit: {e}")
            res['mention_error'] = str(e)
            res['mentions_updated'] = 0

    return jsonify(res)
