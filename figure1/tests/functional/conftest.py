import uuid
from random import choice

import pytest

from figure1.common.models.db.c_question_model import QAnswerOption
from figure1.configuration import es_settings
from figure1.common.elasticsearch import add_or_update_case
from figure1.common.models.db import Content
from figure1.common.models.db import DmdNpiInfo
from figure1.common.models.db import LegacyUser
from figure1.common.models.db import UserNPI
from figure1.common.models.db import LegacySpecialty
from figure1.common.models.db import MeshTerms
from figure1.common.models.db import Media
from figure1.common.models.db import MediaType
from figure1.common.models.db import Comment
from figure1.common.models.db import CommentReport
from figure1.common.models.db import School
from figure1.common.models.db import Country
from figure1.common.models.db import UserVerification
from figure1.common.models.db import Campaign
from figure1.common.models.db import SpecialtyTreeV2
from figure1.common.models.db import ProfessionV2
from figure1.common.models.db import Features
from figure1.common.models.db import LegacyCase
from figure1.common.models.db import TaggingState
from figure1.common.models.db import Case
from figure1.common.models.db import UserNotification
from figure1.common.models.db import ContentUpdate
from figure1.common.models.db import ContentTranslation
from figure1.common.models.db import Question
from figure1.common.helpers import UserManagement
from figure1.common.helpers import UserDocument
from figure1.common.helpers import GroupManagement
from figure1.common.helpers import CaseManagement
from figure1.common.models.db.c_content_update_model import ContentUpdateTranslations
from figure1.common.types import CaseState
from figure1.common.types import CommentState
from figure1.common.types import ReportReason
from figure1.common.types import CampaignState
from figure1.common.types import VerificationStatus
from figure1.common.types import VerificationType
from figure1.common.types import Locale
from figure1.common.types import GroupModel
from figure1.common.types.notification import UserNotificationState
from figure1.common.types.notification import UserNotificationType
from figure1.common.types.case import ContentUpdateType
from figure1.common.types.case import CaseClassification
from figure1.common.types.groups import GroupTypes
from figure1.pro.cases.casecme.casecme import create_new_question_set
from figure1.tests.utils.case import create_test_case
from figure1.tests.utils.user import create_test_user
from figure1.admin.iterable.domain import add_channel


@pytest.fixture(scope="module")
def create_group(load_db) -> GroupModel:
    session = load_db
    group_creator = create_test_user(session=session)
    g = GroupManagement.create_group(group_name='test_group_1_' + ''.join(choice("abcdefghijk") for _ in range(10)),
                                     group_label='test_group_label_1',
                                     group_type=GroupTypes.USER,
                                     group_creator_uuid=str(group_creator.user_uuid),
                                     session=session)
    assert isinstance(g, GroupModel)
    session.flush()
    yield g
    GroupManagement.delete_group(group_uuid=g.groupUuid, session=session)
    deleted_group = GroupManagement.get_group(group_uuid=g.groupUuid, session=session)
    assert deleted_group is None
    session.flush()


@pytest.fixture(scope="module")
def create_institutional_group(load_db) -> GroupModel:
    session = load_db
    g = GroupManagement.create_group(group_name='test_group_1',
                                     group_label='test_group_label_1',
                                     group_type=GroupTypes.INSTITUTIONAL,
                                     session=session)
    assert isinstance(g, GroupModel)
    session.flush()
    yield g
    GroupManagement.delete_group(group_uuid=g.groupUuid, session=session)
    deleted_group = GroupManagement.get_group(group_uuid=g.groupUuid, session=session)
    assert deleted_group is None
    session.flush()


@pytest.fixture()
def iterable_channels():
    add_channel(channel_id=10, channel_name='test_10')
    add_channel(channel_id=20, channel_name='test_20')


@pytest.fixture(scope="module")
def test_content_obj(load_db):
    session = load_db
    content = session.query(Content).filter(Content.title == 'Default case').first()
    return content


@pytest.fixture(scope="module")
def test_content(test_content_obj):
    return test_content_obj.as_dict()


@pytest.fixture(scope="module")
def test_physician_user(load_db, initialize_data):
    session = load_db
    for t in session.query(SpecialtyTreeV2) \
            .filter(SpecialtyTreeV2.profession_uuid.isnot(None), SpecialtyTreeV2.specialty_v2_uuid.isnot(None)) \
            .all():
        if t.profession:
            if t.profession.name == 'Physician':
                ob = t.as_object()
                user = create_test_user(session=session, primary_specialty_uuid=ob.treeUuid)
                return user.as_dict()


@pytest.fixture(scope="module")
def test_non_physician_user(load_db, initialize_data):
    session = load_db
    for t in session.query(SpecialtyTreeV2) \
            .filter(SpecialtyTreeV2.profession_uuid.isnot(None), SpecialtyTreeV2.specialty_v2_uuid.isnot(None)) \
            .all():
        if t.profession:
            if t.profession.name != 'Physician':
                ob = t.as_object()
                user = create_test_user(session=session, primary_specialty_uuid=ob.treeUuid)
                return user.as_dict()


@pytest.fixture(scope="module")
def test_user(load_db, initialize_data):
    session = load_db
    specialty = session.query(SpecialtyTreeV2).filter(SpecialtyTreeV2.specialty_v2_uuid.isnot(None)).limit(5).all()

    specialty_should_be = None
    primary_specialty = None
    specialties = []
    for i, s in enumerate(specialty):
        if i == 0:
            primary_specialty = s.specialty_uuid
        elif i == 2:
            primary_specialty = s.specialty_uuid
            specialty_should_be = s.as_object()
        else:
            specialties = [s.specialty_uuid]
    u = create_test_user(session=session, primary_specialty_uuid=primary_specialty, specialties=specialties)
    user_doc = UserDocument.user_detail(user_uuid=u.user_uuid, session=session)
    assert user_doc['primarySpecialty']['treeUuid'] == specialty_should_be.treeUuid
    session.commit()

    return u.as_dict()


@pytest.fixture()
def test_case_pending_approval(load_db, test_user, initialize_data):
    session = load_db
    case, content = create_test_case(
        author_uuid=test_user.get('userUuid'),
        is_paging_case=False,
        language=Locale.EN_US.code,
        title="Case Title",
        caption="Case Caption",
        state=CaseState.PENDING_APPROVAL,
        session=session)
    mt = MeshTerms()
    mt.case_uuid = case.case_uuid
    mt.approved_terms = ['Test']
    session.add(mt)
    Media.create(content_uuid=content.content_uuid,
                 media_type=MediaType.IMAGE,
                 filename="",
                 session=session)
    session.commit()
    add_or_update_case(case_uuid=str(case.case_uuid), session=session)
    return case


@pytest.fixture()
def approved_case_and_content(load_db, test_user):
    session = load_db
    case, content = create_test_case(
        author_uuid=test_user.get('userUuid'),
        is_paging_case=False,
        language='EN_US',
        title="Case Title",
        caption="Case Caption",
        state=CaseState.APPROVED,
        session=session)
    session.commit()

    yield case, content
    CaseManagement.delete_case(case_uuid=case.case_uuid, session=session)


@pytest.fixture()
def approved_post_and_content(load_db, test_user):
    session = load_db
    case, content = create_test_case(
        author_uuid=test_user.get('userUuid'),
        is_paging_case=False,
        language='EN_US',
        title="Case Title",
        caption="Case Caption",
        state=CaseState.APPROVED,
        case_classification=CaseClassification.NONMEDICAL,
        session=session)
    session.commit()

    yield case, content
    CaseManagement.delete_case(case_uuid=case.case_uuid, session=session)


@pytest.fixture()
def approved_anonymous_case_and_content_and_user(load_db):
    session = load_db
    user = create_test_user(session=session).as_dict()
    case, content = create_test_case(
        author_uuid=user.get('userUuid'),
        is_paging_case=False,
        language='EN_US',
        title="Case Title",
        caption="Case Caption",
        state=CaseState.APPROVED,
        is_anonymous=True,
        session=session)
    session.commit()

    yield case, content, user
    CaseManagement.delete_case(case_uuid=case.case_uuid, session=session)


@pytest.fixture()
def case_update(load_db, test_case_pending_approval):
    session = load_db
    case = Case.get_case(case_uuid=test_case_pending_approval.case_uuid, raise_exception=True)
    content = case.content[0]
    update = ContentUpdate.create(session=session,
                                  content_uuid=content.content_uuid,
                                  text="text",
                                  update_type=ContentUpdateType.UPDATE,
                                  skip_commit=True)
    session.commit()

    yield update


@pytest.fixture()
def users(load_db, approved_case_and_content):
    session = load_db
    users = []
    for _ in range(6):
        users.append(create_test_user(session))
    session.commit()

    yield users
    for each in users:
        mgmt = UserManagement(user_uuid=each.user_uuid, session=session)
        mgmt.delete_user()


@pytest.fixture()
def case_content_translation(load_db, test_case_pending_approval):
    session = load_db
    case_uuid = test_case_pending_approval.case_uuid
    content_uuid = test_case_pending_approval.content[0].content_uuid

    content_translation = ContentTranslation()
    content_translation.content_uuid = content_uuid
    content_translation.case_uuid = case_uuid
    content_translation.source_language = "EN_EN"
    content_translation.target_language = "PT_PT"
    content_translation.title = "title"
    content_translation.caption = "caption"

    session.add(content_translation)
    session.flush()

    yield content_translation


@pytest.fixture()
def case_update_translation(load_db, case_update):
    session = load_db
    update_translation = ContentUpdateTranslations()
    update_translation.update_uuid = case_update.update_uuid
    update_translation.language = "PT_PT"
    update_translation.text = "text"

    session.add(update_translation)
    session.flush()

    yield update_translation


@pytest.fixture()
def test_case_comment_queue(load_db, test_user, initialize_data):
    session = load_db
    case, content = create_test_case(
        author_uuid=test_user.get('userUuid'),
        is_paging_case=False,
        language=Locale.EN_US.code,
        title="Case Title",
        caption="Case Caption",
        state=CaseState.APPROVED,
        session=session)
    mt = MeshTerms()
    mt.case_uuid = case.case_uuid
    mt.approved_terms = ['Test']
    session.add(mt)
    f = Features.create_or_update(content_uuid=content.content_uuid,
                                  comment_queue_enabled=True,
                                  session=session)
    add_or_update_case(case_uuid=str(case.case_uuid), session=session)
    return case


@pytest.fixture()
def test_comment(load_db, test_content, test_user, initialize_data):
    session = load_db
    c = Comment.create(author_uuid=test_user.get('userUuid'),
                       content_uuid=test_content.get('contentUuid'),
                       text="Sample comment",
                       state=CommentState.APPROVED,
                       session=session)
    session.add(c)
    session.flush()
    return c


@pytest.fixture()
def test_comment_pending_approval(load_db, test_content, test_user, initialize_data):
    session = load_db
    c = Comment.create(author_uuid=test_user.get('userUuid'),
                       content_uuid=test_content.get('contentUuid'),
                       text="Sample comment in comment queue",
                       state=CommentState.PENDING_APPROVAL,
                       session=session)
    session.add(c)
    session.flush()
    return c


@pytest.fixture()
def test_reported_comment(load_db, test_comment, test_user, initialize_data):
    session = load_db
    test_comment.state = CommentState.REPORTED
    r = CommentReport.create_report(user_uuid=test_user.get('userUuid'),
                                    comment_uuid=test_comment.comment_uuid,
                                    report_reason=ReportReason.OTHER,
                                    text='This comment is bad',
                                    session=session)
    session.add(r)
    session.flush()
    return test_comment


@pytest.fixture()
def test_country(load_db):
    session = load_db
    c = Country.create_or_update(name="Test country",
                                 code="TC",
                                 type="Country",
                                 path_str="testcountry",
                                 alpha_3='TCO',
                                 session=session)
    session.add(c)
    session.flush()
    return c


@pytest.fixture()
def usa_country(load_db):
    session = load_db
    c = Country.create_or_update(name="United States",
                                 code="US",
                                 type="Country",
                                 path_str="us",
                                 alpha_3='USA',
                                 session=session)
    session.add(c)
    session.flush()
    return c


@pytest.fixture()
def test_state(load_db):
    session = load_db
    c = Country.create_or_update(name="Test state",
                                 code="TS",
                                 type="State",
                                 path_str="testcountry.teststate",
                                 alpha_3='TST',
                                 session=session)
    session.add(c)
    session.flush()
    return c


@pytest.fixture()
def test_school(load_db, test_country):
    session = load_db
    prof_uuid = session.query(ProfessionV2.specialty_uuid).first()
    s = School.create_or_update(name="Test school",
                                country_uuid=test_country.country_uuid,
                                subdivision_uuid=test_country.country_uuid,
                                abbreviation="TSCHO",
                                profession_uuid=prof_uuid[0],
                                session=session)
    session.add(s)
    session.commit()
    return s


@pytest.fixture()
def test_user_pending_verification(load_db, initialize_data):
    session = load_db
    user = create_test_user(session=session)

    v = UserVerification()
    v.user_uuid = user.user_uuid
    v.verification_uuid = uuid.uuid4()
    v.verification_status = VerificationStatus.PENDING_MANUAL_VERIFICATION
    v.verification_type = VerificationType.LICENSE
    session.add(v)
    session.commit()

    return user


@pytest.fixture()
def test_campaign(load_db, test_user, initialize_data):
    session = load_db
    c = Campaign()
    c.campaign_uuid = uuid.uuid4()
    c.name = "Test Campaign"
    c.client_name = "Test Client"
    c.state = CampaignState.ACTIVE
    c.author_uuid = test_user.get('userUuid')
    session.add(c)
    session.commit()

    return c


@pytest.fixture()
def test_legacy_case(load_db, initialize_data):
    session = load_db
    lc = LegacyCase()
    lc.case_uuid = uuid.uuid4()
    lc.legacy_id = "5da5f5ba031f4e1d00032aed"
    lc.title = "Case Title"
    lc.caption = "Case Caption"
    lc.likes = 0
    lc.follows = 0
    lc.state = TaggingState.APPROVED
    session.add(lc)
    session.commit()
    return lc


@pytest.fixture()
def test_group_case(load_db, get_elasticsearch_client, test_user, create_group):
    session = load_db
    es = get_elasticsearch_client
    g = create_group
    case, content = create_test_case(author_uuid=test_user.get('userUuid'),
                                     is_paging_case=False,
                                     language=Locale.EN_US.code,
                                     title="Case Title",
                                     caption="Case Caption",
                                     state=CaseState.APPROVED,
                                     group_uuid=g.groupUuid,
                                     session=session)
    add_or_update_case(case_uuid=str(case.case_uuid), session=session)
    es.indices.refresh(index=es_settings.cases_alias)
    yield case, content
    case.group_uuid = None
    case.mark_deleted()
    session.add(case)
    session.flush()


@pytest.fixture()
def test_group_anonymous_case(load_db, get_elasticsearch_client, test_user, create_group):
    session = load_db
    es = get_elasticsearch_client
    g = create_group
    case, _ = create_test_case(author_uuid=test_user.get('userUuid'),
                               is_paging_case=False,
                               language=Locale.EN_US.code,
                               title="Case Title",
                               caption="Case Caption",
                               state=CaseState.APPROVED,
                               group_uuid=g.groupUuid,
                               is_anonymous=True,
                               session=session)
    add_or_update_case(case_uuid=str(case.case_uuid), session=session)
    es.indices.refresh(index=es_settings.cases_alias)
    yield case
    case.group_uuid = None
    case.mark_deleted()
    session.add(case)
    session.flush()


@pytest.fixture()
def test_institutional_group_case(load_db, get_elasticsearch_client, test_user, create_institutional_group):
    session = load_db
    es = get_elasticsearch_client
    g = create_institutional_group
    case, _ = create_test_case(author_uuid=test_user.get('userUuid'),
                               is_paging_case=False,
                               language=Locale.EN_US.code,
                               title="Case Title",
                               caption="Case Caption",
                               state=CaseState.APPROVED,
                               group_uuid=g.groupUuid,
                               session=session)
    add_or_update_case(case_uuid=str(case.case_uuid), session=session)
    es.indices.refresh(index=es_settings.cases_alias)
    yield case
    case.group_uuid = None
    case.mark_deleted()
    session.add(case)
    session.flush()


@pytest.fixture()
def test_notification(load_db, initialize_data, test_content):
    session = load_db
    u = create_test_user(session=session)
    n = UserNotification.create(user_uuid=u.user_uuid,
                                source_uuid=u.user_uuid,
                                case_uuid=test_content.get('caseUuid'),
                                session=session,
                                state=UserNotificationState.NEW,
                                notification_type=UserNotificationType.APPROVE)
    session.commit()
    return n


@pytest.fixture(scope="module")
def case_cme_questions_set(load_db):
    question_set_uuid = uuid.uuid4()
    questions = {
        "question_set_uuid": question_set_uuid,
        "question_set_label": "Name of question set",
        "questions": [{"question_text": "A question",
                       "question_type": "checkboxlist",
                       "question_label": "q1",
                       "display_order": 1,
                       "answer_groups": [{"answer_group_display_order": 1,
                                          "answer_group_heading": "Heading for this group",
                                          "answers": [{"answer_text": "first answer option",
                                                       "answer_display_order": 1,
                                                       "next_question_label": "q2"},
                                                      {"answer_text": "second answer option",
                                                       "answer_display_order": 2,
                                                       "next_question_label": "q2"}]},
                                         {"answer_group_display_order": 2,
                                          "answer_group_heading": "Heading for second group",
                                          "answers": [{"answer_text": "third answer",
                                                       "answer_display_order": 1,
                                                       "next_question_label": "q2"}]}]},

                      {"question_text": "Question 2",
                       "question_type": "freeform",
                       "question_label": "q2",
                       "display_order": 2,
                       "answer_groups": [{"answer_group_display_order": 1,
                                          "answer_group_heading": "This is another group",
                                          "answers": [{"answer_text": "It will not impact my practice",
                                                       "answer_display_order": 1,
                                                       "answer_suggested_text": "Type this for example"}]}]}]}
    session = load_db
    questions_set = create_new_question_set(questions, session=session)
    session.flush()
    yield questions_set

    for each_question in questions_set.questions:
        session.query(QAnswerOption).filter(QAnswerOption.question_uuid == each_question.questionUuid).delete()
        session.flush()

    session.query(Question).filter(Question.question_set_uuid == question_set_uuid).delete()
    session.flush()


@pytest.fixture()
def user_email_with_dmd_npi_record(load_db, test_user):
    session = load_db

    email = f"user@dmd.com"
    dmd_npi_info = DmdNpiInfo()
    dmd_npi_info.user_uuid = uuid.uuid4()
    dmd_npi_info.email = email
    dmd_npi_info.dmd_npi = 1234567893

    session.add(dmd_npi_info)
    session.commit()

    yield email
