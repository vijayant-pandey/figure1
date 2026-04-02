import uuid
from datetime import datetime

from figure1.common.models.db import Case
from figure1.common.models.db import Content
from figure1.common.models.db import CaseAuthor
from figure1.common.models.db import Features
from figure1.common.models.db import CaseSpecialtyV2
from figure1.common.models.db import SpecialtyV2
from figure1.common.types import ContentType
from figure1.common.types import CaseType
from figure1.common.types import FeedCardType
from figure1.common.types import Locale
from figure1.common.types import CaseState
from figure1.common.types import CaseClassification


def attach_case_specialties(case_uuid, specialty_uuids=None, session=None):
    specialty_list = []
    if specialty_uuids and isinstance(specialty_uuids, list):
        specialty_list = specialty_uuids
    else:
        q = session.query(SpecialtyV2).filter(SpecialtyV2.specialty_type == 'specialty').limit(100)
        for s in q.all():
            specialty_list.append(str(s.specialty_uuid))
    for s in specialty_list:
        c = CaseSpecialtyV2()
        c.case_uuid = case_uuid
        c.specialty_uuid = s
        session.add(c)
    session.commit()


def create_case_with_specialties(author_uuid,
                                 is_paging_case,
                                 language,
                                 state,
                                 session,
                                 case_type=CaseType.STATIC,
                                 specialty_uuids=None,
                                 is_anonymous=False,
                                 case_classification=CaseClassification.MEDICAL):
    Locale.get_from_code(language)
    c = Case()
    c.case_uuid = uuid.uuid4()
    c.is_paging_case = is_paging_case
    c.state = state
    c.case_type = case_type
    c.is_anonymous = is_anonymous
    c.case_classification = case_classification
    case = session.merge(c)
    session.flush()
    attach_case_specialties(case_uuid=str(c.case_uuid), specialty_uuids=specialty_uuids, session=session)
    CaseAuthor.create(case_uuid=case.case_uuid,
                      author_uuid=author_uuid,
                      skip_commit=True,
                      session=session)
    session.commit()
    return case


def create_test_case(author_uuid,
                     session,
                     is_paging_case=False,
                     language=Locale.EN_US.code,
                     title="Case Title",
                     caption='Case Caption',
                     state=CaseState.APPROVED,
                     case_type=CaseType.STATIC,
                     group_uuid=None,
                     rejection_reason=None,
                     published_at=None,
                     is_anonymous=False,
                     case_classification=CaseClassification.MEDICAL):
    language = Locale.get_from_code(language)

    c = Case()
    c.case_uuid = uuid.uuid4()
    c.is_paging_case = is_paging_case
    c.state = state
    c.case_type = case_type
    c.cme1_credits = 0
    c.language = language.code
    c.group_uuid = group_uuid
    c.rejection_reason = rejection_reason
    c.published_at = published_at
    c.is_anonymous = is_anonymous
    c.case_classification = case_classification
    case = session.merge(c)
    session.flush()
    attach_case_specialties(case_uuid=str(c.case_uuid), session=session)

    content = Content()
    content.content_uuid = uuid.uuid4()
    content.title = title
    content.caption = caption
    content.case_uuid = case.case_uuid
    content.feed_card_type = FeedCardType.BASIC
    content.is_feed_card = True
    content.content_type = ContentType.CONTENT
    content.display_order = 0
    cn = session.merge(content)
    session.flush()
    Features.set_default(content_uuid=cn.content_uuid,
                         session=session,
                         skip_commit=True)

    CaseAuthor.create(case_uuid=case.case_uuid,
                      author_uuid=author_uuid,
                      skip_commit=True,
                      session=session)
    session.commit()
    return case, cn
