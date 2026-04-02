from flask import Blueprint, request, abort, make_response
from flask.json import jsonify
from flask_jwt_extended import jwt_required
from figure1.common.firebase import do_firebase_sync
from figure1.common.types import FirebaseAction
from figure1.common.types.case import Reaction, ContentUpdateType
from figure1.common.utils import execute_on_return
from figure1.exceptions import InsufficientPermissions
from figure1.pro.cases.domain import submit_case_reaction, save_case, report_case, \
    submit_case_update, delete_case, get_case, update_content_position, check_missing_media, \
    do_translate_case
from figure1.common.types import CMEContentPositionModel
from figure1.common.models.db.c_case_model import Case
from figure1.core.db import global_session

bp = Blueprint('pro_case_endpoint', __name__)


@bp.errorhandler(InsufficientPermissions)
def insufficient_permissions(e):
    return jsonify(e.as_dict()), e.rc


@bp.route('/case/<case_uuid>', methods=["GET"])
@jwt_required()
def get_case_by_uuid(case_uuid):
    """
    Get a case and push it to Firestore
    ---
    tags:
     - cases
    produces:
      - application/json
    parameters:
      - name: case_uuid
        in: path
        type: string
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
    res = get_case(case_uuid, return_task=True)

    task = res.pop('task')
    return execute_on_return(task, synchronous=True, response=res)


@bp.route('/case/<case_uuid>/action', methods=["POST"])
@jwt_required()
def case_action(case_uuid):
    """
    Perform an action on a case (save/unsave, report)
    Supported actions:  'save', 'unsave', 'report'
    ---
    tags:
     - cases
    produces:
      - application/json
    parameters:
      - name: case_uuid
        in: path
        type: string
        required: true
      - name: force_synchronous
        in: query
        type: bool
        required: false
        description: Forces the return to be synchronous
      - name: body
        in: body
        required: true
        schema:
          properties:
            user_uid:
              type: string
              description: The uid for the user submitting the action
            action:
              type: string
              enum: ['save', 'unsave', 'report']
            value:
              type: string
              description: Additional action info, used bu some actions
          example:
            user_uid: sOSe6ll4fUMPCMgRliuo4r3SoKC3
            action: save
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
        return abort(400, 'missing user_uid')
    if 'action' not in request.json:
        return abort(400, 'missing reaction')

    user_uid = request.json.get('user_uid')
    action = request.json.get('action').lower()

    force_synchronous = request.args.get("force_synchronous")
    if force_synchronous == 'true':
        force_synchronous = True
    else:
        force_synchronous = False
    if action == 'save':
        res = save_case(user_uid=user_uid, case_uuid=case_uuid, save_state=True)
    elif action == 'unsave':
        res = save_case(user_uid=user_uid, case_uuid=case_uuid, save_state=False)
    elif action == 'report':
        value = request.json.get('value')
        res = report_case(user_uid=user_uid, case_uuid=case_uuid, report_text=value)
    else:
        return abort(400, 'Unsupported action')
    task = res.pop("task")
    return execute_on_return(task, synchronous=force_synchronous, response=res)


@bp.route('/case/<case_uuid>/reaction', methods=["POST"])
@jwt_required()
def case_reaction(case_uuid):
    """
    Add a reaction for a case
    Supported reactions:  'clinicallyUseful', 'agree', 'informative'
    ---
    tags:
     - cases
    produces:
      - application/json
    parameters:
      - name: case_uuid
        in: path
        type: string
        required: true
      - name: force_synchronous
        in: query
        type: bool
        required: false
        description: Forces the return to be synchronous
      - name: body
        in: body
        required: true
        schema:
          properties:
            user_uid:
              type: string
              description: The uid for the user submitting the reaction
            reaction:
              type: string
              enum: ['clinicallyUseful', 'agree', 'informative']
            value:
              type: boolean
          example:
            user_uid: sOSe6ll4fUMPCMgRliuo4r3SoKC3
            reaction: agree
            value: true
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
        return abort(400, 'missing user_uid')
    if 'reaction' not in request.json:
        return abort(400, 'missing reaction')
    if 'value' not in request.json:
        return abort(400, 'missing value')

    user_uid = request.json.get('user_uid')
    reaction = request.json.get('reaction').upper()
    value = request.json.get('value')

    if reaction not in [r.name for r in Reaction]:
        return abort(400, f'Reaction {reaction} is not supported')
    force_synchronous = request.args.get("force_synchronous")
    if force_synchronous == 'true':
        force_synchronous = True
    else:
        force_synchronous = False
    res = submit_case_reaction(user_uid=user_uid,
                               case_uuid=case_uuid,
                               reaction=Reaction[reaction],
                               value=value)
    task = res.pop('task')
    return execute_on_return(task, synchronous=force_synchronous, response=res)


@bp.route('/case/<case_uuid>/update', methods=["POST"])
@jwt_required()
def case_update(case_uuid):
    """
    Add an update to the description of a case.
    The update is stored alongside the original contents of the case.  Optionally the update can also indicate that the
    case should now be marked as resolved or unresolved.
    ---
    tags:
     - cases
    produces:
      - application/json
    parameters:
      - name: case_uuid
        in: path
        type: string
        required: true
      - name: force_synchronous
        in: query
        type: bool
        required: false
        description: Forces the return to be synchronous
      - name: content_uuid
        in: query
        type: string
        required: false
        description: If null, the update will be assigned to the first
          content in the case
      - name: body
        in: body
        required: true
        schema:
          properties:
            user_uid:
              type: string
              description: The uid for the user submitting the update
            text:
              type: string
              required: true
              description: The text contents of the update.
            diagnosis_text:
              type: string
              required: false
              description: The text contents of the diagnosis.
            linked_update_uuid:
              type: string
              description: The linked update uuid.
            resolved:
              type: boolean
              required: false
              description: A boolean indicating if the case label should be changed to 'resolved' or 'unresolved'.
                If null, no change will be made
          example:
            user_uid: sOSe6ll4fUMPCMgRliuo4r3SoKC3
            text: Case update text
            diagnosis_text: Case diagnosis text - Optional
            linked_update_uuid:  246d539f-c17c-4293-ab72-119449eaf1ba - Optional
            resolved: true
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
        return abort(400, 'missing user_uid')
    if 'text' not in request.json and 'diagnosis_text' not in request.json:
        return abort(400, 'missing text, or diagnosis_text')

    content_uuid = request.args.get('content_uuid')
    user_uid = request.json.get('user_uid')
    text = request.json.get('text')
    diagnosis_text = request.json.get('diagnosis_text')
    linked_update_uuid = request.json.get('linked_update_uuid')
    resolved = request.json.get('resolved')
    force_synchronous = request.args.get('force_synchronous')
    if force_synchronous == 'true':
        force_synchronous = True
    else:
        force_synchronous = False

    res = submit_case_update(user_uid=user_uid,
                             case_uuid=case_uuid,
                             text=text,
                             diagnosis_text=diagnosis_text,
                             content_uuid=content_uuid,
                             linked_update_uuid=linked_update_uuid,
                             resolved=resolved)
    task = res.pop('task')
    return execute_on_return(task, synchronous=force_synchronous, response=res)


@bp.route('/case/<case_uuid>/<user_uid>', methods=["DELETE"])
@bp.route('/admin/case/<case_uuid>/<moderator_uid>', methods=['DELETE'])
@jwt_required()
def case_delete_endpoint(case_uuid, user_uid=None, moderator_uid=None):
    """
    Delete a case
    Marks a case and associated content as deleted.  The case is also removed from the ES index and Firestore.
    ---
    tags:
     - cases
    produces:
      - application/json
    parameters:
      - name: case_uuid
        in: path
        type: string
        required: true
      - name: user_uid
        in: path
        type: string
        required: false
      - name: moderator_uid
        in: path
        type: string
        required: false
      - name: force_synchronous
        in: query
        type: bool
        required: false
        description: Forces the return to be synchronous
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

    res = delete_case(case_uuid=case_uuid, user_uid=user_uid, moderator_uid=moderator_uid)
    force_synchronous = request.args.get('force_synchronous')
    if force_synchronous == 'true':
        force_synchronous = True
    else:
        force_synchronous = False
    task = res.pop('task')
    return execute_on_return(task, synchronous=force_synchronous, response=res)


@bp.route('/case/<case_uuid>/progress', methods=["POST"])
@jwt_required()
def content_position(case_uuid):
    """
    Updates a user's progress on a case
    ---
    tags:
     - cases
    produces:
      - application/json
    parameters:
      - name: case_uuid
        in: path
        type: string
        required: true
      - name: force_synchronous
        in: query
        type: bool
        required: false
        description: Forces the return to be synchronous
      - name: body
        in: body
        required: true
        schema:
          properties:
            user_uid:
              type: string
              description: The uid for the user
            content_position:
              type: string
              required: false
              description: The index of the content reached
            is_complete:
              type: boolean
              required: false
              description: True if the case has been completed by the user, false otherwise.  If missing or null,
                the completed state is not updated
            degree_type:
              type: enum
              required: false
              items: ['M.D.', 'D.O.']
              description: Degree type of user.  Required for is_complete=true CME activities for certificate generation
          example:
            user_uid: sOSe6ll4fUMPCMgRliuo4r3SoKC3
            content_position: 5
            is_complete: true
            degree_type: M.D.
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
    m = CMEContentPositionModel.parse_obj({
        'case_uuid': case_uuid,
        **request.json
    })
    force_synchronous = request.args.get('force_synchronous')
    if force_synchronous == 'true':
        force_synchronous = True
    else:
        force_synchronous = False
    res = update_content_position(model=m)
    task = res.pop('task')
    return execute_on_return(task, synchronous=force_synchronous, response=res)


@bp.route('/case/missing_images', methods=["POST"])
@jwt_required()
def missing_images():
    """
        this endpoint checks to see if there are cases with missing images in the app/web.

         - if the case_uuid has a value, it will process it.
         - if an option is selected, it will process the selected option.
         - if nothing is passed or selected it will return nothing.
    ---
        tags:
         - Backend Tools
        produces:
          - application/json
        parameters:
          - name: case_uuid
            in: query
            required: false
            type: string
          - name: option
            in: query
            type: string
            enum: ['all_cases', 'new_cases']
            required: false
          - name: force_synchronous
            in: query
            type: bool
            required: false
            description: Forces the return to be synchronous
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
    case_uuid = request.args.get('case_uuid', None)
    option = request.args.get('option')
    force_synchronous = request.args.get('force_synchronous')
    if force_synchronous == 'true':
        force_synchronous = True
    else:
        force_synchronous = False

    if case_uuid:
        return execute_on_return(task=check_missing_media(case_uuid=case_uuid), synchronous=force_synchronous)
    elif option == 'all_cases':
        return execute_on_return(task=check_missing_media(all_cases=True), synchronous=force_synchronous)
    elif option == 'new_cases':
        return execute_on_return(task=check_missing_media(new_cases=True), synchronous=force_synchronous)
    else:
        return jsonify({}), 200


@bp.route('/case/sync_publications', methods=["POST"])
@jwt_required()
def publications_sync():
    """
    syncs case publication to firestore
    ---
    tags:
     - admin
    produces:
      - application/json
    parameters:
      - name: body
        in: body
        required: true
        schema:
          properties:
            case_uuid:
              type: string
              required: true
              description: The case uuid to sync
            action:
              type: string
              enum: ["SET", "DELETE"]
              description: The type of firebase action to perform
          example:
            case_uuid: <case_uuid>
            action: 'SET'
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
    if 'case_uuid' not in request.json:
        return abort(400, 'missing case uuid')
    if 'action' not in request.json:
        return abort(400, 'missing action')

    case_uuid = request.json.get('case_uuid')
    action = request.json.get('action', 'SET').upper()

    do_firebase_sync.delay(firebasemodel='CasePublications', uuid=case_uuid, action=FirebaseAction[action])
    return make_response(jsonify({"success": " CasePublications has been synced to firestore"}), 200)


@bp.route('/case/translate/<case_uuid>', methods=['POST'])
def translate_case_endpoint(case_uuid):
    """
    Translate a case
    ---
    tags:
     - cases
    produces:
      - application/json
    parameters:
      - name: case_uuid
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
    res = do_translate_case(case_uuid=case_uuid, target_language=request.json.get('target_language'))
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


@bp.route('/case/<case_uuid>/update/with-mentions', methods=["POST"])
@jwt_required()
def case_update_with_mentions(case_uuid):
    """
    Add an update to the description of a case with user mentions.
    The update is stored alongside the original contents of the case.  Optionally the update can also indicate that the
    case should now be marked as resolved or unresolved.
    ---
    tags:
     - mentions
    produces:
      - application/json
    parameters:
      - name: case_uuid
        in: path
        type: string
        required: true
      - name: force_synchronous
        in: query
        type: bool
        required: false
        description: Forces the return to be synchronous
      - name: content_uuid
        in: query
        type: string
        required: false
        description: If null, the update will be assigned to the first
          content in the case
      - name: body
        in: body
        required: true
        schema:
          properties:
            user_uid:
              type: string
              description: The uid for the user submitting the update
            text:
              type: string
              required: true
              description: The text contents of the update.
            diagnosis_text:
              type: string
              required: false
              description: The text contents of the diagnosis.
            linked_update_uuid:
              type: string
              description: The linked update uuid.
            resolved:
              type: boolean
              required: false
              description: A boolean indicating if the case label should be changed to 'resolved' or 'unresolved'.
                If null, no change will be made
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
            text: Case update text with @john_doe
            diagnosis_text: Case diagnosis text - Optional
            linked_update_uuid:  246d539f-c17c-4293-ab72-119449eaf1ba - Optional
            resolved: true
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
    if 'user_uid' not in request.json:
        return abort(400, 'missing user_uid')
    if 'text' not in request.json and 'diagnosis_text' not in request.json:
        return abort(400, 'missing text, or diagnosis_text')

    content_uuid = request.args.get('content_uuid')
    user_uid = request.json.get('user_uid')
    text = request.json.get('text')
    diagnosis_text = request.json.get('diagnosis_text')
    linked_update_uuid = request.json.get('linked_update_uuid')
    resolved = request.json.get('resolved')
    mentions = request.json.get('mentions', [])
    force_synchronous = request.args.get('force_synchronous')
    if force_synchronous == 'true':
        force_synchronous = True
    else:
        force_synchronous = False

    import logging
    logger = logging.getLogger('figure1.cases')
    logger.info(f"Creating case update with {len(mentions)} mentions")

    # Create the case update first
    res = submit_case_update(user_uid=user_uid,
                             case_uuid=case_uuid,
                             text=text,
                             diagnosis_text=diagnosis_text,
                             content_uuid=content_uuid,
                             linked_update_uuid=linked_update_uuid,
                             resolved=resolved)

    # Process and store mentions if update was created successfully
    if mentions and 'error' not in res:
        try:
            from figure1.pro.mentions.domain import process_and_store_mentions

            # Use the content_uuid from the update if available, otherwise from query params
            update_content_uuid = res.get('content_uuid') or content_uuid
            logger.info(f"Processing mentions with content_uuid={update_content_uuid}, case_uuid={case_uuid}")

            mention_uuids = process_and_store_mentions(
                mentions=mentions,
                text=text or diagnosis_text or '',  # Use whichever text was provided
                mentioning_user_uid=user_uid,
                comment_uuid=None,  # Case updates are not comments
                content_uuid=update_content_uuid,
                case_uuid=case_uuid
            )

            # Add mention info to response
            res['mentions_created'] = len(mention_uuids)
            res['mention_uuids'] = mention_uuids

            logger.info(f"Stored {len(mention_uuids)} mentions for case update {case_uuid}")

            # Reset case sync timestamp to bypass throttling
            try:
                session = global_session()
                case = session.query(Case).get(case_uuid)
                if case:
                    case.synced_at = None
                    session.commit()
                    logger.info(f"Reset sync timestamp for case {case_uuid} to allow immediate Firestore sync with mentions")
                else:
                    logger.warning(f"Case {case_uuid} not found when trying to reset sync timestamp")
            except Exception as reset_error:
                logger.exception(f"Failed to reset sync timestamp: {reset_error}")

            logger.info(f"Case sync task will now fetch and include these mentions in Firestore")

            # TODO: Trigger notification system for each mention
            # This should send notifications to mentioned users

        except Exception as e:
            logger.exception(f"Error processing mentions for case update: {e}")
            # Don't fail the whole request if mention processing fails
            res['mention_error'] = str(e)
            res['mentions_created'] = 0

    task = res.pop('task')
    logger.info(f"Executing case sync task for {case_uuid} (synchronous={force_synchronous})")
    return execute_on_return(task, synchronous=force_synchronous, response=res)
