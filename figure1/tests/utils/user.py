import string
import uuid
from random import choice

from figure1.common.elasticsearch import add_or_update_user
from figure1.common.helpers import UserManagement, UserDocument
from figure1.common.models.db import SpecialtyTreeV2, UserVerification
from figure1.common.types import VerificationStatus, VerificationType
from figure1.common.models.db import SpecialtyTreeV2, UserSavedCase, CaseReaction, Comment
from figure1.common.types import Reaction, CommentState


def _random_string(length):
    letters = string.ascii_letters
    return ''.join(choice(letters) for _ in range(length))


def create_test_user(session, primary_specialty_uuid=None, specialties=[], verified=False):
    user = _random_string(16)
    if not primary_specialty_uuid:
        specialty = session.query(SpecialtyTreeV2).filter(SpecialtyTreeV2.specialty_v2_uuid.isnot(None)).first()
        primary_specialty_uuid = specialty.specialty_uuid
    mgmt = UserManagement(session=session, is_new_user=True, user_uid=f"test_{user}")
    mgmt.add_user(first_name=f"test_{user}_first_name",
                  last_name=f"test_{user}_last_name",
                  user_uuid=None,
                  email=f"test_{user}@figure1.com")
    mgmt.update_username(f"test_{user}")
    mgmt.set_primary_specialty(primary_specialty_uuid)
    if specialties:
        mgmt.set_specialties(specialties)
    if verified:
        v = UserVerification()
        v.user_uuid = mgmt.user.user_uuid
        v.verification_uuid = uuid.uuid4()
        v.verification_status = VerificationStatus.VERIFIED
        v.verification_type = VerificationType.INSTITUTIONAL_EMAIL
        v.institutional_email = f"test_inst_{user}@figure1.com"
        session.merge(v)
    session.commit()
    user_detail = UserDocument.elasticsearch_user_detail(user_uuid=str(mgmt.user.user_uuid), session=session)
    add_or_update_user(user_uuid=str(mgmt.user.user_uuid), user_detail=user_detail)
    return mgmt.user


def user_comment_case(session, content_uuid, user_uuid):
    c = Comment.create(author_uuid=user_uuid,
                       content_uuid=content_uuid,
                       text="Sample comment",
                       state=CommentState.APPROVED,
                       session=session)

    session.commit()


def user_save_case(session, case_uuid, user_uuid):
    s = UserSavedCase.create(case_uuid, user_uuid, session=session)

    session.commit()


def user_like_case(session, case_uuid, user_uuid):
    r = CaseReaction.set_reaction(case_uuid,
                                  user_uuid,
                                  Reaction.AGREE,
                                  session=session)

    session.commit()
