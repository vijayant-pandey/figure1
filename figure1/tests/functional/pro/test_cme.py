import string
import time
from random import choice
from uuid import UUID

from sqlalchemy.orm import Session
from figure1.common.firebase import do_firebase_sync
from figure1.common.elasticsearch import add_or_update_case, add_or_update_campaign
from figure1.common.helpers import UserManagement
from figure1.common.models.db import CampaignCase, CampaignPreviewUser, CaseProgress
from figure1.common.types.case import CaseState, CaseType
from figure1.tests.utils.case import create_test_case


def _get_user_cme_collection(user_uid, fs, collection_name):
    doc = fs.collection('userCmeDB') \
        .document(user_uid).get()
    count = 0
    while not doc.exists:
        doc = fs.collection('userCmeDB') \
            .document(user_uid).get()
        count += 1
        time.sleep(1)
        if count >= 10:
            raise TimeoutError("Timed out waiting for firestore")

    for doc in fs.collection('userCmeDB') \
            .document(user_uid) \
            .collection(collection_name) \
            .stream():
        yield doc.id


def _create_case(author_uuid: str,
                 state: CaseState,
                 case_type: CaseType,
                 campaign_uuid: str,
                 session: Session):
    case, _ = create_test_case(
        author_uuid=author_uuid,
        is_paging_case=False,
        language='EN_US',
        title="Case Title",
        caption="Case Caption",
        case_type=case_type,
        state=CaseState.SC_DRAFT,
        session=session)

    CampaignCase.create_or_update(campaign_uuid=campaign_uuid,
                                  case_uuid=case.case_uuid,
                                  name='Test campaign case',
                                  moderator_uuid=author_uuid,
                                  tactic_priority=1,
                                  session=session)

    if state == CaseState.SC_REVIEW:
        CampaignCase.review(session=session, case_uuid=case.case_uuid, user_uuid=UUID(author_uuid))
    elif state == CaseState.SC_APPROVED:
        CampaignCase.review(session=session, case_uuid=case.case_uuid, user_uuid=UUID(author_uuid))
        CampaignCase.publish(session=session, case_uuid=case.case_uuid, user_uuid=UUID(author_uuid))

    add_or_update_case(case_uuid=str(case.case_uuid), session=session)
    add_or_update_campaign(campaign_uuid=str(campaign_uuid), session=session)

    return case


def _create_user(session):
    def _random_string(length):
        letters = string.ascii_letters
        return ''.join(choice(letters) for _ in range(length))

    user = _random_string(16)
    mgmt = UserManagement(user_uid=f'test_{user}', session=session, is_new_user=True)
    mgmt.add_user(first_name=f'test_{user}_first_name',
                  last_name=f'test_{user}_last_name',
                  email=f'test_{user}@figure1.com',
                  user_uuid=None,
                  legacy=False)
    return mgmt.user


def test_get_cme_activities(client, headers, load_db, get_firestore_client, test_campaign, test_user):
    session = load_db
    fs = get_firestore_client
    approved_case1 = _create_case(author_uuid=test_user.get('userUuid'),
                                  state=CaseState.SC_APPROVED,
                                  case_type=CaseType.CME,
                                  campaign_uuid=test_campaign.campaign_uuid,
                                  session=session)
    approved_case2 = _create_case(author_uuid=test_user.get('userUuid'),
                                  state=CaseState.SC_APPROVED,
                                  case_type=CaseType.CME,
                                  campaign_uuid=test_campaign.campaign_uuid,
                                  session=session)
    preview_case1 = _create_case(author_uuid=test_user.get('userUuid'),
                                 state=CaseState.SC_REVIEW,
                                 case_type=CaseType.CME,
                                 campaign_uuid=test_campaign.campaign_uuid,
                                 session=session)
    draft_case = _create_case(author_uuid=test_user.get('userUuid'),
                              state=CaseState.SC_DRAFT,
                              case_type=CaseType.CME,
                              campaign_uuid=test_campaign.campaign_uuid,
                              session=session)

    user1 = _create_user(session=session)
    user2 = _create_user(session=session)
    CampaignPreviewUser.create(campaign_uuid=test_campaign.campaign_uuid,
                               user_uuid=user2.user_uuid,
                               topic_uuid=None,
                               session=session)

    user3 = _create_user(session=session)
    CaseProgress.create_or_update(user_uuid=user3.user_uuid,
                                  case_uuid=approved_case1.case_uuid,
                                  session=session,
                                  is_complete=True)
    session.commit()

    do_firebase_sync.apply(kwargs={'firebasemodel': 'FirebaseUserCmeDB', 'uuid': str(user1.user_uuid)})
    do_firebase_sync.apply(kwargs={'firebasemodel': 'FirebaseUserCmeDB', 'uuid': str(user2.user_uuid)})
    do_firebase_sync.apply(kwargs={'firebasemodel': 'FirebaseUserCmeDB', 'uuid': str(user3.user_uuid)})

    # Test user who is not preview user sees only approved cases
    available = list(_get_user_cme_collection(user_uid=user1.user_uid, fs=fs, collection_name='available'))
    completed = list(_get_user_cme_collection(user_uid=user1.user_uid, fs=fs, collection_name='completed'))
    assert len(available) == 2
    assert str(approved_case1.case_uuid) in available
    assert str(approved_case2.case_uuid) in available
    assert len(completed) == 0

    # Test user who is preview user sees also sees preview cases
    available = list(_get_user_cme_collection(user_uid=user2.user_uid, fs=fs, collection_name='available'))
    completed = list(_get_user_cme_collection(user_uid=user2.user_uid, fs=fs, collection_name='completed'))
    assert len(available) == 3
    assert str(approved_case1.case_uuid) in available
    assert str(approved_case2.case_uuid) in available
    assert str(preview_case1.case_uuid) in available
    assert len(completed) == 0

    # Test completed activities appear in completed collection
    available = list(_get_user_cme_collection(user_uid=user3.user_uid, fs=fs, collection_name='available'))
    completed = list(_get_user_cme_collection(user_uid=user3.user_uid, fs=fs, collection_name='completed'))
    assert len(available) == 1
    assert str(approved_case2.case_uuid) in available
    assert len(completed) == 1
    assert str(approved_case1.case_uuid) in completed
