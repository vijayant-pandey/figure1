import logging
import os

from flask import Blueprint, request, abort, current_app
from flask.json import jsonify
from flask_jwt_extended import jwt_required

from figure1.common.types import CaseState
from figure1.common.utils import s3_utils, case_image_original_path
from figure1.exceptions import S3Error, UserError, GroupException, CaseError
from figure1.pro.cases.upload.domain import update_case_with_single_content, refresh_media_upload_url
from figure1.pro.cases.upload.tasks import add_image_to_draft, remove_media, delete_draft
from figure1.common.types import CaseUploadModel

bp = Blueprint('pro_cases_upload_endpoint', __name__)
logger = logging.getLogger(__name__)


@bp.errorhandler(S3Error)
def upload_handle_s3_error(e):
    logger.exception("S3 upload failed %s", e.msg)
    return jsonify(dict(message=e.msg, code=e.rc)), 500


@bp.errorhandler(UserError)
def handle_user_error(e):
    logger.exception("%s", e.msg)
    return jsonify(e.as_dict()), e.rc


@bp.errorhandler(GroupException)
def handle_group_error(e):
    logger.exception("%s", e.msg)
    return jsonify(e.as_dict()), e.rc


@bp.errorhandler(CaseError)
def handle_case_modification_error(e):
    logger.exception("%s", e.msg)
    return jsonify(e.as_dict()), e.rc


@bp.route('/draft/<user_uid>/<draft_uid>', methods=["POST"])
@jwt_required()
def post_case(user_uid, draft_uid):
    """
    Upload new case content
    Updates a draft or submit a case for moderation.  Once completed, updates the draft's firestore data as appropriate.
    ---
    tags:
     - draft
    produces:
      - application/json
    parameters:
      - name: user_uid
        in: path
        type: string
        description:  The UID of the user creating the draft
        required: true
      - name: draft_uid
        in: path
        type: string
        description:  The UID of the draft being created
        required: true
      - name: state
        in: query
        type: string
        enum: ['draft', 'submit']
        description:  The state of the case that's being uploaded.  'submit' if the case has been finalized and is ready
          for submission to moderation, 'draft' otherwise
        required: true
      - name: body
        in: body
        required: true
        schema:
          properties:
            post_process_media:
              type: bool
              required: false
              description: Set to true if media is uploaded from the device.
            case_uuid:
              type: string
              required: false
              description: The uuid of the case to update.  If missing, a new case will be created instead.
            case_classification:
              type: enum
              required: False
              values: ['medical', 'nonmedical']
              description: Is this a medical or non-medical case?

            title:
              type: string
              required: true
              description: The title of the case
            caption:
              type: string
              required: true
              description: The caption text for the case
            media:
              type: array
              description: The media (e.g. images, videos) for the case
              items:
                type: object
                properties:
                  url:
                    type: string
                    description: The url for the media
                  index:
                    type: int
                    description:  The index position of the media within the case.
                  type:
                    type: string
                    enum: ['image', 'image_series', 'video']
                    description:  The type of media
                  filename:
                    type: int
                    description:  The stored filename for the media, set during media upload
                required: true
            specialty_uuids:
              type: array
              items:
                type: string
              description:  The specialties that the case relates to
              required: true
            label_uuids:
              type: array
              items:
                type: string
              description:  The labels for the case (e.g. 'resolved', 'teaching_case')
              required: true
            paging:
              type: bool
              description:  True if the case is a paging case
              required: true
            request_help:
              type: bool
              description: True if the help is needed, False otherwise
              required: false
            group_uuid:
              type: string
              item:
                type: string
              description: group uuid if exists - optional
              required: false
            diagnosis:
              type: string
              description: case diagnosis - optional
              required: false
            is_anonymous:
              type: bool
              description: True if the case anonymous, False otherwise
              required: false
          example:
            post_process_media: false
            title: Case title
            caption: Case details
            case_classification: nonmedical
            media:
                - url: https://figure1-pro-dev.imgix.net/cases/images/upload_57505d4da4812f39528a514ce27881f4.jpg
                  index: 0
                  type: image
                  filename: upload_57505d4da4812f39528a514ce27881f4.jpg
                - url: https://figure1-pro-dev.imgix.net/cases/images/upload_0bf829847169a8bb4e5b58684b665794.jpg
                  index: 1
                  type: image
                  filename: upload_0bf829847169a8bb4e5b58684b665794.jpg
            specialty_uuids:
                - 7e2a2aac-629e-444e-8668-b8eaaf75171e
                - 8bc8a7e8-7c85-43dd-8c4d-3da5e1f8ccd9
            label_uuids:
                - 4a9a2519-98a1-4908-a8ae-ef1b3127487b
                - 2897fd2f-4353-4b53-923d-dbb05128c4b6
            group_uuid: <group_uuid>
            paging: false
            request_help: true
            diagnosis: diagnosis 1
            is_anonymous: false

    responses:
      default:
        description: Unexpected Failure
      '422':
        description: Invalid request body
      '202':
        description: OK
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """

    case_data = CaseUploadModel.parse_obj(request.json)
    state = request.args.get('state').lower()
    if state == 'draft':
        case_state = CaseState.DRAFT
    elif state == 'submit':
        case_state = CaseState.PENDING_APPROVAL
    else:
        return abort(422, f'Invalid state: {state}')

    # Extract mentions if provided
    mentions = request.json.get('mentions', [])
    if mentions:
        logger.info(f"Creating case for user {user_uid} with {len(mentions)} mentions, state={state}")

    task, case_uuid = update_case_with_single_content(user_uid=user_uid,
                                                      draft_uid=draft_uid,
                                                      data=case_data,
                                                      state=case_state)

    # Process mentions if provided
    response_data = dict(success='Upload task started', caseUuid=case_uuid)

    if mentions and case_uuid:
        try:
            from figure1.pro.mentions.domain import process_and_store_mentions
            from figure1.core.db import global_session
            from figure1.common.models.db.c_case_model import Case
            from figure1.common.models.db.c_content_model import Content

            logger.info(f"Processing {len(mentions)} mentions for case {case_uuid}")

            # Get the content_uuid for this case's caption
            session = global_session()
            content = session.query(Content).filter(
                Content.case_uuid == case_uuid
            ).order_by(Content.display_order).first()

            if content:
                content_uuid = content.content_uuid

                # Process and store mentions
                mention_uuids = process_and_store_mentions(
                    mentions=mentions,
                    text=case_data.caption or '',
                    mentioning_user_uid=user_uid,
                    comment_uuid=None,
                    content_uuid=content_uuid,
                    case_uuid=case_uuid
                )

                logger.info(f"Stored {len(mention_uuids)} mentions for case {case_uuid}")

                # Reset sync timestamp to ensure Firestore includes mentions
                try:
                    case = session.query(Case).get(case_uuid)
                    if case:
                        case.synced_at = None
                        session.commit()
                        logger.info(f"Reset sync timestamp for case {case_uuid}")
                except Exception as reset_error:
                    logger.exception(f"Failed to reset sync timestamp: {reset_error}")

                response_data['mentions_created'] = len(mention_uuids)
                response_data['mention_uuids'] = [str(m) for m in mention_uuids]
            else:
                logger.warning(f"No content found for case {case_uuid}, cannot process mentions")
                response_data['mention_error'] = 'No content found for case'

        except Exception as e:
            logger.exception(f"Error processing mentions: {e}")
            response_data['mention_error'] = str(e)

    task.apply_async()
    return jsonify(response_data), 202


@bp.route('/draft/<user_uid>/<draft_uid>', methods=["DELETE"])
@jwt_required()
def delete_case(user_uid, draft_uid):
    """
    Delete previously uploaded case draft
    Deletes the draft from firestore, then deletes the case and media from postgres, and the media from s3.
    ---
    tags:
     - draft
    produces:
      - application/json
    parameters:
      - name: user_uid
        in: path
        type: string
        description:  The UID of the user who created the draft
        required: true
      - name: draft_uid
        in: path
        type: string
        description:  The UID of the draft to delete
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
    delete_draft.delay(user_uid=user_uid, draft_uid=draft_uid)
    return jsonify({'success': f'Task submitted'}), 202


@bp.route('/draft/<user_uid>/<draft_uid>/refresh_media_upload_url', methods=['GET'])
@jwt_required()
def refresh_media_upload_url_endpoint(user_uid, draft_uid):
    """
    Update presigned media upload url - assumes the user is uploading to '/drafts/<user_uid>/<draft_uid>/'
    Updates the presigned url in firestore as well as returns it.
    ---
    tags:
     - draft
    produces:
      - application/json
    parameters:
      - name: user_uid
        in: path
        type: string
        description:  The UID of the user creating the draft
        required: true
      - name: draft_uid
        in: path
        type: string
        description:  The UID of the draft being created
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
    r = refresh_media_upload_url(user_uid=user_uid, draft_uid=draft_uid)
    return jsonify(r), 200


@bp.route('/draft/<user_uid>/<draft_uid>/media', methods=["POST"])
@jwt_required()
def upload_case_media(user_uid, draft_uid):
    """
    Upload media for new case content
    Uploads the media to s3.  Once uploaded, a task is invoked to process the image and update the draft's firestore
    data for the uploaded media.  If a filename is given, an existing image will be updated; otherwise a new image will
    be uploaded.
    ---
    tags:
     - draft
    produces:
      - application/json
    parameters:
      - name: user_uid
        in: path
        type: string
        description:  The UID of the user creating the draft
        required: true
      - name: draft_uid
        in: path
        type: string
        description:  The UID of the draft being created
        required: true
      - name: picture
        in: formData
        description:  The media to upload
        type: file
        required: true
      - name: index
        in: query
        type: int
        description:  The index position of the media within the case, 0-based.  If the index is null, the new media
          will get the next available index.
        required: false
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
    if 'picture' not in request.files:
        abort(400)

    file = request.files['picture']
    try:
        index = int(request.args['index']) if 'index' in request.args else None
    except ValueError:
        logging.error(f"Invalid index: {request.args['index']}")
        return jsonify({'success': f'Invalid index'}), 422

    temp_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], user_uid)
    res = s3_utils.upload_image_to_s3(file=file, upload_dir=case_image_original_path, temp_dir=temp_dir)
    if 'error' in res:
        return jsonify({'error': res['error']}), 500

    add_image_to_draft.delay(original_filename=res.get('filename'),
                             file_hash=res.get('file_hash'),
                             temp_dir=temp_dir,
                             user_uid=user_uid,
                             draft_uid=draft_uid,
                             index=index)
    return jsonify({'success': f'Task submitted'}), 202


@bp.route('/draft/<user_uid>/<draft_uid>/media', methods=["DELETE"])
@jwt_required()
def delete_case_media(user_uid, draft_uid):
    """
    Delete previously uploaded case media
    Deletes the media from s3.  Once deleted, updates the draft's firestore data to remove the media.
    ---
    tags:
     - draft
    produces:
      - application/json
    parameters:
      - name: user_uid
        in: path
        type: string
        description:  The UID of the user creating the draft
        required: true
      - name: draft_uid
        in: path
        type: string
        description:  The UID of the draft being created
        required: true
      - name: index
        in: query
        type: int
        description:  The index position of the media to delete.
        required: false
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
    if 'index' not in request.args:
        abort(400)
    index = int(request.args['index'])

    remove_media.delay(user_uid=user_uid,
                       draft_uid=draft_uid,
                       index=index)

    return jsonify({'success': f'Task submitted'}), 202
