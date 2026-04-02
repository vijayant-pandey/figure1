import logging
import os

from PIL import Image
from flask import Blueprint, jsonify, request, abort, current_app
from flask_jwt_extended import jwt_required

from figure1.admin.campaign.case.domain import create_update_quiz, \
    create_update_static_case, \
    create_update_quiz_series, \
    create_update_clinical_moments, \
    set_campaign_tactic_active_range, \
    publish_campaign_tactic, \
    review_campaign_tactic, \
    archive_campaign_tactic, \
    unarchive_campaign_tactic, \
    create_update_cme, \
    delete_tactic, create_promo_card
from figure1.admin.campaign.case.tasks import sync_promo_card_task
from figure1.core import es
from figure1.common.utils import s3_utils, case_image_path, cme_certificate_templates_path
from figure1.exceptions import CampaignException, VimeoError

bp = Blueprint('pro_admin_campaign_case_endpoint', __name__)


@bp.app_errorhandler(CampaignException)
def handle_campaign_exception(e):
    return jsonify(e.as_dict()), e.rc


@bp.app_errorhandler(VimeoError)
def handle_vimeo_error(e):
    return jsonify(e.as_dict()), e.rc


@bp.route('/case/<case_uuid>/archive', methods=["POST"])
@jwt_required()
def archive_tactic(case_uuid):
    """
    This endpoint archives a tactic, it does not check what the state of the campaign or the tactic is in.
    ---
    tags:
     - campaigns
    produces:
      - application/json
    parameters:
      - name: case_uuid
        in: path
        type: string
        required: true
        description: The uuid of the tactic to update
      - name: body
        in: body
        required: true
        schema:
          properties:
            moderator_uid:
              type: string
              required: true
              description: The uid of the moderator modifying the case

    responses:
      default:
        description: Unexpected Failure
      '200':
        description: OK
      '404':
        description: User or Tactic not found
      '410':
        description: Tactic has been marked deleted
      '500':
        description: Error caught while updating tactic

    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    moderator_uid = request.json.get('moderator_uid')
    task = archive_campaign_tactic(case_uuid=case_uuid, user_uid=moderator_uid)
    task.apply()
    return jsonify({}), 200


@bp.route('/case/<case_uuid>/unarchive', methods=["POST"])
@jwt_required()
def unarchive_tactic(case_uuid):
    """
    This call unarchives a previously archived tactic. This does not verify the campaign state, however the state
    will be invalid if set to DRAFT when the attached campaign is set to ARCHIVED.

    ---
    tags:
     - campaigns
    produces:
      - application/json
    parameters:
      - name: case_uuid
        in: path
        type: string
        required: true
        description: The uuid of the tactic to update
      - name: body
        in: body
        required: true
        schema:
          properties:
            moderator_uid:
              type: string
              required: true
              description: The uid of the moderator modifying the case

    responses:
      default:
        description: Unexpected Failure
      '200':
        description: OK
      '404':
        description: User or Tactic not found
      '410':
        description: Tactic has been marked deleted
      '500':
        description: Error caught while updating tactic

    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    moderator_uid = request.json.get('moderator_uid')
    task = unarchive_campaign_tactic(case_uuid=case_uuid, user_uid=moderator_uid)
    task.apply()
    return jsonify({}), 200


@bp.route('/case/<case_uuid>/publish', methods=["POST"])
@jwt_required()
def publish_tactic(case_uuid):
    """
    This call requires the case be in SC_REVIEW state, this call makes the calls necessary to deploy the tactic. This
    includes:
    - Set Campaign state to active
    - Set Case state to SC_APPROVED
    - Set Tactic start_date to today if it is unset.
    Note that this means the campaign this is attached to can no longer be edited

    ---
    tags:
     - campaigns
    produces:
      - application/json
    parameters:
      - name: case_uuid
        in: path
        type: string
        required: true
        description: The uuid of the tactic to update
      - name: body
        in: body
        required: true
        schema:
          properties:
            moderator_uid:
              type: string
              required: true
              description: The uid of the moderator modifying the case

    responses:
      default:
        description: Unexpected Failure
      '200':
        description: OK
      '404':
        description: User or Tactic not found
      '410':
        description: Tactic has been marked deleted
      '500':
        description: Error caught while updating tactic

    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    moderator_uid = request.json.get('moderator_uid')
    task = publish_campaign_tactic(case_uuid=case_uuid, user_uid=moderator_uid)
    task.apply()
    return jsonify({}), 200


@bp.route('/case/<case_uuid>/review', methods=["POST"])
@jwt_required()
def review_tactic(case_uuid):
    """
    This call requires the case be in DRAFT state, this currently just sets the state to SC_REVIEW. This is required
    for moving the tactic to SC_APPROVED

    ---
    tags:
     - campaigns
    produces:
      - application/json
    parameters:
      - name: case_uuid
        in: path
        type: string
        required: true
        description: The uuid of the tactic to update
      - name: body
        in: body
        required: true
        schema:
          properties:
            moderator_uid:
              type: string
              required: true
              description: The uid of the moderator modifying the case

    responses:
      default:
        description: Unexpected Failure
      '200':
        description: OK
      '404':
        description: User or Tactic not found
      '410':
        description: Tactic has been marked deleted
      '500':
        description: Error caught while updating tactic
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    moderator_uid = request.json.get('moderator_uid')
    task = review_campaign_tactic(case_uuid=case_uuid, user_uid=moderator_uid)
    task.apply()
    return jsonify({}), 200


@bp.route('/case/<case_uuid>', methods=["DELETE"])
@jwt_required()
def delete_tactic_endpoint(case_uuid):
    """
    Deletes a tactic
    ---
    tags:
     - campaigns
    produces:
      - application/json
    parameters:
      - name: case_uuid
        in: path
        type: string
        required: true
        description: The uuid of the tactic to delete
      - name: body
        in: body
        required: true
        schema:
          properties:
            moderator_uid:
              type: string
              required: true
              description: The uid of the moderator modifying the case

    responses:
      default:
        description: Unexpected Failure
      '200':
        description: OK
      '404':
        description: User or Tactic not found
      '500':
        description: Error caught while deleting tactic
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    moderator_uid = request.json.get('moderator_uid')
    task = delete_tactic(case_uuid=case_uuid, user_uid=moderator_uid)
    task.apply()
    return jsonify({'success': 'Tactic Deleted'}), 200


@bp.route('/case/<case_uuid>/set', methods=["POST"])
@jwt_required()
def set_tactic_active_range(case_uuid):
    """
    Sets date_range for a given tactic
    Date range is optional, however if a tactic is published the start_date is set to today
    If the end_date is not passed, it is set to the end_date for the campaign, if the campaign end_date is not set,
     it is left null.
    When a campaign is archived, end_dates for all tactics are set to today.

    ---
    tags:
     - campaigns
    produces:
      - application/json
    parameters:
      - name: case_uuid
        in: path
        type: string
        required: true
        description: The uuid of the tactic to update
      - name: body
        in: body
        required: true
        schema:
          properties:
            moderator_uid:
              type: string
              required: true
              description: The uid of the moderator modifying the case
            tactic_priority:
              type: integer
              description: Set the priority of this tactic
            start_date:
              type: string
              format: date
              description: The date to start serving this tactic - defaults to current date if left empty
            end_date:
              type: string
              format: date
              description: The date to stop serving this tactic - defaults to Null which serves the tactic until the
                           campaign is stopped.

    responses:
      default:
        description: Unexpected Failure
      '200':
        description: OK
      '404':
        description: User or Tactic not found
      '410':
        description: Tactic has been marked deleted
      '500':
        description: Error caught while updating tactic
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    data = request.json
    moderator_uid = data.get('moderator_uid')
    start_date = data.get('start_date', None)
    end_date = data.get('end_date', None)
    task = set_campaign_tactic_active_range(case_uuid=case_uuid,
                                            user_uid=moderator_uid,
                                            start_date=start_date,
                                            end_date=end_date)
    task.apply()
    return jsonify({}), 200


@bp.route('/tools/sync_promo_card', methods=["POST"])
@jwt_required()
def sync_promo_card_endpoint():
    """
    Forces a firestore sync of a promo card to a user

    Previous promo cards are not removed.  If the promo card was previously synced and not dismissed it will be
    duplicated
    ---
    tags:
     -  admin
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
              description: The case_uuid of the promo card to sync
            user_uid:
              type: integer
              description: The user_uid of the user the card should be synced for.
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
    data = request.json
    case_uuid = data.get('case_uuid')
    user_uid = data.get('user_uid')
    task = sync_promo_card_task.apply(kwargs=dict(case_uuid=case_uuid, user_uid=user_uid))
    return jsonify({'status': task.status})


@bp.route('/case/image/<moderator_uid>', methods=["POST"])
@jwt_required()
def upload_case_image(moderator_uid):
    """
    Upload image media for a case.
    Uploads the image to s3 and returns the media properties to include in case creation.
    ---
    tags:
     - campaigns
    produces:
      - application/json
    parameters:
      - name: moderator_uid
        in: path
        type: string
        required: true
      - name: picture
        in: formData
        description:  The media to upload
        type: file
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
    if 'picture' not in request.files:
        abort(422)

    file = request.files['picture']

    temp_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], moderator_uid)
    res = s3_utils.upload_image_to_s3(file=file, upload_dir=case_image_path, temp_dir=temp_dir)

    file.stream.seek(0)
    image = Image.open(file)

    return jsonify({
        'success': 'Image Uploaded',
        'media': {
            "type": "image",
            "filename": res.get('filename'),
            "url": res.get('photo_url'),
            "height": image.height,
            "width": image.width
        },
    }), 200


@bp.route('/case/cme_certificate/<moderator_uid>', methods=["POST"])
@jwt_required()
def upload_cme_certificate(moderator_uid):
    """
    Upload cme certificate template for a case.
    Uploads the certificate to s3 and returns the properties to include the tactic 'certificates'
    ---
    tags:
     - campaigns
    produces:
      - application/json
    parameters:
      - name: moderator_uid
        in: path
        type: string
        required: true
      - name: certificate
        in: formData
        description:  The certificate to upload
        type: file
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
    if 'certificate' not in request.files:
        abort(422)

    file = request.files['certificate']

    temp_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], moderator_uid)
    try:
        os.makedirs(temp_dir, exist_ok=True)
    except OSError as e:
        logging.error(f"Failed to create temp dir {temp_dir}: {e}")
        return jsonify({'error': 'Failed to save certificate'}), 500

    temp_path = os.path.join(temp_dir, file.filename)
    try:
        file.save(temp_path)
    except Exception as e:
        logging.error(f"Failed to save certificate: {e}")
        return jsonify({'error': 'Failed to save certificate'}), 500

    upload_path = '/'.join([cme_certificate_templates_path, 'unassigned', file.filename])
    s3_utils.upload_to_s3(source_path=temp_path, upload_path=upload_path)

    return jsonify({
        'success': 'CME Certificate Template Uploaded',
        'certificate': {
            'filename': file.filename,
            'path': upload_path
        },
    }), 200


@bp.route('/case/static', methods=['POST'])
@bp.route('/case/static/<case_uuid>', methods=['PUT'])
@jwt_required()
def create_update_static_case_endpoint(case_uuid=None):
    """
    Create or update a static case tactic
    ---
    tags:
     - campaigns
    produces:
      - application/json
    parameters:
      - name: case_uuid
        in: path
        type: string
        required: false
        description: The uuid of the case to update.  Required for PUT only.
      - name: body
        in: body
        required: true
        schema:
          properties:
            moderator_uid:
              type: string
              required: true
              description: The uid of the moderator creating the case
            campaign_uuid:
              type: string
              description: The campaign for the tactic
              required: true
            author_uid:
              type: string
              required: true
              description: The uid of the author that the case will be attributed to
            title:
              type: string
              required: false
            caption:
              type: string
              required: false
            references:
              type: string
              required: false
            media:
              type: array
              items: object
              required: false
              properties:
                filename:
                  type: string
                type:
                  type: string
                width:
                  type: int
                height:
                  type: int
            sponsored_content:
              type: object
              required: false
              description: The sponsor details.  If null, the case is not sponsored
              properties:
                sponsored_text:
                  type: string
                disclosure_text:
                  type: string
                job_code:
                  type: string
            external_link:
              type: object
              required: false
              description: An external link to show in the case.  If null, no link will be shown.
              properties:
                external_link_text:
                  type: string
                external_link_url:
                  type: string
            features:
              type: object
              required: false
              description: Optional behaviours to enable/disable on the case.
              properties:
                comments_enabled:
                  type: boolean
                comment_queue_enabled:
                  type: boolean
                reactions_enabled:
                  type: boolean
                save_enabled:
                  type: boolean
                share_enabled:
                  type: boolean
                zoom_enabled:
                  type: boolean
            isi:
              type: object
              required: false
              description: ISI information for the case.  If null, ISI is not shown.
              properties:
                isi_link:
                  type: string
                isi_text:
                  type: string
                isi_embedded_content_link:
                  type: string
            feed_card:
              type: object
              required: false
              description: Data for the tactic feed card.  Some feed_card_types donot require all properties to be set
              properties:
                feed_card_type:
                  type: string
                  items: ['BASIC', 'HIGHLIGHT']
                feed_card_label:
                  type: string
                feed_card_title:
                  type: string
                button_text:
                  type: string
                colour:
                  type: string
                feed_card_media:
                  type: object
                  items: object
                  required: false
                  properties:
                    filename:
                      type: string
                    type:
                      type: string
                    width:
                      type: int
                    height:
                      type: int
            settings:
              type: object
              required: false
              properties:
                tactic_priority:
                  type: int
                  description: A value between 1 and 3 which influences the ordering of the tactic within user feeds.
                name:
                  type: text
          example:
            moderator_uid: tJMPKzrR4ig3Yejc7cRQGSl8URr1
            author_uid: tJMPKzrR4ig3Yejc7cRQGSl8URr1
            campaign_uuid:
            title: Sample case title
            caption: Sample case caption
            references: Sample references
            media:
              - filename: 33468feea4872dbaab01b8f383ef83606c82d1dce0cf5393fb4044c026ef5071.png
                type: image
                width: 3000
                height: 2002
            sponsored_content:
              sponsored_text: Sponsored Content
              disclosure_text: This case is sponsored
              job_code: 123
            external_link:
              external_link_text: Learn more
              external_link_url: https://www.figure1.com
            features:
              comments_enabled: True
              comment_queue_enabled: False
              reactions_enabled: True
              save_enabled: True
              share_enabled: True
              zoom_enabled: True
            isi:
              isi_link: http://www.figure1.com
              isi_text: Full Prescribing Information, including Boxed WARNING
              isi_embedded_content_link: http://www.figure1.com
            feed_card:
              feed_card_type: HIGHLIGHT
              feed_card_label: Label
              feed_card_title: Common upstream regulators of MCL-1
              button_text: Start Activity
              colour: 236B84
              feed_card_media:
                filename: 33468feea4872dbaab01b8f383ef83606c82d1dce0cf5393fb4044c026ef5071.png
                type: image
                width: 3000
                height: 2002
            settings:
              tactic_priority: 1
              name: New Tactic
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

    if 'moderator_uid' not in request.json:
        return abort(422, 'missing moderator_uid')
    if 'author_uid' not in request.json:
        return abort(422, 'missing author_uid')
    if 'campaign_uuid' not in request.json:
        return abort(422, 'missing campaign_uuid')
    if request.method == 'PUT' and not case_uuid:
        return abort(422, 'missing case_uuid')

    moderator_uid = request.json.get('moderator_uid')

    res = create_update_static_case(moderator_uid=moderator_uid,
                                    case_uuid=case_uuid,
                                    data=request.json)
    task = res.pop('task')
    task.apply()
    return jsonify(res), 200


@bp.route('/case/static/with-mentions', methods=['POST'])
@jwt_required()
def create_static_case_with_mentions_endpoint():
    """
    Create a new static case tactic with mentions in caption
    """
    logger = logging.getLogger('figure1.admin.campaign')

    # Validate required fields
    if 'moderator_uid' not in request.json:
        return abort(422, 'missing moderator_uid')
    if 'author_uid' not in request.json:
        return abort(422, 'missing author_uid')
    if 'campaign_uuid' not in request.json:
        return abort(422, 'missing campaign_uuid')

    moderator_uid = request.json.get('moderator_uid')
    author_uid = request.json.get('author_uid')
    mentions = request.json.get('mentions', [])

    logger.info(f"Creating new case with {len(mentions)} mentions in caption")

    # Step 1: Create the case using existing logic
    res = create_update_static_case(moderator_uid=moderator_uid,
                                    case_uuid=None,  # Always creating new case
                                    data=request.json)

    if 'error' in res:
        return jsonify(res), 400

    # Extract case_uuid and content_uuid from result
    case_uuid = res.get('case_uuid')
    content_uuid = res.get('content_uuid')

    if not case_uuid or not content_uuid:
        logger.error(f"Failed to extract case_uuid or content_uuid from result: {res}")
        return jsonify({'error': 'Failed to extract case_uuid or content_uuid from result'}), 500

    # Step 2: Process and store mentions if provided
    if mentions and request.json.get('caption'):
        try:
            from figure1.pro.mentions.domain import process_and_store_mentions
            from figure1.core.db import global_session
            from figure1.common.models.db.c_case_model import Case

            logger.info(f"Processing mentions for new case {case_uuid}, content {content_uuid}")

            mention_uuids = process_and_store_mentions(
                mentions=mentions,
                text=request.json.get('caption', ''),
                mentioning_user_uid=author_uid,
                comment_uuid=None,  # Not a comment
                content_uuid=content_uuid,
                case_uuid=case_uuid
            )

            logger.info(f"Stored {len(mention_uuids)} mentions for new case {case_uuid}")

            # Step 3: Reset sync timestamp to ensure Firestore sync includes mentions
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

            # Add mention info to response
            res['mentions_created'] = len(mention_uuids)
            res['mention_uuids'] = [str(m) for m in mention_uuids]

        except Exception as e:
            logger.exception(f"Error processing mentions for new case: {e}")
            res['mention_error'] = str(e)
            res['mentions_created'] = 0

    # Execute the sync task
    task = res.pop('task')
    task.apply()

    # Wrap response in 'store' key to match expected cloud function response format
    return jsonify({
        'store': {
            'case_uuid': res.get('case_uuid'),
            'content_uuid': res.get('content_uuid')
        },
        'success': res.get('success'),
        'mentions_created': res.get('mentions_created', 0),
        'mention_uuids': res.get('mention_uuids', [])
    }), 200


@bp.route('/case/quiz', methods=['POST'])
@bp.route('/case/quiz/<case_uuid>', methods=['PUT'])
@jwt_required()
def create_update_quiz_case_endpoint(case_uuid=None):
    """
    Create or update a quiz tactic
    ---
    tags:
     - campaigns
    produces:
      - application/json
    parameters:
      - name: case_uuid
        in: path
        type: string
        required: false
        description: The uuid of the case to update.  Required for PUT only.
      - name: body
        in: body
        required: true
        schema:
          properties:
            moderator_uid:
              type: string
              required: true
              description: The uid of the moderator creating the case
            campaign_uuid:
              type: string
              description: The campaign for the tactic
            author_uid:
              type: string
              required: true
              description: The uid of the author that the case will be attributed to
            title:
              type: string
              required: false
            caption:
              type: string
              required: false
            references:
              type: string
              required: false
            media:
              type: array
              items: object
              required: false
              properties:
                filename:
                  type: string
                type:
                  type: string
                width:
                  type: int
                height:
                  type: int
            question_answer_details:
              type: string
              required: false
            question_options:
              type: array
              items: object
              required: false
              description: The selectable choices for the quiz question.  If no questions are marked as is_answer=True
                the created case will be a poll instead of a quiz
              properties:
                text:
                  type: string
                is_answer:
                  type: boolean
            sponsored_content:
              type: object
              required: false
              description: The sponsor details.  If null, the case is not sponsored
              properties:
                sponsored_text:
                  type: string
                disclosure_text:
                  type: string
                job_code:
                  type: string
            external_link:
              type: object
              required: false
              description: An external link to show in the case.  If null, no link will be shown.
              properties:
                external_link_text:
                  type: string
                external_link_url:
                  type: string
            features:
              type: object
              required: false
              description: Optional behaviours to enable/disable on the case.
              properties:
                comments_enabled:
                  type: boolean
                comment_queue_enabled:
                  type: boolean
                reactions_enabled:
                  type: boolean
                save_enabled:
                  type: boolean
                share_enabled:
                  type: boolean
                zoom_enabled:
                  type: boolean
            isi:
              type: object
              required: false
              description: ISI information for the case.  If null, ISI is not shown.
              properties:
                isi_link:
                  type: string
                isi_text:
                  type: string
                isi_embedded_content_link:
                  type: string
            feed_card:
              type: object
              required: false
              description: Data for the tactic feed card.  Some feed_card_types donot require all properties to be set
              properties:
                feed_card_type:
                  type: string
                  items: ['BASIC', 'HIGHLIGHT']
                feed_card_label:
                  type: string
                feed_card_title:
                  type: string
                button_text:
                  type: string
                colour:
                  type: string
                feed_card_media:
                  type: object
                  required: false
                  description: Passing an empty object here deletes an existing feed card media entry if it exists
                  properties:
                    filename:
                      type: string
                    type:
                      type: string
                    width:
                      type: int
                    height:
                      type: int
            settings:
              type: object
              required: false
              properties:
                tactic_priority:
                  type: int
                  description: A value between 1 and 3 which influences the ordering of the tactic within user feeds.
                name:
                  type: text
          example:
            moderator_uid: tJMPKzrR4ig3Yejc7cRQGSl8URr1
            author_uid: tJMPKzrR4ig3Yejc7cRQGSl8URr1
            campaign_uuid:
            title: Quiz question goes here?
            caption: Quiz caption
            references: Sample references
            media:
              - filename: 33468feea4872dbaab01b8f383ef83606c82d1dce0cf5393fb4044c026ef5071.png
                type: image
                width: 3000
                height: 2002
            question_answer_details: Details here
            question_options:
              - text: Option A
                is_answer: True
              - text: Option B
                is_answer: False
              - text: Option C
                is_answer: False
            sponsored_content:
              sponsored_text: Sponsored Content
              disclosure_text: This case is sponsored
              job_code: 123
            external_link:
              external_link_text: Learn more
              external_link_url: https://www.figure1.com
            features:
              comments_enabled: True
              comment_queue_enabled: False
              reactions_enabled: True
              save_enabled: True
              share_enabled: True
              zoom_enabled: True
            isi:
              isi_link: http://www.figure1.com
              isi_text: Full Prescribing Information, including Boxed WARNING
              isi_embedded_content_link: http://www.figure1.com
            feed_card:
              feed_card_type: HIGHLIGHT
              feed_card_label: Label
              feed_card_title: Common upstream regulators of MCL-1
              button_text: Start Activity
              colour: 236B84
              feed_card_media:
                filename: 33468feea4872dbaab01b8f383ef83606c82d1dce0cf5393fb4044c026ef5071.png
                type: image
                width: 3000
                height: 2002
            settings:
              tactic_priority: 1
              name: New Tactic
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

    if 'moderator_uid' not in request.json:
        return abort(422, 'missing moderator_uid')
    if 'author_uid' not in request.json:
        return abort(422, 'missing author_uid')
    if 'campaign_uuid' not in request.json:
        return abort(422, 'missing campaign_uuid')
    if request.method == 'PUT' and not case_uuid:
        return abort(422, 'missing case_uuid')

    moderator_uid = request.json.get('moderator_uid')

    res = create_update_quiz(moderator_uid=moderator_uid,
                             case_uuid=case_uuid,
                             data=request.json)
    task = res.pop('task')
    task.apply()

    return jsonify(res), 200


@bp.route('/case/quiz_series', methods=['POST'])
@bp.route('/case/quiz_series/<case_uuid>', methods=['PUT'])
@jwt_required()
def create_update_quiz_series_endpoint(case_uuid=None):
    """
    Create or update a quiz series tactic
    ---
    tags:
     - campaigns
    produces:
      - application/json
    parameters:
      - name: case_uuid
        in: path
        type: string
        required: false
        description: The uuid of the case to update.  Required for PUT only.
      - name: body
        in: body
        required: true
        schema:
          properties:
            moderator_uid:
              type: string
              required: true
              description: The uid of the moderator creating the case
            campaign_uuid:
              type: string
              description: The campaign for the tactic
            author_uid:
              type: string
              required: true
              description: The uid of the author that the case will be attributed to
            heading:
              type: string
              required: false
            questions:
              type: array
              items: object
              required: true
              properties:
                title:
                  type: string
                  required: false
                caption:
                  type: string
                  required: false
                media:
                  type: array
                  items: object
                  required: false
                  properties:
                    filename:
                      type: string
                    type:
                      type: string
                    width:
                      type: int
                    height:
                      type: int
                question_answer_details:
                  type: string
                  required: false
                question_options:
                  type: array
                  items: object
                  required: false
                  description: The selectable choices for the quiz question.  If no quiz are marked as is_answer=True
                    the created case will be a poll instead of a quiz
                  properties:
                    text:
                      type: string
                    is_answer:
                      type: boolean
                external_link:
                  type: object
                  required: false
                  description: An external link to show in the question.  If null, no link will be shown.
                  properties:
                    external_link_text:
                      type: string
                    external_link_url:
                      type: string
                isi:
                  type: object
                  required: false
                  description: ISI information for the case.  If null, ISI is not shown.
                  properties:
                    isi_link:
                      type: string
                    isi_text:
                      type: string
                    isi_embedded_content_link:
                      type: string
                references:
                  type: string
                  required: false
            conclusion:
              type: object
              properties:
                caption:
                  type: string
                  required: false
                external_link:
                  type: object
                  required: false
                  description: An external link to show in the conclusion.  If null, no link will be shown.
                  properties:
                    external_link_text:
                      type: string
                    external_link_url:
                      type: string
              isi:
                type: object
                required: false
                description: ISI information for the case.  If null, ISI is not shown.
                properties:
                  isi_link:
                    type: string
                  isi_text:
                    type: string
                  isi_embedded_content_link:
                    type: string
            sponsored_content:
              type: object
              required: false
              description: The sponsor details.  If null, the case is not sponsored
              properties:
                sponsored_text:
                  type: string
                disclosure_text:
                  type: string
                job_code:
                  type: string
            features:
              type: object
              required: false
              description: Optional behaviours to enable/disable on the case.
              properties:
                comments_enabled:
                  type: boolean
                comment_queue_enabled:
                  type: boolean
                reactions_enabled:
                  type: boolean
                save_enabled:
                  type: boolean
                share_enabled:
                  type: boolean
                zoom_enabled:
                  type: boolean
            feed_card:
              type: object
              required: false
              description: Data for the tactic feed card.  Some feed_card_types donot require all properties to be set
              properties:
                feed_card_type:
                  type: string
                  items: ['BASIC', 'HIGHLIGHT']
                feed_card_label:
                  type: string
                feed_card_title:
                  type: string
                button_text:
                  type: string
                colour:
                  type: string
                feed_card_media:
                  type: object
                  required: false
                  description: Passing an empty object here deletes an existing feed_card_media if it exists
                  properties:
                    filename:
                      type: string
                    type:
                      type: string
                    width:
                      type: int
                    height:
                      type: int
            settings:
              type: object
              required: false
              properties:
                tactic_priority:
                  type: int
                  description: A value between 1 and 3 which influences the ordering of the tactic within user feeds.
                name:
                  type: text
          example:
            moderator_uid: tJMPKzrR4ig3Yejc7cRQGSl8URr1
            author_uid: tJMPKzrR4ig3Yejc7cRQGSl8URr1
            campaign_uuid:
            heading: Overarching quiz series banner
            questions:
              - title: Question 1
                caption: This is the first question
                external_link:
                  external_link_text: Learn more
                  external_link_url: https://www.figure1.com
                media:
                  - filename: 33468feea4872dbaab01b8f383ef83606c82d1dce0cf5393fb4044c026ef5071.png
                    type: image
                    width: 3000
                    height: 2002
                question_answer_details: First question answer details
                question_options:
                  - text: Option A
                    is_answer: True
                  - text: Option B
                    is_answer: False
                  - text: Option C
                    is_answer: False
                isi:
                  isi_link: http://www.figure1.com
                  isi_text: Full Prescribing Information, including Boxed WARNING
                  isi_embedded_content_link: http://www.figure1.com
                references: sample references
              - title: Question 2
                caption: This is the second question
                media:
                  - filename: 33468feea4872dbaab01b8f383ef83606c82d1dce0cf5393fb4044c026ef5071.png
                    type: image
                    width: 3000
                    height: 2002
                question_answer_details: Second question answer details
                question_options:
                  - text: Option 1
                    is_answer: True
                  - text: Option 2
                    is_answer: False
            conclusion:
              caption: This is the end of the quiz series
              external_link:
                external_link_text: Learn more
                external_link_url: https://www.figure1.com
              isi:
                isi_link: http://www.figure1.com
                isi_text: Full Prescribing Information, including Boxed WARNING
                isi_embedded_content_link: http://www.figure1.com
            sponsored_content:
              sponsored_text: Sponsored Content
              disclosure_text: This case is sponsored
              job_code: 123
            features:
              comments_enabled: True
              comment_queue_enabled: False
              reactions_enabled: True
              save_enabled: True
              share_enabled: True
              zoom_enabled: True
            feed_card:
              feed_card_type: HIGHLIGHT
              feed_card_label: Label
              feed_card_title: Common upstream regulators of MCL-1
              button_text: Start Activity
              colour: 236B84
              feed_card_media:
                filename: 33468feea4872dbaab01b8f383ef83606c82d1dce0cf5393fb4044c026ef5071.png
                type: image
                width: 3000
                height: 2002
            settings:
              tactic_priority: 1
              name: New Tactic
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

    if 'moderator_uid' not in request.json:
        return abort(422, 'missing moderator_uid')
    if 'author_uid' not in request.json:
        return abort(422, 'missing author_uid')
    if 'campaign_uuid' not in request.json:
        return abort(422, 'missing campaign_uuid')
    if request.method == 'PUT' and not case_uuid:
        return abort(422, 'missing case_uuid')

    moderator_uid = request.json.get('moderator_uid')

    res = create_update_quiz_series(moderator_uid=moderator_uid,
                                    case_uuid=case_uuid,
                                    data=request.json)
    task = res.pop('task')
    task.apply()

    return jsonify(res), 200


@bp.route('/case/clinical_moments', methods=['POST'])
@bp.route('/case/clinical_moments/<case_uuid>', methods=['PUT'])
@jwt_required()
def create_update_clinical_moments_endpoint(case_uuid=None):
    """
    Create or update a clinical moments tactic
    ---
    tags:
     - campaigns
    produces:
      - application/json
    parameters:
      - name: case_uuid
        in: path
        type: string
        required: false
        description: The uuid of the case to update.  Required for PUT only.
      - name: body
        in: body
        required: true
        schema:
          properties:
            moderator_uid:
              type: string
              required: true
              description: The uid of the moderator creating the case
            campaign_uuid:
              type: string
              description: The campaign for the tactic
            author_uid:
              type: string
              required: true
              description: The uid of the author that the case will be attributed to
            slides:
              type: array
              items: object
              required: true
              properties:
                content_type:
                  type: string
                  enum: ['FEED_CARD', 'COVER', 'CONTENT', 'QUIZ']
                title:
                  type: string
                  required: false
                caption:
                  type: string
                  required: false
                media:
                  type: array
                  items: object
                  required: false
                  properties:
                    filename:
                      type: string
                    type:
                      type: string
                    width:
                      type: int
                    height:
                      type: int
                question_answer_details:
                  type: string
                  required: false
                question_options:
                  type: array
                  items: object
                  required: false
                  description: The selectable choices for the quiz question.  If no quiz are marked as is_answer=True
                    the created case will be a poll instead of a quiz
                  properties:
                    text:
                      type: string
                    is_answer:
                      type: boolean
                external_link:
                  type: object
                  required: false
                  description: An external link to show in the question.  If null, no link will be shown.
                  properties:
                    external_link_text:
                      type: string
                    external_link_url:
                      type: string
                isi:
                  type: object
                  required: false
                  description: ISI information for the case.  If null, ISI is not shown.
                  properties:
                    isi_link:
                      type: string
                    isi_text:
                      type: string
                    isi_embedded_content_link:
                      type: string
                button_text:
                  type: string
                button_link:
                  type: string
                references:
                  type: string
                  required: false
            sponsored_content:
              type: object
              required: false
              description: The sponsor details.  If null, the case is not sponsored
              properties:
                sponsored_text:
                  type: string
                disclosure_text:
                  type: string
                job_code:
                  type: string
            features:
              type: object
              required: false
              description: Optional behaviours to enable/disable on the case.
              properties:
                comments_enabled:
                  type: boolean
                comment_queue_enabled:
                  type: boolean
                reactions_enabled:
                  type: boolean
                save_enabled:
                  type: boolean
                share_enabled:
                  type: boolean
                zoom_enabled:
                  type: boolean
            settings:
              type: object
              required: true
              properties:
                tactic_priority:
                  type: int
                  description: A value between 1 and 3 which influences the ordering of the tactic within user feeds.
                name:
                  type: text
          example:
            moderator_uid: tJMPKzrR4ig3Yejc7cRQGSl8URr1
            author_uid: tJMPKzrR4ig3Yejc7cRQGSl8URr1
            campaign_uuid:
            slides:
              - content_type: FEED_CARD
                feed_card_label: Grand Rounds
                feed_card_title: Chronic Myeloid Leukemia (CML)
                colour: 5A3D93
                button_text: Test your knowledge now
                feed_card_media:
                  filename: 33468feea4872dbaab01b8f383ef83606c82d1dce0cf5393fb4044c026ef5071.png
                  type: image
                  width: 3000
                  height: 2002
              - content_type: COVER
                title: Chronic Myeloid Leukemia (CML)
                caption: This is a clinical moments activity.
                feed_card_label: Grand Rounds
                media:
                  - filename: 33468feea4872dbaab01b8f383ef83606c82d1dce0cf5393fb4044c026ef5071.png
                    type: image
                    width: 3000
                    height: 2002
              - content_type: QUIZ
                title: Question
                caption: This is a quiz question
                media:
                  - filename: 33468feea4872dbaab01b8f383ef83606c82d1dce0cf5393fb4044c026ef5071.png
                    type: image
                    width: 3000
                    height: 2002
                question_answer_details: Second question answer details
                question_options:
                  - text: Option 1
                    is_answer: True
                  - text: Option 2
                    is_answer: False
                references: sample references
              - content_type: CONTENT
                title: Conclusion
                caption: The end of the clinical moments
                external_link:
                  external_link_text: Learn more
                  external_link_url: https://www.figure1.com
                media:
                  - filename: 33468feea4872dbaab01b8f383ef83606c82d1dce0cf5393fb4044c026ef5071.png
                    type: image
                    width: 3000
                    height: 2002
            sponsored_content:
              sponsored_text: Sponsored Content
              disclosure_text: This case is sponsored
              job_code: 123
            features:
              comments_enabled: True
              comment_queue_enabled: False
              reactions_enabled: True
              save_enabled: True
              share_enabled: True
              zoom_enabled: True
            settings:
              tactic_priority: 1
              name: New Tactic
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

    if 'moderator_uid' not in request.json:
        return abort(422, 'missing moderator_uid')
    if 'author_uid' not in request.json:
        return abort(422, 'missing author_uid')
    if 'campaign_uuid' not in request.json:
        return abort(422, 'missing campaign_uuid')
    if request.method == 'PUT' and not case_uuid:
        return abort(422, 'missing case_uuid')

    moderator_uid = request.json.get('moderator_uid')

    res = create_update_clinical_moments(moderator_uid=moderator_uid,
                                         case_uuid=case_uuid,
                                         data=request.json)
    task = res.pop('task')
    task.apply()

    return jsonify(res), 200


@bp.route('/case/cme', methods=['POST'])
@bp.route('/case/cme/<case_uuid>', methods=['PUT'])
@jwt_required()
def create_update_cme_endpoint(case_uuid=None):
    """
    Create or update a cme tactic
    ---
    tags:
     - campaigns
    produces:
      - application/json
    parameters:
      - name: case_uuid
        in: path
        type: string
        required: false
        description: The uuid of the case to update.  Required for PUT only.
      - name: body
        in: body
        required: true
        schema:
          properties:
            moderator_uid:
              type: string
              required: true
              description: The uid of the moderator creating the case
            campaign_uuid:
              type: string
              description: The campaign for the tactic
            author_uid:
              type: string
              required: true
              description: The uid of the author that the case will be attributed to
            cme1_credits:
              type: float
              required: true
            passing_score:
              type: int
              required: true
            slides:
              type: array
              items: object
              required: true
              properties:
                content_type:
                  type: string
                  enum: ['FEED_CARD', 'COVER', 'CONTENT', 'QUIZ']
                feed_card_type:
                  type: string
                  enum: ['HIGHLIGHT', 'CME_HUB']
                section:
                  type: string
                  enum: ['FRONT_MATTER', 'PRE_TEST', 'ACTIVITY', 'POST_TEST', 'SURVEY']
                feed_card_label:
                  type: string
                  required: false
                feed_card_title:
                  type: string
                  required: false
                title:
                  type: string
                  required: false
                caption:
                  type: string
                  required: false
                heading:
                  type: string
                  required: false
                media:
                  type: array
                  items: object
                  required: false
                  properties:
                    filename:
                      type: string
                    type:
                      type: string
                    width:
                      type: int
                    height:
                      type: int
                question_answer_details:
                  type: string
                  required: false
                question_options:
                  type: array
                  items: object
                  required: false
                  description: The selectable choices for the quiz question.  If no quiz are marked as is_answer=True
                    the created case will be a poll instead of a quiz
                  properties:
                    text:
                      type: string
                    is_answer:
                      type: boolean
                    is_free_form:
                      type: boolean
                external_link:
                  type: object
                  required: false
                  description: An external link to show in the question.  If null, no link will be shown.
                  properties:
                    external_link_text:
                      type: string
                    external_link_url:
                      type: string
                isi:
                  type: object
                  required: false
                  description: ISI information for the case.  If null, ISI is not shown.
                  properties:
                    isi_link:
                      type: string
                    isi_text:
                      type: string
                    isi_embedded_content_link:
                      type: string
                button_text:
                  type: string
                button_link:
                  type: string
                references:
                  type: string
                  required: false
            sponsored_content:
              type: object
              required: false
              description: The sponsor details.  If null, the case is not sponsored
              properties:
                sponsored_text:
                  type: string
                disclosure_text:
                  type: string
                job_code:
                  type: string
            features:
              type: object
              required: false
              description: Optional behaviours to enable/disable on the case.
              properties:
                comments_enabled:
                  type: boolean
                comment_queue_enabled:
                  type: boolean
                reactions_enabled:
                  type: boolean
                save_enabled:
                  type: boolean
                share_enabled:
                  type: boolean
                zoom_enabled:
                  type: boolean
            settings:
              type: object
              required: true
              properties:
                tactic_priority:
                  type: int
                  description: A value between 1 and 3 which influences the ordering of the tactic within user feeds.
                name:
                  type: text
          example:
            moderator_uid: tJMPKzrR4ig3Yejc7cRQGSl8URr1
            author_uid: tJMPKzrR4ig3Yejc7cRQGSl8URr1
            campaign_uuid:
            cme1_credits: 0.25
            passing_score: 3
            slides:
              - content_type: FEED_CARD
                feed_card_type: HIGHLIGHT
                feed_card_label: CME
                feed_card_title: Chronic Myeloid Leukemia (CML)
                colour: 8E596D
                heading: Start activity to earn 0.25 Category 1 Credits
                feed_card_media:
                  filename: 33468feea4872dbaab01b8f383ef83606c82d1dce0cf5393fb4044c026ef5071.png
                  type: image
                  width: 3000
                  height: 2002
              - content_type: CME_HUB_CARD
                title: Chronic Myeloid Leukemia (CML)
                heading: 0.25 CME credits
                media:
                  - filename: 33468feea4872dbaab01b8f383ef83606c82d1dce0cf5393fb4044c026ef5071.png
                    type: image
                    width: 3000
                    height: 2002
              - content_type: CONTENT
                section: FRONT_MATTER
                caption: Front matter text
                section: FRONT_MATTER
                button_text: Take the CME pre-test
              - content_type: QUIZ
                section: PRE_TEST
                caption: How confident are you in your ability to manage alpha-1 antitrypsin deficiency (AATD)?
                question_options:
                  - text: Not confident at all
                    is_answer: False
                  - text: Moderately confident
                    is_answer: False
                  - text: Pretty much confident
                    is_answer: False
              - content_type: QUIZ
                section: PRE_TEST
                caption: Sample Question 2
                question_options:
                  - text: Option A
                    is_answer: False
                  - text: Option B
                    is_answer: False
              - content_type: QUIZ
                section: PRE_TEST
                caption: Sample question 3
                question_options:
                  - text: Option A
                    is_answer: False
                  - text: Option B
                    is_answer: False
                  - text: Option C
                    is_answer: False
              - content_type: COVER
                section: ACTIVITY
                title: Chronic Myeloid Leukemia (CML)
                caption: This is a CME activity.
                feed_card_label: CME
                button_text: Start activity
                heading: Start activity to earn 0.25 Category 1 Credits
                media:
                  - filename: 33468feea4872dbaab01b8f383ef83606c82d1dce0cf5393fb4044c026ef5071.png
                    type: image
                    width: 3000
                    height: 2002
              - content_type: CONTENT
                section: ACTIVITY
                caption: A 56-year-old male with chronic myeloid leukemia (CML) has had stable molecular remission (MR)
                  4.0 for 1 year. He was initially diagnosed with chronic-phase CML with a high-risk Sokal score 4 years
                  ago during a workup for abdominal pain. After 2 years on imatinib, his medication was switched to a
                  second-generation tyrosine kinase inhibitor (2G-TKI) because of disease transformation to accelerated
                  phase. He has been on the 2G-TKI ever since.
                references: sample references
              - content_type: CONTENT
                section: ACTIVITY
                caption: A 56-year-old male with chronic myeloid leukemia (CML) has had stable molecular remission (MR)
                  4.0 for 1 year. He was initially diagnosed with chronic-phase CML with a high-risk Sokal score 4 years
                  ago during a workup for abdominal pain. After 2 years on imatinib, his medication was switched to a
                  second-generation tyrosine kinase inhibitor (2G-TKI) because of disease transformation to accelerated
                  phase. He has been on the 2G-TKI ever since.
              - content_type: CONCLUSION
                section: ACTIVITY
                caption: Conclusion text
                button_text: Take the CME post-test
              - content_type: QUIZ
                section: POST_TEST
                caption: Sample Question 1
                question_options:
                  - text: Option A
                    is_answer: True
                  - text: Option B
                    is_answer: False
              - content_type: QUIZ
                section: POST_TEST
                caption: Sample Question 2
                question_options:
                  - text: Option A
                    is_answer: True
                  - text: Option B
                    is_answer: False
              - content_type: QUIZ
                section: POST_TEST
                caption: Sample Question 3
                question_options:
                  - text: Option A
                    is_answer: True
                  - text: Option B
                    is_answer: False
                  - text: Option C
                    is_answer: False
              - content_type: QUIZ
                section: SURVEY
                caption: Did you enjoy this CME Activity
                question_options:
                  - text: Yes
                    is_answer: False
                  - text: No
                    is_answer: False
              - content_type: QUIZ
                section: SURVEY
                caption: What is your favourite colour?
                question_options:
                  - text: Red
                    is_answer: False
                  - text: Green
                    is_answer: False
                  - text: Blue
                    is_answer: False
              - content_type: QUIZ
                section: SURVEY
                caption: What is your favourite colour?
                question_options:
                  - text: Red
                    is_answer: False
                  - text: Green
                    is_answer: False
                  - text: Blue
                    is_answer: False
            sponsored_content:
              sponsored_text: Sponsored Content
              disclosure_text: This case is sponsored
              job_code: 123
            features:
              comments_enabled: True
              comment_queue_enabled: False
              reactions_enabled: True
              save_enabled: True
              share_enabled: True
              zoom_enabled: True
            settings:
              tactic_priority: 1
              name: New Tactic
            certificates:
              - filename: certificate1.docx
                path: cases/certificate-templates/unassigned/certificate1.docx
                profession_tree_uuids:
                  - 7275dbe6-7416-4352-b2d9-ebf3d580cc0d
                  - 9b26f97b-9de0-443b-823d-fd599efcb1c3
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

    if 'moderator_uid' not in request.json:
        return abort(422, 'missing moderator_uid')
    if 'author_uid' not in request.json:
        return abort(422, 'missing author_uid')
    if 'campaign_uuid' not in request.json:
        return abort(422, 'missing campaign_uuid')
    if request.method == 'PUT' and not case_uuid:
        return abort(422, 'missing case_uuid')

    moderator_uid = request.json.get('moderator_uid')

    res = create_update_cme(moderator_uid=moderator_uid,
                            case_uuid=case_uuid,
                            data=request.json)
    task = res.pop('task')
    task.apply()
    return jsonify(res), 200


@bp.route('/case/promo_card', methods=['POST'])
@bp.route('/case/promo_card/<case_uuid>', methods=['PUT'])
@jwt_required()
def create_update_promo_card_endpoint(case_uuid=None):
    """
    Create or update a promo card
    ---
    tags:
     - campaigns
    produces:
      - application/json
    parameters:
      - name: case_uuid
        in: path
        type: string
        required: false
        description: The uuid of the case to update.  Required for PUT only.
      - name: body
        in: body
        required: true
        schema:
          properties:
            moderator_uid:
              type: string
              required: true
              description: The uid of the moderator creating the case
            author_uid:
              type: string
              required: false
              description: The uid of the author that the case will be attributed to.  Optional, if missing the
                moderator will be assigned as the author
            campaign_uuid:
              type: string
              description: The campaign for the tactic
            title:
              type: string
              required: true
              description: The title of the promo card
            caption:
              type: string
              required: true
              description: The body text of the promo card
            button_text:
              type: boolean
              required: true
              description: The text to display on the clickable button
            button_url:
              type: boolean
              required: true
              description: The url to open when the button is clicked
            job_code:
              type: string
              required: false
              description: The optional job code.
            features:
              type: object
              required: true
              properties:
                dismiss_button:
                  type: boolean
                  required: true
                  description: True if the promo card has a dismiss button
                dismiss_on_click:
                  type: boolean
                  required: true
                  description: True if the promo card will be dismissed on click
                show_in_web:
                  type: boolean
                  required: true
                  description: True if the promo card should be shown on the Web client
                show_in_mobile:
                  type: boolean
                  required: true
                  description: True if the promo card should be shown on Mobile clients
            settings:
              type: object
              required: false
              properties:
                tactic_priority:
                  type: int
                  description: A value between 1 and 3 which influences the ordering of the tactic within user feeds.
                name:
                  type: text
          example:
            moderator_uid:
            campaign_uuid:
            title: Sample title
            caption: Sample caption
            button_text:  Click here
            button_url:  https://www.figure1.com
            job_code:
            features:
              dismiss_button: true
              dismiss_on_click: false
              show_in_web:  true
              show_in_mobile:  true
            settings:
              tactic_priority: 1
              name: New Promo Card
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

    if 'moderator_uid' not in request.json:
        return abort(422, 'missing moderator_uid')
    if 'campaign_uuid' not in request.json:
        return abort(422, 'missing campaign_uuid')
    if request.method == 'PUT' and not case_uuid:
        return abort(422, 'missing case_uuid')

    moderator_uid = request.json.get('moderator_uid')

    res = create_promo_card(moderator_uid=moderator_uid,
                            case_uuid=case_uuid,
                            data=request.json)
    task = res.pop('task')
    task.apply()

    return jsonify(res), 200
