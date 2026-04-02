import time
import uuid
from datetime import datetime, timedelta
from figure1.configuration import es_settings
from figure1.tests.utils.case import create_test_case
from figure1.common.types import CaseState
from figure1.notifications.iterable import CaseAggregateEvent
from figure1.common.iterable.scheduled_aggregations_tasks import user_case_comment_aggregate
from figure1.common.models.db import CaseAuthor, UserRecommendedCase
from figure1.pro.api.recommended_datafeed import get_recommended
from figure1.aggregation import generate_user_recommendations_task
from figure1.pro.comments.domain import do_post_comment
from figure1.common.elasticsearch import add_or_update_case
from figure1.store import Recommended


def _create_case(author_uuid, session):
    case, _ = create_test_case(
        author_uuid=author_uuid,
        is_paging_case=False,
        language='EN_US',
        title="Case Title",
        caption="Case Caption",
        state=CaseState.APPROVED,
        session=session)
    # Add case to elasticsearch
    session.commit()
    add_or_update_case(case_uuid=str(case.case_uuid), session=session)
    return case


def post_comment(user_uid, content_uuid, session, parent_uuid=None):
    c = do_post_comment(user_uid=user_uid,
                        content_uuid=content_uuid,
                        comment_text='test1',
                        session=session,
                        parent_comment_uuid=parent_uuid)
    return c


def test_comment_aggregate_by_case_author(load_db, test_content, test_physician_user):
    """
    Generate an aggregate and ensure the correct structure is returned
    :param load_db:
    :param test_content:
    :param test_physician_user:
    :return:
    """
    session = load_db
    case_uuid = test_content['caseUuid']
    physician = test_physician_user

    case_author = session.query(CaseAuthor.author_uuid).filter(CaseAuthor.case_uuid == case_uuid).first()
    phys_comment = post_comment(user_uid=physician['userUid'],
                                content_uuid=test_content['contentUuid'],
                                session=session)

    last_run_time = datetime.utcnow() - timedelta(days=1)

    agg = user_case_comment_aggregate(last_run_date=last_run_time, case_author_uuid=case_author[0], session=session)
    assert isinstance(agg[test_content['caseUuid']], CaseAggregateEvent)
    assert agg[test_content['caseUuid']].commentCount > 0


def test_recommend(load_db, test_physician_user, test_user, get_elasticsearch_client):
    """
    First, ensure user is regenerated
    """
    random_uuid = str(uuid.uuid4())
    es = get_elasticsearch_client
    author_uuid = test_user.get("userUuid")
    case = _create_case(author_uuid=author_uuid, session=load_db)
    user_uuid = test_physician_user.get('userUuid')

    # Add user to regen list
    Recommended.regenerate_user(user_uuid)
    task = generate_user_recommendations_task.apply().get()

    regen_profile_list = Recommended.get_regenerate_user(count=100)
    get_empty_profile_list = Recommended.get_regenerate_user(count=100)
    # Ensure user has been processed and removed
    assert user_uuid not in get_empty_profile_list

    doc = es.get(index=es_settings.cases_alias, id=str(case.case_uuid))
    # Get the recommended case
    r = get_recommended(user_uuid=user_uuid)

    caseUuidRecommended = r.get('caseUuid')
    assert caseUuidRecommended is not None

    # Ensure that the recommended case is saved
    sent_keys = Recommended.get_sent_user_keys()

    assert sent_keys[user_uuid] == caseUuidRecommended

    # Ensure the user is added back into the regenerate profile list
    regen_user_profile = Recommended.get_regenerate_user(count=100)

    assert user_uuid in regen_user_profile

    # Make sure the sent case is saved
    generate_user_recommendations_task.apply().get()

    q = load_db.query(UserRecommendedCase) \
        .filter(UserRecommendedCase.user_uuid == user_uuid, UserRecommendedCase.case_uuid == caseUuidRecommended)
    assert q.one()
