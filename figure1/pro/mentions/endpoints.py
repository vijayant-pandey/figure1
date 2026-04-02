"""
API endpoints for mention functionality and testing.
"""
import logging
from datetime import datetime
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from figure1.common.models.db import Mention, User
from figure1.core import managed_session

bp = Blueprint('pro_mention_endpoint', __name__)
logger = logging.getLogger('figure1.mentions')


class MentionError(Exception):
    """Custom exception for mention-related errors"""
    def __init__(self, msg, rc=400):
        self.msg = msg
        self.rc = rc

    def as_dict(self):
        return {'error': self.msg}


@bp.app_errorhandler(MentionError)
def mention_error(e):
    logger.exception(e.msg)
    return jsonify(e.as_dict()), e.rc


# ============================================================================
# TESTING ENDPOINTS (for Phase 2 & 3 testing)
# ============================================================================

@bp.route('/test/mentions/create', methods=['POST'])
def test_create_mention():
    """
    TEST ENDPOINT: Create a mention through SQLAlchemy (triggers events)
    ---
    tags:
      - mentions
      - testing
    summary: Create a test mention
    description: |
      Creates a mention through SQLAlchemy ORM which properly triggers events and syncs to Firestore.

      ⚠️ Direct SQL inserts bypass SQLAlchemy events and won't sync to Firestore!

      Send empty body {} to auto-select two users, or provide specific UUIDs.
    produces:
      - application/json
    parameters:
      - name: body
        in: body
        required: false
        schema:
          type: object
          properties:
            mentioned_user_uuid:
              type: string
              description: UUID of user being mentioned (optional - auto-selected if omitted)
            mentioning_user_uuid:
              type: string
              description: UUID of user creating the mention (optional - auto-selected if omitted)
            comment_uuid:
              type: string
              description: UUID of comment containing the mention (optional)
            case_uuid:
              type: string
              description: UUID of case containing the mention (optional)
          example:
            mentioned_user_uuid: ""
            mentioning_user_uuid: ""
    responses:
      201:
        description: Mention created successfully
        schema:
          type: object
          properties:
            success:
              type: boolean
            mention_uuid:
              type: string
            mentioned_user:
              type: object
            mentioning_user:
              type: object
            message:
              type: string
      400:
        description: Invalid request or not enough users in database
      500:
        description: Server error
    """
    try:
        data = request.get_json() or {}

        with managed_session() as session:
            # If UUIDs not provided, auto-select two users
            if not data.get('mentioned_user_uuid') or not data.get('mentioning_user_uuid'):
                users = session.query(User).filter(User.user_uid.isnot(None)).limit(2).all()

                if len(users) < 2:
                    return jsonify({
                        'error': 'Need at least 2 users with user_uid in database'
                    }), 400

                mentioned_user = users[0]
                mentioning_user = users[1]
            else:
                mentioned_user = session.query(User).get(data['mentioned_user_uuid'])
                mentioning_user = session.query(User).get(data['mentioning_user_uuid'])

                if not mentioned_user or not mentioning_user:
                    return jsonify({'error': 'User(s) not found'}), 404

            # Create mention through SQLAlchemy (triggers events!)
            mention = Mention(
                mentioned_user_uuid=mentioned_user.user_uuid,
                mentioning_user_uuid=mentioning_user.user_uuid,
                comment_uuid=data.get('comment_uuid'),
                case_uuid=data.get('case_uuid'),
                position=0,
                is_read=False,
                created_at=datetime.utcnow()
            )

            session.add(mention)
            session.commit()  # This triggers the after_insert event!

            logger.info(f"Test mention created: {mention.mention_uuid}")

            return jsonify({
                'success': True,
                'mention_uuid': str(mention.mention_uuid),
                'mentioned_user': {
                    'uuid': str(mentioned_user.user_uuid),
                    'uid': mentioned_user.user_uid,
                    'username': mentioned_user.username
                },
                'mentioning_user': {
                    'uuid': str(mentioning_user.user_uuid),
                    'uid': mentioning_user.user_uid,
                    'username': mentioning_user.username
                },
                'message': 'Mention created! Check Celery logs for sync task.'
            }), 201

    except Exception as e:
        logger.exception("Error creating test mention")
        return jsonify({'error': str(e)}), 500


@bp.route('/test/mentions/<mention_uuid>/mark-read', methods=['POST'])
def test_mark_mention_read(mention_uuid):
    """
    TEST ENDPOINT: Mark a mention as read (triggers update event)
    ---
    tags:
      - mentions
      - testing
    summary: Mark mention as read
    description: Updates mention.is_read to true, triggers SQLAlchemy event, and syncs to Firestore
    produces:
      - application/json
    parameters:
      - name: mention_uuid
        in: path
        required: true
        type: string
        description: UUID of the mention to mark as read
    responses:
      200:
        description: Mention marked as read successfully
        schema:
          type: object
          properties:
            success:
              type: boolean
            mention_uuid:
              type: string
            is_read:
              type: boolean
            read_at:
              type: string
            message:
              type: string
      404:
        description: Mention not found
      500:
        description: Server error
    """
    try:
        with managed_session() as session:
            mention = session.query(Mention).get(mention_uuid)

            if not mention:
                return jsonify({'error': 'Mention not found'}), 404

            # Update through SQLAlchemy (triggers event!)
            mention.is_read = True
            mention.read_at = datetime.utcnow()
            mention.updated_at = datetime.utcnow()

            session.commit()  # This triggers the is_read event!

            logger.info(f"Test mention marked as read: {mention_uuid}")

            return jsonify({
                'success': True,
                'mention_uuid': str(mention.mention_uuid),
                'is_read': mention.is_read,
                'read_at': mention.read_at.isoformat() if mention.read_at else None,
                'message': 'Mention marked as read! Check Celery logs for sync task.'
            }), 200

    except Exception as e:
        logger.exception("Error marking mention as read")
        return jsonify({'error': str(e)}), 500


@bp.route('/test/mentions/<mention_uuid>', methods=['DELETE'])
def test_delete_mention(mention_uuid):
    """
    TEST ENDPOINT: Delete a mention (triggers delete event)
    ---
    tags:
      - mentions
      - testing
    summary: Delete a mention
    description: Deletes mention through SQLAlchemy ORM, triggers after_delete event, and removes from Firestore
    produces:
      - application/json
    parameters:
      - name: mention_uuid
        in: path
        required: true
        type: string
        description: UUID of the mention to delete
    responses:
      200:
        description: Mention deleted successfully
        schema:
          type: object
          properties:
            success:
              type: boolean
            mention_uuid:
              type: string
            message:
              type: string
      404:
        description: Mention not found
      500:
        description: Server error
    """
    try:
        with managed_session() as session:
            mention = session.query(Mention).get(mention_uuid)

            if not mention:
                return jsonify({'error': 'Mention not found'}), 404

            # Delete through SQLAlchemy (triggers event!)
            session.delete(mention)
            session.commit()  # This triggers the after_delete event!

            logger.info(f"Test mention deleted: {mention_uuid}")

            return jsonify({
                'success': True,
                'mention_uuid': str(mention_uuid),
                'message': 'Mention deleted! Check Celery logs for delete task.'
            }), 200

    except Exception as e:
        logger.exception("Error deleting mention")
        return jsonify({'error': str(e)}), 500


@bp.route('/test/mentions', methods=['GET'])
def test_list_mentions():
    """
    TEST ENDPOINT: List all mentions (for debugging)
    ---
    tags:
      - mentions
      - testing
    summary: List mentions
    description: List mentions with optional filtering by user and limit
    produces:
      - application/json
    parameters:
      - name: user_uuid
        in: query
        required: false
        type: string
        description: Filter by mentioned user UUID
      - name: limit
        in: query
        required: false
        type: integer
        default: 10
        description: Maximum number of results to return
    responses:
      200:
        description: List of mentions
        schema:
          type: object
          properties:
            count:
              type: integer
            mentions:
              type: array
              items:
                type: object
                properties:
                  mention_uuid:
                    type: string
                  mentioned_user_uuid:
                    type: string
                  mentioning_user_uuid:
                    type: string
                  is_read:
                    type: boolean
                  created_at:
                    type: string
      500:
        description: Server error
    """
    try:
        user_uuid = request.args.get('user_uuid')
        limit = int(request.args.get('limit', 10))

        with managed_session() as session:
            query = session.query(Mention)

            if user_uuid:
                query = query.filter(Mention.mentioned_user_uuid == user_uuid)

            query = query.order_by(Mention.created_at.desc()).limit(limit)
            mentions = query.all()

            return jsonify({
                'count': len(mentions),
                'mentions': [{
                    'mention_uuid': str(m.mention_uuid),
                    'mentioned_user_uuid': str(m.mentioned_user_uuid),
                    'mentioning_user_uuid': str(m.mentioning_user_uuid),
                    'is_read': m.is_read,
                    'created_at': m.created_at.isoformat() if m.created_at else None
                } for m in mentions]
            }), 200

    except Exception as e:
        logger.exception("Error listing mentions")
        return jsonify({'error': str(e)}), 500


# ============================================================================
# PRODUCTION ENDPOINTS (Phase 4 implementation)
# ============================================================================

@bp.route('/mentions', methods=['GET'])
@jwt_required()
def get_user_mentions():
    """
    Get mentions for the authenticated user
    ---
    tags:
      - mentions
    summary: Get user mentions
    description: Retrieve mentions for the authenticated user with optional filtering
    produces:
      - application/json
    parameters:
      - name: unread
        in: query
        required: false
        type: boolean
        description: Filter by unread mentions only (true/false)
      - name: limit
        in: query
        required: false
        type: integer
        default: 50
        description: Maximum number of results (max 100)
      - name: offset
        in: query
        required: false
        type: integer
        default: 0
        description: Pagination offset
    responses:
      200:
        description: List of mentions
        schema:
          type: object
          properties:
            total:
              type: integer
            limit:
              type: integer
            offset:
              type: integer
            mentions:
              type: array
              items:
                type: object
      404:
        description: User not found
      500:
        description: Server error
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    try:
        user_uid = get_jwt_identity()
        unread_only = request.args.get('unread', '').lower() == 'true'
        limit = min(int(request.args.get('limit', 50)), 100)
        offset = int(request.args.get('offset', 0))

        with managed_session() as session:
            # Get user by uid
            user = session.query(User).filter(User.user_uid == user_uid).first()
            if not user:
                return jsonify({'error': 'User not found'}), 404

            # Build query
            query = session.query(Mention).filter(
                Mention.mentioned_user_uuid == user.user_uuid
            )

            if unread_only:
                query = query.filter(Mention.is_read == False)

            # Get total count
            total = query.count()

            # Apply pagination
            query = query.order_by(Mention.created_at.desc())
            query = query.limit(limit).offset(offset)

            mentions = query.all()

            return jsonify({
                'total': total,
                'limit': limit,
                'offset': offset,
                'mentions': [{
                    'mention_uuid': str(m.mention_uuid),
                    'mentioning_user': {
                        'uuid': str(m.mentioning_user_uuid),
                        'username': m.mentioning_user.username if m.mentioning_user else None
                    },
                    'case_uuid': str(m.case_uuid) if m.case_uuid else None,
                    'comment_uuid': str(m.comment_uuid) if m.comment_uuid else None,
                    'is_read': m.is_read,
                    'created_at': m.created_at.isoformat() if m.created_at else None
                } for m in mentions]
            }), 200

    except Exception as e:
        logger.exception("Error fetching user mentions")
        return jsonify({'error': str(e)}), 500


@bp.route('/mentions/<mention_uuid>/read', methods=['POST'])
@jwt_required()
def mark_mention_read(mention_uuid):
    """
    Mark a mention as read
    ---
    tags:
      - mentions
    summary: Mark mention as read
    description: Mark a specific mention as read for the authenticated user
    produces:
      - application/json
    parameters:
      - name: mention_uuid
        in: path
        required: true
        type: string
        description: UUID of the mention to mark as read
    responses:
      200:
        description: Mention marked as read
        schema:
          type: object
          properties:
            success:
              type: boolean
            mention_uuid:
              type: string
            is_read:
              type: boolean
      403:
        description: Unauthorized - mention belongs to different user
      404:
        description: Mention or user not found
      500:
        description: Server error
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    try:
        user_uid = get_jwt_identity()

        with managed_session() as session:
            # Get user
            user = session.query(User).filter(User.user_uid == user_uid).first()
            if not user:
                return jsonify({'error': 'User not found'}), 404

            # Get mention
            mention = session.query(Mention).get(mention_uuid)
            if not mention:
                return jsonify({'error': 'Mention not found'}), 404

            # Verify this mention belongs to the user
            if mention.mentioned_user_uuid != user.user_uuid:
                return jsonify({'error': 'Unauthorized'}), 403

            # Mark as read
            mention.is_read = True
            mention.read_at = datetime.utcnow()
            mention.updated_at = datetime.utcnow()

            session.commit()

            return jsonify({
                'success': True,
                'mention_uuid': str(mention.mention_uuid),
                'is_read': True
            }), 200

    except Exception as e:
        logger.exception("Error marking mention as read")
        return jsonify({'error': str(e)}), 500


# ============================================================================
# NOTE: User search for @mention autocomplete
# ============================================================================
# User search is handled by the existing endpoint:
#   POST /pro/v1/search/users
#
# This endpoint is already implemented in services_v2/figure1/pro/search/
# and is used throughout the application.
#
# Frontend integration:
#   - admin_v2: searchUsersCall() in src/api/cloud-functions.js
#   - functions_v2: backendSearchUsers in backend/search/users.function.js
#
# Do NOT create a separate /mentions/search-users endpoint.
# This avoids code duplication and maintains consistency across the app.
