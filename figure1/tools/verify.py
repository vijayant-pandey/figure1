import codecs
import logging
import os
import uuid
from uuid import UUID

import csv

from pydantic import ValidationError
from sqlalchemy.exc import DatabaseError
from sqlalchemy.orm import Session
from typing import Optional
from typing import List
from typing import Any

from figure1.common.helpers import VerificationManagement
from figure1.common.types.verification import DmdNpiDataModel
from figure1.common.utils import download_from_s3
from figure1.common.utils import dmd_data_path
from figure1.core import managed_session
from figure1.common.models.db import User
from figure1.common.models.db import UserState
from figure1.common.models.db import UserVerification
from figure1.common.models.db import UserNPI
from figure1.common.models.db import DmdNpiInfo
from figure1.common.types import VerificationStatus
from figure1.common.types import VerificationType
from figure1.common.types import UserNPIVerificationDocument
from figure1.exceptions import S3Error


def _handle_dmd_row(row, session):
    try:
        new_dmd_npi_info = DmdNpiInfo.create(dmd_data_model=DmdNpiDataModel(**row))
        session.merge(new_dmd_npi_info)
        return 1, None
    except ValidationError as e:
        error_message = f"Failed to validate row: {row}, error: {e}"
        logging.error(error_message)
        return 0, error_message


def _verify_user(user_uuid: str,
                 moderator: User,
                 verification_type: Optional[VerificationType],
                 session: Session) -> (bool, Optional[str]):
    user = User.get_user_by_uuid(user_uuid=user_uuid, session=session)
    if not user:
        logging.info("Could not find user %s", user_uuid)
        return False, "Could not find user"
    if not user.user_verification:
        if verification_type:
            uv = UserVerification()
            uv.verification_uuid = uuid.uuid4()
            uv.user_uuid = user.user_uuid
            uv.verification_type = VerificationType.LEGACY
            uv.verification_status = VerificationStatus.VERIFIED
            uv.last_modified_by = moderator.user_uuid
            session.add(uv)
        else:
            logging.info("User %s does not have a user verification entry", user_uuid)
            return False, "Missing verification entry"
    else:
        verify_mgmt = VerificationManagement(user_uuid=user_uuid,
                                             moderator_uuid=moderator.user_uuid,
                                             session=session)
        verify_mgmt.update_status(status=VerificationStatus.VERIFIED)

    if not user.user_state:
        us = UserState()
        us.user_uuid = user_uuid
        session.add(us)
    else:
        us = user.user_state
    us.block_legacy_migration = True

    return True, None


@managed_session
def bulk_verify(filename: str,
                moderator_uid: str,
                session: Session,
                verification_type: Optional[VerificationType] = None):
    """
    Loads a list of users from a file and marks them as verified.

    The expected file structure is a list of user_uuids, one per line

    If a verification_type is given, a verification record will be created for users who are missing one, with the
    given verification_type.  If missing, these users will report as errors instead.
    """

    def _validate_uuid(uuid: str) -> bool:
        try:
            UUID(uuid)
            return True
        except ValueError as e:
            logging.info("Invalid uuid format: %s", e)
            return False

    if not os.path.isfile(filename):
        return {"Error": f"Filename {filename} is not a file"}

    moderator = User.get_user_by_uid(user_uid=moderator_uid, session=session, raise_exception=True)
    count = 0
    errors = []

    with open(filename, mode='r', newline=None) as fn:
        for user_uuid in [line.strip() for line in fn]:
            if not _validate_uuid(user_uuid):
                errors.append({user_uuid: "Invalid UUID"})
                continue

            updated, reason = _verify_user(user_uuid=user_uuid,
                                           moderator=moderator,
                                           verification_type=verification_type,
                                           session=session)
            if updated:
                count += 1
            else:
                errors.append({user_uuid: reason})

            if not count % 500:
                session.commit()
                logging.info("Updated: %d", count)

    session.commit()

    return {"UpdatedCount": count,
            "ErrorCount": len(errors),
            "Errors": errors}


def _handle_npi_line(data_line: List[Any],
                     session: Session) -> (int, Optional[str]):
    """
    :return: The number of updated users, and an error message if an error occurred.
    """
    username = data_line.pop(0)
    email = data_line.pop(0)
    new_npi_number = data_line.pop(0)

    user = User.get_user_by_username(username=username, session=session, raise_exception=False)
    if not user:
        user = User.get_user_by_email(email=email, session=session, raise_exception=False)
    if not user:
        logging.info("User not found: username=%s email=%s", username, email)
        return 0, f"({username}, {email}): user not found"

    try:
        doc = UserNPIVerificationDocument.parse_obj({"npi": new_npi_number})
    except ValidationError:
        logging.info("Invalid npi number user %s", user.user_uuid)
        return 0, f"{user.user_uuid}: invalid npi number user"

    v = session.query(UserVerification) \
        .filter(UserVerification.user_uuid == user.user_uuid).one_or_none()
    if not v or v.verification_status != VerificationStatus.VERIFIED:
        logging.info("User is not verified %s", user.user_uuid)
        return 0, f"{user.user_uuid}: not verified"

    npi = session.query(UserNPI).filter(UserNPI.user_uuid == user.user_uuid).one_or_none()
    if npi:
        if str(npi.npi_number) == new_npi_number:
            return 0, None
        else:
            logging.info("User %s has an conflicting npi number", user.user_uuid)
            return 0, f"{user.user_uuid}: conflicting npi number old={npi.npi_number}, new={new_npi_number}"

    npi = UserNPI()
    npi.npi_uuid = uuid.uuid4()
    npi.user_uuid = user.user_uuid
    npi.npi_number = doc.npiNumber
    session.add(npi)
    return 1, None


@managed_session
def import_npi_numbers(filename: str, session: Session):
    """
    Imports a list of NPI numbers for users from a csv file

    The expected csv structure is
     Column 0: <username:str>
     Column 1: <email:str>
     Column 2: <npi_number:str>
    """
    count = 0
    errors = []

    if not os.path.isfile(filename):
        return {"Error": f"Filename {filename} is not a file"}

    with open(filename, mode='r', newline='') as fn:
        reader = csv.reader(fn)
        for line in reader:
            updated, error = _handle_npi_line(data_line=line, session=session)
            count += updated
            if error:
                errors.append(error)
            if count > 0 and not count % 500:
                session.commit()
                logging.info("Updated: %d", count)

    return {"UpdatedCount": count,
            "ErrorCount": len(errors),
            "Errors": errors}


@managed_session
def download_and_import_dmd_data_from_s3_to_database(filename: str, session=None):
    count = 0
    errors = []

    try:
        data = download_from_s3(path='/'.join([dmd_data_path, filename]))
    except S3Error as e:
        return {
            "error": e.msg,
        }

    for row in csv.DictReader(codecs.getreader('utf-8')(data['Body'])):
        updated_count, error = _handle_dmd_row(row, session)
        if error:
            errors.append(error)

        count += updated_count
        if count > 0 and not count % 500:
            session.flush()

    return {
        "ImportUpdatedCount": count,
        "ImportErrorCount": len(errors),
        "ImportErrors": errors,
    }
