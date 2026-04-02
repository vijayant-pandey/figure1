import logging
import os

from flask import Blueprint, request, abort, current_app
from flask.json import jsonify
from flask_jwt_extended import jwt_required
from jsonschema import ValidationError

from figure1.common.types import UserVerificationUpdate, VerificationType
from figure1.common.utils import s3_utils
from figure1.exceptions import VerificationException, UserNotFound, UserError
from .verify import verify_user, save_comms_for_user, parse_npi_data, get_upload_url

logger = logging.getLogger(__name__)
bp = Blueprint('pro_verification_endpoint', __name__)


@bp.errorhandler(VerificationException)
def handle_general_verification_error(e):
    logger.exception("Caught verification error")
    return jsonify(e), e.rc


@bp.errorhandler(ValidationError)
def handle_verification_validation(e):
    logger.exception("Post body validation failed")
    return jsonify(msg="Post body failed to validate"), 422


@bp.errorhandler(UserNotFound)
def handle_verification_user_not_found(e):
    logger.exception("Unable to find user to verify")
    return jsonify(e.as_dict()), e.rc


@bp.errorhandler(UserError)
def handle_user_error(e):
    logger.exception("%s", e.msg)
    return jsonify(e.as_dict()), e.rc


@bp.route('/verification/<user_uid>/upload', methods=['POST'])
@jwt_required()
def upload_verification_picture_old(user_uid):
    """
    Submit a photo verification request for a user.
    Deprecated before v9.0.  Replaced by /verification/<user_uid>/photo/<country_uuid>/<state_uuid>
    ---
    tags:
     - deprecated
    consumes:
      - multipart/form-data
    produces:
      - application/json
    parameters:
      - name: user_uid
        in: path
        type: string
        required: true
      - name: picture
        in: formData
        type: file
    responses:
      default:
        description: Unexpected Failure
      '400':
        description: User not found
      '202':
        description: Verification submitted successfully
      '200':
        description: Verification request already exists for user
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    return upload_verification_picture(user_uid=user_uid, country_uuid=None)


@bp.route('/verification/<user_uid>/photo/<country_uuid>', methods=['POST'])
@jwt_required()
def upload_verification_picture(user_uid, country_uuid):
    """
    Submit a photo verification request for a user.
    Deprecated as of v9.10.  Replaced by /verification with method='photo'
    ---
    tags:
     - deprecated
    consumes:
      - multipart/form-data
    produces:
      - application/json
    parameters:
      - name: user_uid
        in: path
        type: string
        required: true
      - name: country_uuid
        in: path
        type: string
        required: true
      - name: picture
        in: formData
        type: file
    responses:
      default:
        description: Unexpected Failure
      '400':
        description: User not found
      '202':
        description: Verification submitted successfully
      '200':
        description: Verification request already exists for user
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
    if file.filename == '':
        abort(400)

    temp_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], user_uid)
    url = s3_utils.upload_image_to_s3(file=file, upload_dir=f'users/verification/{user_uid}', temp_dir=temp_dir)

    if 'error' in url:
        return jsonify({'error': url['error']}), 500
    update = UserVerificationUpdate(method=VerificationType.PHOTO,
                                    user_uid=user_uid,
                                    photos=[url['photo_url']],
                                    license_country_code=country_uuid)
    res = verify_user(update)
    task = res.pop('task')
    if task:
        task.apply_async()
    return jsonify(res), 200


@bp.route('/verification', methods=["POST"])
@jwt_required()
def submit_verification():
    """
    Submit a verification request for a user.

    Required parameters:
     - user_uid:  The user uid to submit the verification for.
     - method:  ['npi', 'license', 'institutional_email', 'photo'].  The type of verification which is being submitted.

    For 'npi' method:
     - npi_number:  The user's npi number.
     - graduation_year:  The graduation year for the user. (optional)
     - license_school_code:  The school code for the user. (optional)

    For 'license' method:
     - license_number:  The medical license number for the user.
     - license_country_code:  The country uuid for the users medical license.
     - license_state_code:  The state uuid for the user's medical license. (optional)
     - graduation_year:  The graduation year for the user.
     - license_school_code:  The school code for the user.

    For 'institutional_email' method:
     - institutional_email: The institutional email address of the user
     - license_country_code:  The country uuid for the users medical license. (optional)

    For 'photo' method:
     - photos: The verification photo(s) for the user.  Up to 4 are allowed.
    ---
    tags:
     - verification
    produces:
      - application/json
    parameters:
      - name: body
        in: body
        required: true
        schema:
          required:
            - user_uid
            - method
          properties:
            user_uid:
              type: string
            method:
              type: string
              enum: ['npi', 'license', 'institutional_email']
            npi_number:
              type: string
            graduation_location:
              type: string
            graduation_year:
              type: int
            license_school_code:
              type: string
            license_number:
              type: string
            license_country_code:
              type: string
            license_state_code:
              type: string
            institutional_email:
              type: string
            photos:
              type: array
              description: A list of the urls for verification photo(s)
              items: str
          example:
            user_uid: rVfnkWNMQmYWZ7T5bojk4UiK3ek2
            method: npi
            npi_number: 1234567893
            graduation_year: 2019
            license_school_code: 445fd35b-76f5-47fd-b809-b7cbec88efbd
    responses:
      default:
        description: Unexpected Failure
      '400':
        description: User not found
      '202':
        description: Verification submitted successfully
      '200':
        description: Verification request already exists for user
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """

    update = UserVerificationUpdate.parse_obj(request.json)
    res = verify_user(update)
    task = res.pop('task')
    if task:
        task.apply_async(countdown=5)
    return jsonify(res), 202


@bp.route('/verification/<user_uid>/communication', methods=['POST'])
@jwt_required()
def save_communication_method(user_uid):
    """
        Submit a verification request for a user.
        Body parameters:
         - user_uid:  The user uid to submit the verification for.
         - is_email: Boolean flag if a user prefers email communication from Comms team
         - is_push: Boolean flag if a user prefers a Push Message from Comms team
         - is_sms: Boolean flag if a user prefers an SMS message from Comms team
         - phone_number: The phone number we will use if SMS is requested
        ---
        tags:
         - verification
        produces:
          - application/json
        parameters:
          - name: user_uid
            in: path
            type: string
            required: true
          - name: body
            in: body
            required: true
            schema:
              required:
                - is_email
                - is_push
                - is_sms
                - phone_number
              properties:
                is_email:
                  type: boolean
                is_push:
                  type: boolean
                is_sms:
                  type: boolean
                phone_number:
                  type: string
              example:
                is_email: true
                is_push: true
                is_sms: true
                phone_number: "+19198887777"
        responses:
          default:
            description: Unexpected Failure
          '400':
            description: User not found
          '200':
            description: Communication Details Saved for User
        securityDefinitions:
          JWT:
            type: apiKey
            name: Authorization
            in: header
        security:
          - JWT: []
        """
    communication_request = request.json
    resp = save_comms_for_user(user_uid=user_uid, request=communication_request)
    if 'error' in resp:
        return jsonify(resp), 500
    return jsonify(resp), 200


@bp.route('/verification/parse_npi', methods=['POST'])
@jwt_required()
def parse_npi_endpoint():
    """
    Parses NPI data and returns the result
    ---
    tags:
     - verification
    produces:
      - application/json
    parameters:
      - name: body
        in: body
        required: true
    responses:
      default:
        description: Unexpected Failure
      '404':
        description: User not found
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    data = request.json
    res = parse_npi_data(data=data)
    return jsonify(res), 200


@bp.route('/verification/get_media_upload_url/<user_uid>', methods=['GET'])
@jwt_required()
def get_verification_media_upload_url(user_uid):
    """
    Returns a presigned url to upload a verification photo
    ---
    tags:
     - verification
    produces:
      - application/json
    parameters:
      - name: user_uid
        in: path
        type: string
        description:  The UID of the user submitting a verification photo
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
    res = get_upload_url(user_uid=user_uid)
    return jsonify(res), 200
