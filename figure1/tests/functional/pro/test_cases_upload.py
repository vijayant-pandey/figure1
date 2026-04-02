import string
import uuid
from random import choice

from sqlalchemy import func

from figure1.common.helpers import UserManagement
from figure1.common.models.db import Case
from figure1.common.models.db import CaseSpecialtyV2
from figure1.common.models.db import Features
from figure1.common.models.db import Label
from figure1.common.models.db import Media
from figure1.common.models.db import MediaType
from figure1.common.models.db import QuestionOption
from figure1.common.models.db import QuestionVote
from figure1.common.models.db import SpecialtyV2
from figure1.common.models.db import SponsoredContent
from figure1.common.types import CaseState
from figure1.common.types import Locale
from figure1.common.types import MediaModelByCase
from figure1.common.types import CaseClassification
from figure1.tests.utils.case import create_test_case


def _random_string(length):
    letters = string.ascii_letters
    return ''.join(choice(letters) for _ in range(length))


def _create_user(session):
    user = _random_string(16)
    mgmt = UserManagement(user_uid=f'test_{user}', session=session, is_new_user=True)
    mgmt.add_user(first_name=f'test_{user}_first_name',
                  last_name=f'test_{user}_last_name',
                  email=f'test_{user}@figure1.com',
                  user_uuid=None,
                  legacy=False)
    mgmt.update_username(username=user)
    return mgmt.user


def _create_label(session, name=None):
    if not name:
        name = _random_string(16)
    return Label.create_or_update(name=name,
                                  kind=name.lower(),
                                  is_public=True,
                                  session=session)


def _create_specialty(session):
    name = _random_string(16)
    new = SpecialtyV2()
    new.name = name
    new.label = name
    new.is_valid_case_tag = True
    new.is_valid_interest = True
    new.specialty_type = 'specialty'
    new.specialty_uuid = uuid.uuid4()
    session.add(new)
    session.flush()
    return new


def _case_specialties(case_uuid, session):
    return session.query(SpecialtyV2) \
        .join(CaseSpecialtyV2, CaseSpecialtyV2.specialty_uuid == SpecialtyV2.specialty_uuid) \
        .filter(CaseSpecialtyV2.case_uuid == case_uuid, CaseSpecialtyV2.deleted_at.is_(None)).all()


def test_case_upload_endpoint(client, headers, load_db, create_group):
    session = load_db

    # Test case creation
    user = _create_user(session=session)
    user_uid = user.user_uid
    draft_uid = _random_string(16)
    title = _random_string(64)
    caption = _random_string(64)
    specialty = _create_specialty(session=session)
    label = _create_label(session=session)
    case_cme_label = _create_label(session=session, name="case_cme")
    image_filename = _random_string(16) + ".png"

    response = client.post(f'/pro/v1/draft/{user_uid}/{draft_uid}?state=draft', headers=headers, json={
        'title': title,
        'caption': caption,
        'media': [{
            'url': f"https://figure1-pro-dev.imgix.net/cases/images/{image_filename}",
            'filename': image_filename,
            'index': 0,
            'type': 'image'
        }],
        'specialty_uuids': [specialty.specialty_uuid],
        'label_uuids': [label.label_uuid],
        'paging': False,
        'request_help': True,
        'diagnosis': 'test diagnosis',
        'case_classification': 'nonmedical',
        'post_process_media': 'false',

    })
    assert response.status_code == 202
    new_case_uuid = response.json['caseUuid']
    case = session.query(Case).filter(Case.case_uuid == new_case_uuid).execution_options(populate_existing=True).one()
    assert case.state == CaseState.DRAFT
    assert case.is_paging_case is False
    assert case.request_help is True
    assert case.content[0].title == title
    assert case.content[0].caption == caption
    assert case.case_classification == CaseClassification.NONMEDICAL
    assert len(case.content[0].media)
    assert case.content[0].media[0].filename == image_filename
    assert case.content[0].media[0].display_order == 0
    assert case.content[0].media[0].type == MediaType.IMAGE
    assert case.labels[0].name == label.name
    assert len(case.labels) == 1
    specialties = _case_specialties(case_uuid=case.case_uuid, session=session)
    assert specialties[0].name == specialty.name
    assert len(specialties) == 1
    assert case.has_diagnosis is True
    assert case.diagnoses[0].text == 'test diagnosis'
    assert case.is_case_cme is False

    # Test case update
    title2 = _random_string(64)
    caption2 = _random_string(64)
    specialty2 = _create_specialty(session=session)
    label2 = _create_label(session=session)
    image_filename2 = _random_string(16) + ".png"

    response = client.post(f'/pro/v1/draft/{user_uid}/{draft_uid}?state=submit', headers=headers, json={
        'case_uuid': case.case_uuid,
        'title': title2,
        'caption': caption2,
        'media': [{
            'url': f"https://figure1-pro-dev.imgix.net/cases/images/{image_filename2}",
            'filename': image_filename2,
            'index': 0,
            'type': 'image'
        }],
        'specialty_uuids': [specialty2.specialty_uuid],
        'label_uuids': [label2.label_uuid],
        'paging': True,
        'request_help': False,
        'post_process_media': 'false',
    })
    r = response.json
    assert response.status_code == 202

    session.refresh(case)
    assert case.state == CaseState.PENDING_APPROVAL
    assert case.is_paging_case is True
    assert case.request_help is False
    assert case.content[0].title == title2
    assert case.content[0].caption == caption2
    assert len(case.content[0].media)
    assert case.content[0].media[0].filename == image_filename2
    assert case.content[0].media[0].display_order == 0
    assert case.content[0].media[0].type == MediaType.IMAGE
    assert case.labels[0].name == label2.name
    assert len(case.labels) == 1
    specialties = _case_specialties(case_uuid=case.case_uuid, session=session)
    assert specialties[0].name == specialty2.name
    assert len(specialties) == 1
    assert case.has_diagnosis is False
    assert len(case.diagnoses) == 0
    assert case.is_case_cme is False

    # Test anonymous case
    response = client.post(f'/pro/v1/draft/{user_uid}/anonymousDraftUid?state=submit', headers=headers, json={
        'title': 'title',
        'caption': 'caption',
        'media': [],
        'specialty_uuids': [specialty2.specialty_uuid],
        'label_uuids': [],
        'paging': False,
        'request_help': False,
        'group_uuid': None,
        'is_anonymous': True,
        'post_process_media': 'false',
    })
    assert response.status_code == 202

    case2_uuid = response.json['caseUuid']
    case2 = session.query(Case).filter(Case.case_uuid == case2_uuid).one()
    assert case2.content[0].features.public_notifications_enabled is False


def test_case_upload_with_mentions_in_caption(client, headers, load_db):
    session = load_db

    # Test user exists
    user = _create_user(session=session)
    user_uid = user.user_uid
    draft_uid = _random_string(16)
    title = _random_string(64)
    caption = f"test @{user.username} test"
    specialty = _create_specialty(session=session)
    label = _create_label(session=session)

    response = client.post(f'/pro/v1/draft/{user_uid}/{draft_uid}?state=draft', headers=headers, json={
        'title': title,
        'caption': caption,
        'media': [],
        'specialty_uuids': [specialty.specialty_uuid],
        'label_uuids': [label.label_uuid],
        'paging': False,
        'request_help': True,
        'diagnosis': 'test diagnosis',
        'post_process_media': 'false',

    })
    assert response.status_code == 202

    new_case_uuid = response.json['caseUuid']
    case = session.query(Case).filter(Case.case_uuid == new_case_uuid).one()
    assert case.content[0].caption == f"test [@{user.username}](/profile/{user.user_uuid}) test"

    # Test user does not exist
    title2 = _random_string(64)
    caption2 = "test @notfound test"
    specialty2 = _create_specialty(session=session)
    label2 = _create_label(session=session)

    response = client.post(f'/pro/v1/draft/{user_uid}/{draft_uid}?state=submit', headers=headers, json={
        'case_uuid': case.case_uuid,
        'title': title2,
        'caption': caption2,
        'media': [],
        'specialty_uuids': [specialty2.specialty_uuid],
        'label_uuids': [label2.label_uuid],
        'paging': True,
        'request_help': False,
        'post_process_media': 'false',
    })
    r = response.json
    assert response.status_code == 202

    session.refresh(case)
    assert case.content[0].caption == f"test [@notfound](/profile/user_not_found) test"

    # Test more than 1 users
    title3 = _random_string(64)
    caption3 = f"test @{user.username} test @{user.username}"
    specialty3 = _create_specialty(session=session)
    label3 = _create_label(session=session)

    response = client.post(f'/pro/v1/draft/{user_uid}/{draft_uid}?state=submit', headers=headers, json={
        'case_uuid': case.case_uuid,
        'title': title3,
        'caption': caption3,
        'media': [],
        'specialty_uuids': [specialty3.specialty_uuid],
        'label_uuids': [label3.label_uuid],
        'paging': True,
        'request_help': False,
        'post_process_media': 'false',
    })
    r = response.json
    assert response.status_code == 202

    session.refresh(case)
    assert case.content[0].caption == f"test [@{user.username}](/profile/{user.user_uuid}) " \
                                      f"test [@{user.username}](/profile/{user.user_uuid})"


def test_case_features(client, headers, load_db):
    session = load_db
    user = _create_user(session=session)
    case, content = create_test_case(caption="Caption",
                                     title="Title",
                                     language=Locale.EN_US.code,
                                     state=CaseState.APPROVED,
                                     is_paging_case=False,
                                     author_uuid=user.user_uuid,
                                     session=session)

    # Case is created with default features
    assert content.features.is_default
    assert content.features.comments_enabled
    assert content.features.reactions_enabled
    assert content.features.report_enabled
    assert content.features.share_enabled
    assert content.features.show_views

    # Can update features
    Features.create_or_update(content_uuid=content.content_uuid,
                              session=session,
                              comments_enabled=False,
                              reactions_enabled=False,
                              report_enabled=False,
                              share_enabled=False,
                              show_views=False)
    assert not content.features.is_default
    assert not content.features.comments_enabled
    assert not content.features.reactions_enabled
    assert not content.features.report_enabled
    assert not content.features.share_enabled
    assert not content.features.show_views

    # Can reset case to default features
    Features.set_default(content_uuid=content.content_uuid, session=session)
    default_feature_uuid1 = content.features_uuid
    assert content.features.is_default

    # Calling set_default again does not change the default row
    Features.set_default(content_uuid=content.content_uuid, session=session)
    default_feature_uuid2 = content.features_uuid
    assert default_feature_uuid1 == default_feature_uuid2


def test_case_sponsored_content(client, headers, load_db):
    session = load_db
    user = _create_user(session=session)
    case, content = create_test_case(caption="Caption",
                                     title="Title",
                                     language=Locale.EN_US.code,
                                     state=CaseState.APPROVED,
                                     is_paging_case=False,
                                     author_uuid=user.user_uuid,
                                     session=session)

    # Case is created without sponsored content
    assert content.sponsored_content is None

    # Can update sponsored content details
    s = SponsoredContent.create_or_update(content_uuid=content.content_uuid,
                                          session=session,
                                          sponsored_text="Sponsored by 123",
                                          disclosure_text="Sponsored disclosure text",
                                          job_code='123')

    assert content.sponsored_content.sponsored_text == "Sponsored by 123"
    assert content.sponsored_content.disclosure_text == "Sponsored disclosure text"
    assert content.sponsored_content.job_code == '123'

    # Can removed sponsored details
    SponsoredContent.delete(content_uuid=content.content_uuid,
                            session=session)
    assert content.sponsored_content is None
    assert s.is_deleted


def test_case_media(client, headers, load_db):
    session = load_db
    user = _create_user(session=session)
    case, content = create_test_case(caption="Caption",
                                     title="Title",
                                     language=Locale.EN_US.code,
                                     state=CaseState.APPROVED,
                                     is_paging_case=False,
                                     author_uuid=user.user_uuid,
                                     session=session)

    # Case is created without
    assert not content.media

    # Can update media
    m = Media.create(content_uuid=content.content_uuid,
                     media_type=MediaType.IMAGE,
                     filename="filename.jpg",
                     display_order=0,
                     session=session)
    session.commit()
    session.refresh(content)
    assert len(content.media) == 1
    assert content.media[0] == m

    m2 = Media.create(content_uuid=content.content_uuid,
                      media_type=MediaType.IMAGE_SERIES,
                      filename="filename2.zip",
                      display_order=1,
                      session=session)
    session.commit()
    session.refresh(content)
    assert len(content.media) == 2
    assert content.media[1] == m2

    case_model = Media.as_case_object(case_uuid=case.case_uuid, session=session)
    assert isinstance(case_model, MediaModelByCase)
    # Can delete media
    m2.mark_deleted()
    session.commit()
    assert len(content.media) == 1


def test_case_question(client, headers, load_db):
    session = load_db
    user = _create_user(session=session)
    case, content = create_test_case(caption="Caption",
                                     title="Title",
                                     language=Locale.EN_US.code,
                                     state=CaseState.APPROVED,
                                     is_paging_case=False,
                                     author_uuid=user.user_uuid,
                                     session=session)

    # Can create options
    QuestionOption.create_or_update(content_uuid=content.content_uuid,
                                    text="Option A",
                                    is_answer=False,
                                    session=session)
    QuestionOption.create_or_update(content_uuid=content.content_uuid,
                                    text="Option B",
                                    is_answer=False,
                                    session=session)
    QuestionOption.create_or_update(content_uuid=content.content_uuid,
                                    text="Option C",
                                    is_answer=False,
                                    session=session)
    options = session.query(QuestionOption) \
        .filter(QuestionOption.content_uuid == content.content_uuid,
                QuestionOption.deleted_at.is_(None)) \
        .order_by(QuestionOption.display_order) \
        .all()
    assert len(options) == 3
    assert options[0].text == "Option A"
    assert options[1].text == "Option B"
    assert options[2].text == "Option C"

    # Can update options
    QuestionOption.create_or_update(content_uuid=content.content_uuid,
                                    text="Option A Updated",
                                    is_answer=False,
                                    display_order=0,
                                    session=session)
    options = session.query(QuestionOption) \
        .filter(QuestionOption.content_uuid == content.content_uuid,
                QuestionOption.deleted_at.is_(None)) \
        .order_by(QuestionOption.display_order) \
        .all()
    assert len(options) == 3
    assert options[0].text == "Option A Updated"
    assert options[1].text == "Option B"
    assert options[2].text == "Option C"

    # Can delete options
    QuestionOption.delete(content_uuid=content.content_uuid,
                          display_order=1,
                          session=session)
    options = session.query(QuestionOption) \
        .filter(QuestionOption.content_uuid == content.content_uuid,
                QuestionOption.deleted_at.is_(None)) \
        .order_by(QuestionOption.display_order) \
        .all()
    assert len(options) == 2
    assert options[0].text == "Option A Updated"
    assert options[1].text == "Option C"

    # Can submit vote
    QuestionVote.create(question_option_uuid=options[1].question_option_uuid,
                        user_uuid=user.user_uuid,
                        session=session)
    votes = session.query(func.count(QuestionVote.question_option_uuid)) \
        .filter(QuestionVote.question_option_uuid == options[1].question_option_uuid) \
        .scalar()
    assert votes == 1
