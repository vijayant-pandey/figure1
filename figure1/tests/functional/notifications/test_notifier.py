from datetime import datetime
from datetime import timedelta
from datetime import timezone

from figure1.common.helpers import GroupManagement
from figure1.common.helpers import CaseDetail
from figure1.common.models.db import ActivityReminder
from figure1.common.models.db import CaseAuthor
from figure1.common.models.db import CaseCMEUserAnswer
from figure1.common.models.db import CaseLabel
from figure1.common.models.db import Comment
from figure1.common.models.db import ContentUpdate
from figure1.common.models.db import Features
from figure1.common.models.db import GroupMember
from figure1.common.models.db import Label
from figure1.common.models.db import SpecialtyTreeV2
from figure1.common.models.db import User
from figure1.common.models.db import UserFollow
from figure1.common.models.db import UserNotification
from figure1.common.models.db import UserSavedCase
from figure1.common.models.db import Features
from figure1.notifications.tasks import notify_all_users_of_new_case
from figure1.notifications.tasks import log_case_update
from figure1.notifications.tasks import log_comment_and_notify
from figure1.notifications.tasks import notify_user_of_new_follower
from figure1.notifications.tasks import log_reaction_and_notify_user
from figure1.notifications.tasks import send_event_cme_completed_to_user
from figure1.notifications.tasks import log_comment_delete_and_notify
from figure1.notifications.tasks import log_user_status_changed_and_notify_user
from figure1.notifications.tasks import log_case_state_changed
from figure1.notifications.tasks import notify_users_activity_reminder
from figure1.notifications.tasks import notify_profession_changed_approved
from figure1.notifications.tasks import get_notifications_paging_case
from figure1.notifications import IterableNotifier
from figure1.notifications.tasks import notify_user_of_group_invite
from figure1.notifications.tasks import notifies_users_of_accepted_answer_not_chosen
from figure1.notifications.tasks import notifies_users_of_accepted_answer_deleted
from figure1.notifications.tasks import notifies_users_of_new_accepted_answer
from figure1.notifications.tasks import notify_group_invite_accepted
from figure1.notifications.tasks import notify_users_of_not_chosen_diagnosis_cases
from figure1.notifications.tasks import notify_specialty_users_of_paging_case
from figure1.common.types import Locale
from figure1.common.types import CommentRejectionReason
from figure1.common.types import CaseState
from figure1.common.types.notification import UserNotificationType
from figure1.common.types import CaseRejectionReason
from figure1.common.types.notification import UserNotificationState
from figure1.common.types.case import ContentUpdateType
from figure1.common.types.case import CaseClassification
from figure1.notifications.iterable import IterableEvent
from figure1.notifications.iterable import IterableEventWrapper
from figure1.common.utils.date_utils import utc_now
from figure1.pro.comments.domain import do_post_comment
from figure1.pro.notifications.domain import mark_single_user_notification_read
from figure1.tests.utils.case import create_case_with_specialties
from figure1.tests.utils.case import create_test_case
from figure1.tests.utils.mock_base import MockBase
from figure1.tests.utils.user import create_test_user
from figure1.tests.utils.user import user_comment_case
from figure1.tests.utils.user import user_like_case
from figure1.tests.utils.user import user_save_case


class IterableEventWrapperAssertion(IterableEventWrapper):
    """
    Asserts IterableEventWrapper equality while optionally ignoring dataFields
    """

    def __eq__(self, other: IterableEventWrapper):
        for k, v in self.dataFields.items():
            if isinstance(v, list):
                for item in v:
                    if item not in other.dataFields.get(k, []):
                        return False
        if self.dataFields:
            if not self.dataFields.keys() == other.dataFields.keys():
                return False
            for k, v in self.dataFields.items():
                if not isinstance(v, list):
                    if v != other.dataFields.get(k):
                        return False
        return self.email == other.email and \
            self.eventName == other.eventName and \
            self.userId == other.userId


class MockIterable(MockBase):
    def track_event(self, **kwargs):
        self.calls.append(kwargs)
        self.call_count += 1

    def assert_track_event_called(self, email, event, user_uuid, data_fields={}):
        event_wrapper = IterableEventWrapperAssertion(email=email,
                                                      event=event,
                                                      user_uuid=user_uuid,
                                                      data_fields=data_fields)
        call = {'event_wrapper': event_wrapper}
        assert call in self.calls

    def assert_track_event_called_once(self, email, event, user_uuid, data_fields={}):
        event_wrapper = IterableEventWrapperAssertion(email=email,
                                                      event=event,
                                                      user_uuid=user_uuid,
                                                      data_fields=data_fields)
        call = {'event_wrapper': event_wrapper}
        assert len([each for each in self.calls if each == call]) == 1


def _disable_notifications(content_uuid, session):
    Features.create_or_update(content_uuid=content_uuid,
                              public_notifications_enabled=False,
                              session=session)


def test_send_paging_case_to_users(load_db, test_user, initialize_data, monkeypatch):
    """
    when a case is approved, two events are sent to iterable. first event to specialty and subspecialty users under one
    tree uuid and second event for users who have specialty only for a case.
    """
    session = load_db

    tree = session.query(SpecialtyTreeV2) \
        .filter(SpecialtyTreeV2.profile_display_label == 'Physician | Family Medicine') \
        .first().as_object()
    case_specialties = [tree.specialty.specialtyUuid, tree.subspecialty.specialtyUuid]
    case_specialty_names = [tree.specialty.specialtyName, tree.subspecialty.specialtyName]

    # User 1's primary specialty matches case specialty and subspecialty
    user1_specialty = tree
    user1 = create_test_user(session=session,
                             primary_specialty_uuid=user1_specialty.treeUuid,
                             verified=True)

    # User 2's primary specialty matches only case specialty
    user2_specialty = session.query(SpecialtyTreeV2) \
        .filter(SpecialtyTreeV2.specialty_v2_uuid == tree.specialty.specialtyUuid,
                SpecialtyTreeV2.subspecialty_uuid != tree.subspecialty.specialtyUuid) \
        .first().as_object()
    user2 = create_test_user(session=session,
                             primary_specialty_uuid=user2_specialty.treeUuid,
                             verified=True)

    # User 3's primary specialty matches only case subspecialty
    user3_specialty = session.query(SpecialtyTreeV2) \
        .filter(SpecialtyTreeV2.specialty_v2_uuid != tree.specialty.specialtyUuid,
                SpecialtyTreeV2.subspecialty_uuid == tree.subspecialty.specialtyUuid) \
        .first().as_object()
    user3 = create_test_user(session=session,
                             primary_specialty_uuid=user3_specialty.treeUuid,
                             verified=True)

    # Unverified users do not get notifications
    unverified_user = create_test_user(session=session,
                                       primary_specialty_uuid=user1_specialty.treeUuid,
                                       verified=False)
    session.flush()

    case = create_case_with_specialties(author_uuid=test_user.get('userUuid'),
                                        is_paging_case=True,
                                        language='en',
                                        specialty_uuids=case_specialties,
                                        state=CaseState.APPROVED,
                                        session=session)

    anonymous_case = create_case_with_specialties(author_uuid=test_user.get('userUuid'),
                                                  is_paging_case=True,
                                                  language='en',
                                                  specialty_uuids=case_specialties,
                                                  state=CaseState.APPROVED,
                                                  is_anonymous=True,
                                                  session=session)

    res = list(get_notifications_paging_case(case_uuid=case.case_uuid, session=session))

    specialty_subspecialty_matches = \
        [n.user_uuid for n in res if n.iterable_event == IterableEvent.PAGING_CASE_POSTED_SPECIALTY_SUBSPECIALTY_USERS]
    assert str(user1.user_uuid) in specialty_subspecialty_matches
    assert str(user2.user_uuid) not in specialty_subspecialty_matches
    assert str(user3.user_uuid) not in specialty_subspecialty_matches
    assert str(unverified_user.user_uuid) not in specialty_subspecialty_matches

    specialty_matches = [n.user_uuid for n in res
                         if n.iterable_event == IterableEvent.PAGING_CASE_POSTED_SPECIALTY_USERS]
    assert str(user1.user_uuid) not in specialty_matches
    assert str(user2.user_uuid) in specialty_matches
    assert str(user3.user_uuid) not in specialty_matches
    assert str(unverified_user.user_uuid) not in specialty_matches

    subspecialty_matches = [n.user_uuid for n in res
                            if n.iterable_event == IterableEvent.PAGING_CASE_POSTED_SUBSPECIALTY_USERS]
    assert str(user1.user_uuid) not in subspecialty_matches
    assert str(user2.user_uuid) not in subspecialty_matches
    assert str(user3.user_uuid) in subspecialty_matches
    assert str(unverified_user.user_uuid) not in subspecialty_matches

    # Repeated tasks do not notify users who were previously notified
    notify_specialty_users_of_paging_case(case_uuid=str(case.case_uuid), session=session, iterable=IterableNotifier())
    res = list(get_notifications_paging_case(case_uuid=str(case.case_uuid), session=session))
    assert len(res) == 0

    # The case is anonymous
    with MockIterable() as mock_iterable:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI.track_event',
                            mock_iterable.track_event)

        notify_specialty_users_of_paging_case(case_uuid=str(anonymous_case.case_uuid),
                                              session=session,
                                              iterable=IterableNotifier())

        expected_data_fields = {
            'caseCaption': None,
            'caseTitle': None,
            'caseUuid': str(anonymous_case.case_uuid),
            'caseTimeApproval': datetime.fromisoformat(str(anonymous_case.created_at)).strftime('%Y-%m-%d %H:%M:%S'),
            'caseSpecialty': case_specialty_names,
            'caseMediaUrl': None,
        }

        mock_iterable.assert_track_event_called(event=IterableEvent.PAGING_CASE_POSTED_SPECIALTY_SUBSPECIALTY_USERS,
                                                email=user1.email,
                                                user_uuid=user1.user_uuid,
                                                data_fields=expected_data_fields,
                                                )
        mock_iterable.assert_track_event_called(event=IterableEvent.PAGING_CASE_POSTED_SPECIALTY_USERS,
                                                email=user2.email,
                                                user_uuid=user2.user_uuid,
                                                data_fields=expected_data_fields,
                                                )
        mock_iterable.assert_track_event_called(event=IterableEvent.PAGING_CASE_POSTED_SUBSPECIALTY_USERS,
                                                email=user3.email,
                                                user_uuid=user3.user_uuid,
                                                data_fields=expected_data_fields,
                                                )


def test_should_not_send_paging_post_to_users(load_db, test_user, initialize_data, monkeypatch):
    session = load_db

    tree = session.query(SpecialtyTreeV2) \
        .filter(SpecialtyTreeV2.profile_display_label == 'Physician | Family Medicine') \
        .first().as_object()
    case_specialties = [tree.specialty.specialtyUuid, tree.subspecialty.specialtyUuid]

    # User 1's primary specialty matches case specialty and subspecialty
    user1_specialty = tree
    user1 = create_test_user(session=session,
                             primary_specialty_uuid=user1_specialty.treeUuid,
                             verified=True)

    # User 2's primary specialty matches only case specialty
    user2_specialty = session.query(SpecialtyTreeV2) \
        .filter(SpecialtyTreeV2.specialty_v2_uuid == tree.specialty.specialtyUuid,
                SpecialtyTreeV2.subspecialty_uuid != tree.subspecialty.specialtyUuid) \
        .first().as_object()
    user2 = create_test_user(session=session,
                             primary_specialty_uuid=user2_specialty.treeUuid,
                             verified=True)

    # User 3's primary specialty matches only case subspecialty
    user3_specialty = session.query(SpecialtyTreeV2) \
        .filter(SpecialtyTreeV2.specialty_v2_uuid != tree.specialty.specialtyUuid,
                SpecialtyTreeV2.subspecialty_uuid == tree.subspecialty.specialtyUuid) \
        .first().as_object()
    user3 = create_test_user(session=session,
                             primary_specialty_uuid=user3_specialty.treeUuid,
                             verified=True)

    # Unverified users do not get notifications
    unverified_user = create_test_user(session=session,
                                       primary_specialty_uuid=user1_specialty.treeUuid,
                                       verified=False)
    session.flush()

    post = create_case_with_specialties(author_uuid=test_user.get('userUuid'),
                                        is_paging_case=True,
                                        language='en',
                                        specialty_uuids=case_specialties,
                                        state=CaseState.APPROVED,
                                        case_classification=CaseClassification.NONMEDICAL,
                                        session=session)

    anonymous_post = create_case_with_specialties(author_uuid=test_user.get('userUuid'),
                                                  is_paging_case=True,
                                                  language='en',
                                                  specialty_uuids=case_specialties,
                                                  state=CaseState.APPROVED,
                                                  is_anonymous=True,
                                                  case_classification=CaseClassification.NONMEDICAL,
                                                  session=session)

    res = list(get_notifications_paging_case(case_uuid=post.case_uuid, session=session))
    assert len(res) == 0

    # The case is anonymous
    with MockIterable() as mock_iterable:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI.track_event',
                            mock_iterable.track_event)

        notify_specialty_users_of_paging_case(case_uuid=str(anonymous_post.case_uuid),
                                              session=session,
                                              iterable=IterableNotifier())

        mock_iterable.assert_not_called()


def test_case_rejected_notifies_author(load_db, initialize_data, get_firestore_client, monkeypatch):
    session = load_db
    case_author = create_test_user(session=session)
    moderator = create_test_user(session=session)
    case, content = create_test_case(author_uuid=case_author.user_uuid,
                                     is_paging_case=False,
                                     language=Locale.EN_US.code,
                                     title="Case Title",
                                     caption="Case Caption",
                                     state=CaseState.REJECTED,
                                     rejection_reason=CaseRejectionReason.NEED_CLINICAL_INFO,
                                     session=session)

    with MockIterable() as mock_iterable:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI.track_event',
                            mock_iterable.track_event)
        log_case_state_changed(case_uuid=case.case_uuid,
                               moderator_uid=moderator.user_uid,
                               session=session,
                               suppress_user_notification=False,
                               iterable=IterableNotifier(),
                               fs_client=get_firestore_client)
        mock_iterable.assert_track_event_called(event=IterableEvent.CASE_STATE_CHANGED,
                                                email=case_author.email,
                                                user_uuid=case_author.user_uuid)
    assert session.query(UserNotification) \
        .filter(UserNotification.user_uuid == case_author.user_uuid,
                UserNotification.case_uuid == case.case_uuid,
                UserNotification.notification_type == UserNotificationType.REJECT) \
        .one_or_none()


def test_case_deleted_notifies_author(load_db, initialize_data, get_firestore_client, monkeypatch):
    session = load_db
    case_author = create_test_user(session=session)
    moderator = create_test_user(session=session)
    case, content = create_test_case(author_uuid=case_author.user_uuid,
                                     is_paging_case=False,
                                     language=Locale.EN_US.code,
                                     title="Case Title",
                                     caption="Case Caption",
                                     state=CaseState.DELETED,
                                     rejection_reason=CaseRejectionReason.SUSPECTED_HOMEWORK,
                                     session=session)

    with MockIterable() as mock_iterable:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI.track_event',
                            mock_iterable.track_event)
        log_case_state_changed(case_uuid=case.case_uuid,
                               moderator_uid=moderator.user_uid,
                               session=session,
                               suppress_user_notification=False,
                               iterable=IterableNotifier(),
                               fs_client=get_firestore_client)
        mock_iterable.assert_track_event_called(event=IterableEvent.CASE_STATE_CHANGED,
                                                email=case_author.email,
                                                user_uuid=case_author.user_uuid)
    assert session.query(UserNotification) \
        .filter(UserNotification.user_uuid == case_author.user_uuid,
                UserNotification.case_uuid == case.case_uuid,
                UserNotification.notification_type == UserNotificationType.CASE_DELETE) \
        .one_or_none()


def test_case_approved_notifies_author(load_db, initialize_data, get_firestore_client, monkeypatch):
    session = load_db
    case_author = create_test_user(session=session)
    moderator = create_test_user(session=session)
    case, content = create_test_case(author_uuid=case_author.user_uuid,
                                     is_paging_case=False,
                                     language=Locale.EN_US.code,
                                     title="Case Title",
                                     caption="Case Caption",
                                     state=CaseState.APPROVED,
                                     session=session)

    with MockIterable() as mock_iterable:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI.track_event',
                            mock_iterable.track_event)

        case_specialty_names = CaseDetail.get_case_specialty_names(case_uuid=case.case_uuid, session=session)
        expected_data_fields = {
            "caseCaption": "Case Caption",
            "caseTitle": "Case Title",
            "caseUuid": str(case.case_uuid),
            "changedCaseState": "approved",
            "receiverUuid": str(case_author.user_uuid),
            "receiverUid": case_author.user_uid,
            "caseClassification": "medical",
            "authorUuid": str(case_author.user_uuid),
            "authorUsername": case_author.username,
            "caseSpecialties": case_specialty_names,
        }
        log_case_state_changed(case_uuid=case.case_uuid,
                               moderator_uid=moderator.user_uid,
                               session=session,
                               suppress_user_notification=False,
                               iterable=IterableNotifier(),
                               fs_client=get_firestore_client)
        mock_iterable.assert_track_event_called(event=IterableEvent.CASE_STATE_CHANGED,
                                                email=case_author.email,
                                                user_uuid=case_author.user_uuid,
                                                data_fields=expected_data_fields)

    assert session.query(UserNotification) \
        .filter(UserNotification.user_uuid == case_author.user_uuid,
                UserNotification.case_uuid == case.case_uuid,
                UserNotification.notification_type == UserNotificationType.APPROVE) \
        .one_or_none()


def test_case_posted_notifies_followers(load_db, initialize_data, monkeypatch):
    session = load_db
    case_author = create_test_user(session=session)
    receiver = create_test_user(session=session)
    case, content = create_test_case(author_uuid=case_author.user_uuid,
                                     is_paging_case=False,
                                     language=Locale.EN_US.code,
                                     title="Case Title",
                                     caption="Case Caption",
                                     state=CaseState.APPROVED,
                                     session=session)
    anonymous_case, anonymous_content = create_test_case(author_uuid=case_author.user_uuid,
                                                         is_paging_case=False,
                                                         language=Locale.EN_US.code,
                                                         title="Case Title",
                                                         caption="Case Caption",
                                                         state=CaseState.APPROVED,
                                                         is_anonymous=True,
                                                         session=session)

    # Test no followers
    with MockIterable() as mock_iterable:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI.track_event',
                            mock_iterable.track_event)
        notify_all_users_of_new_case(case_uuid=case.case_uuid, session=session, iterable=IterableNotifier())
        assert mock_iterable.call_count == 0

    # Test successful notification
    UserFollow.follow_user(session=session,
                           user_uuid=case_author.user_uuid,
                           follower_user_uuid=receiver.user_uuid)
    session.commit()
    with MockIterable() as mock_iterable:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI.track_event',
                            mock_iterable.track_event)
        notify_all_users_of_new_case(case_uuid=case.case_uuid,
                                     session=session,
                                     iterable=IterableNotifier())

        expected_data_fields = {
            'caseCaption': content.caption,
            'caseTitle': content.title,
            'caseUuid': str(case.case_uuid),
            'caseAuthorUsername': case_author.username,
            'caseAuthorFirstName': case_author.first_name,
            'caseAuthorLastName': case_author.last_name,
            'caseAuthorUuid': str(case_author.user_uuid),
            'caseAuthorEmail': case_author.email,
            'receiverUuid': str(receiver.user_uuid),
            'caseClassification': 'medical',
            'caseMediaUrl': None,
        }

        mock_iterable.assert_track_event_called(event=IterableEvent.CASE_POSTED_FOLLOWED_USER,
                                                email=receiver.email,
                                                user_uuid=receiver.user_uuid,
                                                data_fields=expected_data_fields)
    assert session.query(UserNotification) \
        .filter(UserNotification.user_uuid == receiver.user_uuid,
                UserNotification.case_uuid == case.case_uuid,
                UserNotification.notification_type == UserNotificationType.NEW_CASE_FOLLOWED_USER) \
        .one_or_none()

    # Test case with disabled notifications
    _disable_notifications(content_uuid=content.content_uuid, session=session)
    with MockIterable() as mock_iterable:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI.track_event',
                            mock_iterable.track_event)
        notify_all_users_of_new_case(case_uuid=case.case_uuid,
                                     session=session,
                                     iterable=IterableNotifier())
        assert mock_iterable.call_count == 0

    # Test anonymous case posted
    with MockIterable() as mock_iterable:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI.track_event',
                            mock_iterable.track_event)
        notify_all_users_of_new_case(case_uuid=anonymous_case.case_uuid,
                                     session=session,
                                     iterable=IterableNotifier())
        assert mock_iterable.call_count == 0
    assert not session.query(UserNotification) \
        .filter(UserNotification.user_uuid == receiver.user_uuid,
                UserNotification.case_uuid == anonymous_case.case_uuid,
                UserNotification.notification_type == UserNotificationType.NEW_CASE_FOLLOWED_USER) \
        .one_or_none()


def test_group_case_posted_notifies_group_members(load_db,
                                                  test_user,
                                                  test_group_case,
                                                  test_group_anonymous_case,
                                                  monkeypatch):
    session = load_db
    receiver = create_test_user(session=session)
    case, content = test_group_case
    anonymous_case = test_group_anonymous_case

    GroupManagement.add_user_to_group(user_uuid=receiver.user_uuid,
                                      group_uuid=case.group_uuid,
                                      session=session)
    session.commit()
    g = GroupManagement.get_group(group_uuid=case.group_uuid, session=session)

    with MockIterable() as mock_iterable:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI.track_event',
                            mock_iterable.track_event)

        expected_data_fields = {
            'groupUuid': g.groupUuid,
            'groupName': g.groupName,
            'caseUuid': str(case.case_uuid),
            'caseSubmissionDate': str(case.created_at),
            'caseTitle': content.title,
            'authorUsername': [test_user.get('username')],
            'caseLabels': case.labels,
            'caseClassification': 'medical',
            'caseMediaUrl': None,
            'caseCaption': content.caption,
        }

        notify_all_users_of_new_case(case_uuid=case.case_uuid,
                                     session=session,
                                     iterable=IterableNotifier())
        assert mock_iterable.call_count == len(g.groupMembers)
        mock_iterable.assert_track_event_called(event=IterableEvent.CASE_POSTED_GROUP,
                                                email=receiver.email,
                                                user_uuid=receiver.user_uuid,
                                                data_fields=expected_data_fields)

    user_notification_query = session.query(UserNotification) \
        .filter(UserNotification.user_uuid == receiver.user_uuid,
                UserNotification.case_uuid == case.case_uuid,
                UserNotification.notification_type == UserNotificationType.NEW_CASE_GROUP)
    assert user_notification_query.count() == 1

    with MockIterable() as mock_iterable:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI.track_event',
                            mock_iterable.track_event)
        notify_all_users_of_new_case(case_uuid=anonymous_case.case_uuid,
                                     session=session,
                                     iterable=IterableNotifier())
        assert mock_iterable.call_count == 0

    user_notification_query = session.query(UserNotification) \
        .filter(UserNotification.user_uuid == receiver.user_uuid,
                UserNotification.case_uuid == anonymous_case.case_uuid,
                UserNotification.notification_type == UserNotificationType.NEW_CASE_GROUP)

    assert user_notification_query.count() == 0

    session.query(UserNotification).filter(UserNotification.group_uuid == case.group_uuid).delete()
    session.query(GroupMember).filter(GroupMember.group_uuid == case.group_uuid).delete()
    session.flush()


def test_case_posted_notifies_saved_users(load_db, initialize_data, monkeypatch):
    session = load_db
    case_author = create_test_user(session=session)
    receiver = create_test_user(session=session)
    previously_saved_case, _ = create_test_case(author_uuid=case_author.user_uuid,
                                                is_paging_case=False,
                                                language=Locale.EN_US.code,
                                                title="Case Title",
                                                caption="Case Caption",
                                                state=CaseState.APPROVED,
                                                session=session)
    new_case, new_content = create_test_case(author_uuid=case_author.user_uuid,
                                             is_paging_case=False,
                                             language=Locale.EN_US.code,
                                             title="Case Title",
                                             caption="Case Caption",
                                             state=CaseState.APPROVED,
                                             session=session)
    anonymous_case, anonymous_content = create_test_case(author_uuid=case_author.user_uuid,
                                                         is_paging_case=False,
                                                         language=Locale.EN_US.code,
                                                         title="Case Title",
                                                         caption="Case Caption",
                                                         state=CaseState.APPROVED,
                                                         is_anonymous=True,
                                                         session=session)

    # Test no receivers
    with MockIterable() as mock_iterable:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI.track_event',
                            mock_iterable.track_event)
        notify_all_users_of_new_case(case_uuid=new_case.case_uuid,
                                     session=session,
                                     iterable=IterableNotifier())
        assert mock_iterable.call_count == 0

    # Test successful notification
    UserSavedCase.create(case_uuid=previously_saved_case.case_uuid,
                         user_uuid=receiver.user_uuid,
                         session=session)
    # The author saved the case
    UserSavedCase.create(case_uuid=previously_saved_case.case_uuid,
                         user_uuid=case_author.user_uuid,
                         session=session)
    session.commit()

    with MockIterable() as mock_iterable:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI.track_event',
                            mock_iterable.track_event)
        notify_all_users_of_new_case(case_uuid=new_case.case_uuid,
                                     session=session,
                                     iterable=IterableNotifier())
        mock_iterable.assert_track_event_called(event=IterableEvent.CASE_POSTED_USER_SAVED_CASE,
                                                email=receiver.email,
                                                user_uuid=receiver.user_uuid)
    assert session.query(UserNotification) \
        .filter(UserNotification.user_uuid == receiver.user_uuid,
                UserNotification.case_uuid == new_case.case_uuid,
                UserNotification.notification_type == UserNotificationType.NEW_CASE_USER_SAVED_CASE) \
        .one_or_none()

    assert not session.query(UserNotification) \
        .filter(UserNotification.user_uuid == case_author.user_uuid,
                UserNotification.case_uuid == new_case.case_uuid,
                UserNotification.notification_type == UserNotificationType.NEW_CASE_USER_SAVED_CASE) \
        .one_or_none()

    # Test case with disabled notifications
    _disable_notifications(content_uuid=new_content.content_uuid, session=session)
    with MockIterable() as mock_iterable:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI.track_event',
                            mock_iterable.track_event)
        notify_all_users_of_new_case(case_uuid=new_case.case_uuid,
                                     session=session,
                                     iterable=IterableNotifier())
        assert mock_iterable.call_count == 0

    # Test anonymous case
    with MockIterable() as mock_iterable:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI.track_event',
                            mock_iterable.track_event)
        notify_all_users_of_new_case(case_uuid=anonymous_case.case_uuid,
                                     session=session,
                                     iterable=IterableNotifier())
        assert mock_iterable.call_count == 0
    assert not session.query(UserNotification) \
        .filter(UserNotification.user_uuid == receiver.user_uuid,
                UserNotification.case_uuid == anonymous_case.case_uuid,
                UserNotification.notification_type == UserNotificationType.NEW_CASE_USER_SAVED_CASE) \
        .one_or_none()


def test_case_update_notifies_saved_users(load_db, initialize_data, monkeypatch):
    session = load_db
    case_author = create_test_user(session=session)
    receiver = create_test_user(session=session)

    case, content = create_test_case(author_uuid=case_author.user_uuid,
                                     is_paging_case=False,
                                     language=Locale.EN_US.code,
                                     title="Case Title",
                                     caption="Case Caption",
                                     state=CaseState.APPROVED,
                                     session=session)
    anonymous_case, anonymous_content = create_test_case(author_uuid=case_author.user_uuid,
                                                         is_paging_case=False,
                                                         language=Locale.EN_US.code,
                                                         title="Case Title",
                                                         caption="Case Caption",
                                                         state=CaseState.APPROVED,
                                                         is_anonymous=True,
                                                         session=session)

    # Test no receivers
    with MockIterable() as mock_iterable:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI.track_event',
                            mock_iterable.track_event)
        log_case_update(case_uuid=str(case.case_uuid),
                        author_uuid=case_author.user_uuid,
                        previous_label='unresolved',
                        current_label='resolved',
                        is_diagnosis=False,
                        session=session,
                        iterable=IterableNotifier())
        assert mock_iterable.call_count == 0

    # Test successful notification
    UserSavedCase.create(case_uuid=case.case_uuid,
                         user_uuid=receiver.user_uuid,
                         session=session)
    session.commit()
    with MockIterable() as mock_iterable:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI.track_event',
                            mock_iterable.track_event)
        log_case_update(case_uuid=str(case.case_uuid),
                        author_uuid=case_author.user_uuid,
                        previous_label='unresolved',
                        current_label='resolved',
                        is_diagnosis=False,
                        session=session,
                        iterable=IterableNotifier())
        mock_iterable.assert_track_event_called(event=IterableEvent.CASE_NEW_UPDATE,
                                                email=receiver.email,
                                                user_uuid=receiver.user_uuid)
    assert session.query(UserNotification) \
        .filter(UserNotification.user_uuid == receiver.user_uuid,
                UserNotification.case_uuid == case.case_uuid,
                UserNotification.notification_type == UserNotificationType.SAVED_CASE_UPDATE) \
        .one_or_none()

    # Test anonymous case
    UserSavedCase.create(case_uuid=anonymous_case.case_uuid,
                         user_uuid=receiver.user_uuid,
                         session=session)
    session.commit()
    with MockIterable() as mock_iterable:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI.track_event',
                            mock_iterable.track_event)
        log_case_update(case_uuid=str(anonymous_case.case_uuid),
                        author_uuid=case_author.user_uuid,
                        previous_label='unresolved',
                        current_label='resolved',
                        is_diagnosis=False,
                        session=session,
                        iterable=IterableNotifier())

        expected_data_fields = {
            'caseTitle': anonymous_content.title,
            'caseUuid': str(anonymous_case.case_uuid),
            'caseCurrentStatus': 'resolved',
            'casePreviousStatus': 'unresolved',
            'diagnosisUpdateAdded': False,
            'groupUuid': None,
            'groupName': None,
            'caseMediaUrl': None,
        }

        mock_iterable.assert_track_event_called(event=IterableEvent.CASE_NEW_UPDATE,
                                                email=receiver.email,
                                                user_uuid=receiver.user_uuid,
                                                data_fields=expected_data_fields)
    assert session.query(UserNotification) \
        .filter(UserNotification.user_uuid == receiver.user_uuid,
                UserNotification.case_uuid == anonymous_case.case_uuid,
                UserNotification.notification_type == UserNotificationType.SAVED_CASE_UPDATE) \
        .one_or_none()


def test_post_update_should_not_notify_saved_users(load_db, initialize_data, monkeypatch):
    session = load_db
    post_author = create_test_user(session=session)
    receiver = create_test_user(session=session)

    post, content = create_test_case(author_uuid=post_author.user_uuid,
                                     is_paging_case=False,
                                     language=Locale.EN_US.code,
                                     title="Case Title",
                                     caption="Case Caption",
                                     state=CaseState.APPROVED,
                                     case_classification=CaseClassification.NONMEDICAL,
                                     session=session)
    anonymous_post, anonymous_content = create_test_case(author_uuid=post_author.user_uuid,
                                                         is_paging_case=False,
                                                         language=Locale.EN_US.code,
                                                         title="Case Title",
                                                         caption="Case Caption",
                                                         state=CaseState.APPROVED,
                                                         is_anonymous=True,
                                                         case_classification=CaseClassification.NONMEDICAL,
                                                         session=session)

    UserSavedCase.create(case_uuid=post.case_uuid,
                         user_uuid=receiver.user_uuid,
                         session=session)
    session.commit()
    with MockIterable() as mock_iterable:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI.track_event',
                            mock_iterable.track_event)
        log_case_update(case_uuid=str(post.case_uuid),
                        author_uuid=post_author.user_uuid,
                        previous_label='unresolved',
                        current_label='resolved',
                        is_diagnosis=False,
                        session=session,
                        iterable=IterableNotifier())
        mock_iterable.assert_not_called()
    assert not session.query(UserNotification) \
        .filter(UserNotification.user_uuid == receiver.user_uuid,
                UserNotification.case_uuid == post.case_uuid,
                UserNotification.notification_type == UserNotificationType.SAVED_CASE_UPDATE) \
        .one_or_none()

    # Test anonymous case
    UserSavedCase.create(case_uuid=anonymous_post.case_uuid,
                         user_uuid=receiver.user_uuid,
                         session=session)
    session.commit()
    with MockIterable() as mock_iterable:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI.track_event',
                            mock_iterable.track_event)
        log_case_update(case_uuid=str(anonymous_post.case_uuid),
                        author_uuid=post_author.user_uuid,
                        previous_label='unresolved',
                        current_label='resolved',
                        is_diagnosis=False,
                        session=session,
                        iterable=IterableNotifier())

        mock_iterable.assert_not_called()
    assert not session.query(UserNotification) \
        .filter(UserNotification.user_uuid == receiver.user_uuid,
                UserNotification.case_uuid == anonymous_post.case_uuid,
                UserNotification.notification_type == UserNotificationType.SAVED_CASE_UPDATE) \
        .one_or_none()


def test_new_follower_notifies_user(load_db, initialize_data, monkeypatch):
    session = load_db
    follower = create_test_user(session=session)
    target_user = create_test_user(session=session)

    with MockIterable() as mock_iterable:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI.track_event',
                            mock_iterable.track_event)
        expected_data_fields = {
            "userNewFollowerUsername": follower.username,
            "userNewFollowerUuid": str(follower.user_uuid),
            "userNewFollowerProfileImage": follower.user_profile.avatar,
        }

        notify_user_of_new_follower(follower_uuid=follower.user_uuid,
                                    target_user_uuid=target_user.user_uuid,
                                    session=session,
                                    iterable=IterableNotifier())
        mock_iterable.assert_track_event_called(event=IterableEvent.FOLLOWER,
                                                email=target_user.email,
                                                user_uuid=target_user.user_uuid,
                                                data_fields=expected_data_fields)
    assert session.query(UserNotification) \
        .filter(UserNotification.user_uuid == target_user.user_uuid,
                UserNotification.notification_type == UserNotificationType.NEW_FOLLOWER) \
        .one_or_none()


def test_reaction_notifiers_author(load_db, initialize_data, monkeypatch):
    session = load_db
    user = create_test_user(session=session)
    case_author = create_test_user(session=session)
    case, content = create_test_case(author_uuid=case_author.user_uuid,
                                     is_paging_case=False,
                                     language=Locale.EN_US.code,
                                     title="Case Title",
                                     caption="Case Caption",
                                     state=CaseState.APPROVED,
                                     session=session)

    with MockIterable() as mock_iterable:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI.track_event',
                            mock_iterable.track_event)
        log_reaction_and_notify_user(user_uuid=user.user_uuid,
                                     case_uuid=case.case_uuid,
                                     session=session,
                                     iterable=IterableNotifier())
        mock_iterable.assert_track_event_called(event=IterableEvent.CASE_REACTION,
                                                email=case_author.email,
                                                user_uuid=case_author.user_uuid)
    assert session.query(UserNotification) \
        .filter(UserNotification.user_uuid == case_author.user_uuid,
                UserNotification.case_uuid == case.case_uuid,
                UserNotification.notification_type == UserNotificationType.REACT) \
        .one_or_none()

    session.query(UserNotification) \
        .filter(UserNotification.user_uuid == case_author.user_uuid,
                UserNotification.case_uuid == case.case_uuid,
                UserNotification.notification_type == UserNotificationType.REACT) \
        .delete()
    session.commit()

    # the author liked the case
    with MockIterable() as mock_iterable:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI.track_event',
                            mock_iterable.track_event)
        log_reaction_and_notify_user(user_uuid=str(case_author.user_uuid),
                                     case_uuid=str(case.case_uuid),
                                     session=session,
                                     iterable=IterableNotifier())
        mock_iterable.assert_not_called()
    assert not session.query(UserNotification) \
        .filter(UserNotification.user_uuid == case_author.user_uuid,
                UserNotification.case_uuid == case.case_uuid,
                UserNotification.notification_type == UserNotificationType.REACT) \
        .one_or_none()


def test_cme_completed_logs_event(load_db, initialize_data, monkeypatch):
    session = load_db
    user = create_test_user(session=session)
    case_author = create_test_user(session=session)
    case, content = create_test_case(author_uuid=case_author.user_uuid,
                                     is_paging_case=False,
                                     language=Locale.EN_US.code,
                                     title="Case Title",
                                     caption="Case Caption",
                                     state=CaseState.APPROVED,
                                     session=session)

    with MockIterable() as mock_iterable:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI.track_event',
                            mock_iterable.track_event)
        send_event_cme_completed_to_user(case_uuid=case.case_uuid,
                                         completed_at=datetime.now(timezone.utc),
                                         user_uuid=user.user_uuid,
                                         session=session,
                                         iterable=IterableNotifier())
        mock_iterable.assert_track_event_called(event=IterableEvent.CME_COMPLETED,
                                                email=user.email,
                                                user_uuid=user.user_uuid)


def test_case_cme_event(load_db, case_cme_questions_set, monkeypatch):
    session = load_db
    user = create_test_user(session=session)
    case_author = create_test_user(session=session)
    case, content = create_test_case(author_uuid=case_author.user_uuid,
                                     is_paging_case=False,
                                     language=Locale.EN_US.code,
                                     title="Case Title",
                                     caption="Case Caption",
                                     state=CaseState.APPROVED,
                                     session=session)
    questions_set = list(case_cme_questions_set.questions)

    with MockIterable() as mock_iterable:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI.track_event',
                            mock_iterable.track_event)

        completed_at = datetime.now(timezone.utc)
        user_case_cme_answer = CaseCMEUserAnswer.add_user_answer(user_uuid=user.user_uuid,
                                                                 question_uuid=questions_set[1].questionUuid,
                                                                 case_uuid=case.case_uuid,
                                                                 user_answer_text="answer")
        session.add(user_case_cme_answer)
        session.flush()

        expected_data_fields = {
            "cmeUuid": None,
            "completedAt": completed_at.strftime('%Y-%m-%d %H:%M:%S'),
            "userUuid": str(user.user_uuid),
            "caseUuid": str(case.case_uuid),
            "caseTitle": "Case Title",
            "caseCaption": "Case Caption",
            "caseImage": [],
            "username": user.username,
            "willImpactPractice": True
        }

        send_event_cme_completed_to_user(case_uuid=case.case_uuid,
                                         completed_at=completed_at,
                                         user_uuid=user.user_uuid,
                                         session=session,
                                         iterable=IterableNotifier(),
                                         is_case_cme=True)

        mock_iterable.assert_track_event_called(event=IterableEvent.CME_COMPLETED,
                                                email=user.email,
                                                user_uuid=user.user_uuid,
                                                data_fields=expected_data_fields,
                                                )
    with MockIterable() as mock_iterable:
        session.query(CaseCMEUserAnswer).delete()
        session.flush()
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI.track_event',
                            mock_iterable.track_event)

        completed_at = datetime.now(timezone.utc)
        user_case_cme_answer = CaseCMEUserAnswer.add_user_answer(user_uuid=user.user_uuid,
                                                                 question_uuid=questions_set[1].questionUuid,
                                                                 case_uuid=case.case_uuid,
                                                                 user_answer_text="It will not impact my practice")
        session.add(user_case_cme_answer)
        session.flush()
        expected_data_fields = {
            "cmeUuid": None,
            "completedAt": completed_at.strftime('%Y-%m-%d %H:%M:%S'),
            "userUuid": str(user.user_uuid),
            "caseUuid": str(case.case_uuid),
            "caseTitle": "Case Title",
            "caseCaption": "Case Caption",
            "caseImage": [],
            "username": user.username,
            "willImpactPractice": False
        }
        send_event_cme_completed_to_user(case_uuid=case.case_uuid,
                                         completed_at=completed_at,
                                         user_uuid=user.user_uuid,
                                         session=session,
                                         iterable=IterableNotifier(),
                                         is_case_cme=True)
        mock_iterable.assert_track_event_called(event=IterableEvent.CME_COMPLETED,
                                                email=user.email,
                                                user_uuid=user.user_uuid,
                                                data_fields=expected_data_fields)


def test_new_comment_notifies_case_author(load_db, initialize_data, monkeypatch):
    session = load_db
    commenter = create_test_user(session=session)
    case_author = create_test_user(session=session)
    case, content = create_test_case(author_uuid=case_author.user_uuid,
                                     is_paging_case=False,
                                     language=Locale.EN_US.code,
                                     title="Case Title",
                                     caption="Case Caption",
                                     state=CaseState.APPROVED,
                                     session=session)

    comment_uuid = do_post_comment(user_uid=commenter.user_uid,
                                   content_uuid=content.content_uuid,
                                   comment_text='new comment',
                                   parent_comment_uuid=None).pop('uuid')

    with MockIterable() as mock_iterable:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI.track_event',
                            mock_iterable.track_event)

        expected_data_fields = {
            'caseCaption': content.caption,
            'caseTitle': content.title,
            'caseUuid': str(case.case_uuid),
            'commentUuid': str(comment_uuid),
            'receiverUuid': str(case_author.user_uuid),
            'receiverUid': case_author.user_uid,
            'groupUuid': None,
            'groupName': None,
            'caseClassification': 'medical',
            'caseMediaUrl': None,
            'commentText': 'new comment',
        }

        log_comment_and_notify(user_uuid=commenter.user_uuid,
                               content_uuid=content.content_uuid,
                               comment_uuid=comment_uuid,
                               session=session,
                               iterable=IterableNotifier())
        mock_iterable.assert_track_event_called(event=IterableEvent.COMMENT_YOUR_CASE,
                                                email=case_author.email,
                                                user_uuid=case_author.user_uuid,
                                                data_fields=expected_data_fields)
        assert session.query(UserNotification) \
            .filter(UserNotification.user_uuid == case_author.user_uuid,
                    UserNotification.case_uuid == case.case_uuid,
                    UserNotification.comment_uuid == comment_uuid,
                    UserNotification.notification_type == UserNotificationType.COMMENT) \
            .first()


def test_group_case_new_comment_notifies_case_author(load_db,
                                                     test_user,
                                                     create_group,
                                                     test_group_case,
                                                     initialize_data,
                                                     monkeypatch):
    session = load_db
    group = create_group
    commenter = create_test_user(session=session)
    case_author = test_user
    case, content = test_group_case

    GroupManagement.add_user_to_group(user_uuid=commenter.user_uuid,
                                      group_uuid=case.group_uuid,
                                      session=session)
    session.commit()

    comment_uuid = do_post_comment(user_uid=commenter.user_uid,
                                   content_uuid=content.content_uuid,
                                   comment_text='new comment',
                                   parent_comment_uuid=None).pop('uuid')

    with MockIterable() as mock_iterable:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI.track_event',
                            mock_iterable.track_event)
        log_comment_and_notify(user_uuid=commenter.user_uuid,
                               content_uuid=content.content_uuid,
                               comment_uuid=comment_uuid,
                               session=session,
                               iterable=IterableNotifier())

        expected_data_fields = {
            'caseCaption': content.caption,
            'caseTitle': content.title,
            'caseUuid': str(case.case_uuid),
            'commentUuid': str(comment_uuid),
            'receiverUuid': case_author['userUuid'],
            'receiverUid': case_author['userUid'],
            'groupUuid': str(group.groupUuid),
            'groupName': group.groupName,
            'caseClassification': 'medical',
            'caseMediaUrl': None,
            'commentText': 'new comment',
        }

        mock_iterable.assert_track_event_called(event=IterableEvent.COMMENT_YOUR_CASE,
                                                email=case_author['email'],
                                                user_uuid=case_author['userUuid'],
                                                data_fields=expected_data_fields)
        assert session.query(UserNotification) \
            .filter(UserNotification.user_uuid == case_author['userUuid'],
                    UserNotification.case_uuid == case.case_uuid,
                    UserNotification.comment_uuid == comment_uuid,
                    UserNotification.notification_type == UserNotificationType.COMMENT) \
            .first()

    session.query(UserNotification).filter(UserNotification.group_uuid == case.group_uuid).delete()
    session.query(GroupMember).filter(GroupMember.group_uuid == case.group_uuid).delete()


def test_comment_reply_notifies_comment_author(load_db, initialize_data, monkeypatch):
    session = load_db
    reply_author = create_test_user(session=session)
    receiver = create_test_user(session=session)

    case, content = create_test_case(author_uuid=receiver.user_uuid,
                                     is_paging_case=False,
                                     language=Locale.EN_US.code,
                                     title="Case Title",
                                     caption="Case Caption",
                                     state=CaseState.APPROVED,
                                     session=session)

    parent_comment_uuid = do_post_comment(user_uid=receiver.user_uid,
                                          content_uuid=content.content_uuid,
                                          comment_text='parent_comment',
                                          parent_comment_uuid=None).pop('uuid')
    reply_uuid = do_post_comment(user_uid=reply_author.user_uid,
                                 content_uuid=content.content_uuid,
                                 comment_text='reply',
                                 parent_comment_uuid=parent_comment_uuid).pop('uuid')
    session.commit()

    # Test successful notification
    with MockIterable() as mock_iterable:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI.track_event',
                            mock_iterable.track_event)

        expected_data_fields = {
            "caseTitle": content.title,
            "caseUuid": str(case.case_uuid),
            "commentUuid": str(reply_uuid),
            "mainCommentAuthorUuid": str(receiver.user_uuid),
            "receiverUuid": str(receiver.user_uuid),
            "respondentUuid": str(reply_author.user_uuid),
            "is_op": False,
            "groupUuid": None,
            "groupName": None,
            "caseClassification": "medical",
            "replyText": "reply",
            "caseMediaUrl": None,
            "caseAuthorUsername": receiver.username,
        }

        log_comment_and_notify(user_uuid=reply_author.user_uuid,
                               content_uuid=content.content_uuid,
                               comment_uuid=reply_uuid,
                               session=session,
                               iterable=IterableNotifier())
        mock_iterable.assert_track_event_called(event=IterableEvent.COMMENT_REPLY,
                                                email=receiver.email,
                                                user_uuid=receiver.user_uuid,
                                                data_fields=expected_data_fields)
    assert session.query(UserNotification) \
        .filter(UserNotification.user_uuid == receiver.user_uuid,
                UserNotification.case_uuid == case.case_uuid,
                UserNotification.comment_uuid == reply_uuid,
                UserNotification.notification_type == UserNotificationType.COMMENT_REPLY) \
        .first()

    assert not session.query(UserNotification) \
        .filter(UserNotification.user_uuid == receiver.user_uuid,
                UserNotification.case_uuid == case.case_uuid,
                UserNotification.comment_uuid == reply_uuid,
                UserNotification.notification_type == UserNotificationType.COMMENT) \
        .first()


def test_group_case_comment_reply_notifies_comment_author(load_db,
                                                          test_user,
                                                          create_group,
                                                          test_group_case,
                                                          initialize_data,
                                                          monkeypatch):
    session = load_db
    group = create_group
    reply_author = create_test_user(session=session)
    receiver = create_test_user(session=session)

    case, content = test_group_case
    GroupManagement.add_user_to_group(user_uuid=receiver.user_uuid,
                                      group_uuid=case.group_uuid,
                                      session=session)
    GroupManagement.add_user_to_group(user_uuid=reply_author.user_uuid,
                                      group_uuid=case.group_uuid,
                                      session=session)
    GroupManagement.add_user_to_group(user_uuid=test_user['userUuid'],
                                      group_uuid=case.group_uuid,
                                      session=session)
    session.commit()

    parent_comment_uuid = do_post_comment(user_uid=receiver.user_uid,
                                          content_uuid=content.content_uuid,
                                          comment_text='parent_comment',
                                          parent_comment_uuid=None).pop('uuid')
    reply_uuid = do_post_comment(user_uid=reply_author.user_uid,
                                 content_uuid=content.content_uuid,
                                 comment_text='reply',
                                 parent_comment_uuid=parent_comment_uuid).pop('uuid')
    reply_uuid2 = do_post_comment(user_uid=test_user['userUid'],
                                  content_uuid=content.content_uuid,
                                  comment_text='reply',
                                  parent_comment_uuid=parent_comment_uuid).pop('uuid')
    session.commit()

    # Test successful notification - is_op = False
    with MockIterable() as mock_iterable:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI.track_event',
                            mock_iterable.track_event)
        log_comment_and_notify(user_uuid=reply_author.user_uuid,
                               content_uuid=content.content_uuid,
                               comment_uuid=reply_uuid,
                               session=session,
                               iterable=IterableNotifier())

        expected_data_fields = {
            'caseTitle': content.title,
            'caseUuid': str(case.case_uuid),
            'commentUuid': str(reply_uuid),
            'mainCommentAuthorUuid': str(receiver.user_uuid),
            'receiverUuid': str(receiver.user_uuid),
            'respondentUuid': str(reply_author.user_uuid),
            'is_op': False,
            'groupUuid': str(group.groupUuid),
            'groupName': group.groupName,
            'caseClassification': 'medical',
            'caseMediaUrl': None,
            'caseAuthorUsername': test_user.get('username'),
            'replyText': 'reply',
        }
        mock_iterable.assert_track_event_called(event=IterableEvent.COMMENT_REPLY,
                                                email=receiver.email,
                                                user_uuid=receiver.user_uuid,
                                                data_fields=expected_data_fields)
    assert session.query(UserNotification) \
        .filter(UserNotification.user_uuid == receiver.user_uuid,
                UserNotification.case_uuid == case.case_uuid,
                UserNotification.comment_uuid == reply_uuid,
                UserNotification.notification_type == UserNotificationType.COMMENT_REPLY) \
        .first()

    # # Test successful notification - is_op = True
    with MockIterable() as mock_iterable:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI.track_event',
                            mock_iterable.track_event)
        log_comment_and_notify(user_uuid=test_user['userUuid'],
                               content_uuid=content.content_uuid,
                               comment_uuid=reply_uuid2,
                               session=session,
                               iterable=IterableNotifier())

        expected_data_fields = {
            'caseTitle': content.title,
            'caseUuid': str(case.case_uuid),
            'commentUuid': str(reply_uuid2),
            'mainCommentAuthorUuid': str(receiver.user_uuid),
            'receiverUuid': str(receiver.user_uuid),
            'respondentUuid': str(test_user['userUuid']),
            'is_op': True,
            'groupUuid': str(group.groupUuid),
            'groupName': group.groupName,
            'caseClassification': 'medical',
            'caseMediaUrl': None,
            'caseAuthorUsername': test_user.get('username'),
            'replyText': 'reply',
        }
        mock_iterable.assert_track_event_called(event=IterableEvent.COMMENT_REPLY,
                                                email=receiver.email,
                                                user_uuid=receiver.user_uuid,
                                                data_fields=expected_data_fields)
    assert session.query(UserNotification) \
        .filter(UserNotification.user_uuid == receiver.user_uuid,
                UserNotification.case_uuid == case.case_uuid,
                UserNotification.comment_uuid == reply_uuid2,
                UserNotification.notification_type == UserNotificationType.COMMENT_REPLY_OP) \
        .first()

    session.query(UserNotification).filter(UserNotification.group_uuid == case.group_uuid).delete()
    session.query(GroupMember).filter(GroupMember.group_uuid == case.group_uuid).delete()


def test_anonymous_case_author_comment_reply_notifies_comment_author(load_db, initialize_data, monkeypatch):
    session = load_db
    case_author = create_test_user(session=session)
    comment_author = create_test_user(session=session)

    anonymous_case, anonymous_content = create_test_case(author_uuid=case_author.user_uuid,
                                                         is_paging_case=False,
                                                         language=Locale.EN_US.code,
                                                         title='Case Title',
                                                         caption='Case Caption',
                                                         state=CaseState.APPROVED,
                                                         is_anonymous=True,
                                                         session=session)

    parent_comment_uuid = do_post_comment(user_uid=comment_author.user_uid,
                                          content_uuid=anonymous_content.content_uuid,
                                          comment_text='parent_comment',
                                          parent_comment_uuid=None).pop('uuid')
    reply_uuid = do_post_comment(user_uid=case_author.user_uid,
                                 content_uuid=anonymous_content.content_uuid,
                                 comment_text='reply',
                                 parent_comment_uuid=parent_comment_uuid).pop('uuid')
    session.commit()

    with MockIterable() as mock_iterable:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI.track_event',
                            mock_iterable.track_event)
        log_comment_and_notify(user_uuid=case_author.user_uuid,
                               content_uuid=anonymous_content.content_uuid,
                               comment_uuid=reply_uuid,
                               session=session,
                               iterable=IterableNotifier())

        expected_data_fields = {
            'caseTitle': anonymous_content.title,
            'caseUuid': str(anonymous_case.case_uuid),
            'commentUuid': str(reply_uuid),
            'mainCommentAuthorUuid': str(comment_author.user_uuid),
            'receiverUuid': str(comment_author.user_uuid),
            'is_op': True,
            'groupUuid': None,
            'groupName': None,
            'caseClassification': 'medical',
            'replyText': 'reply',
            'caseMediaUrl': None,
            'caseAuthorUsername': case_author.username,
        }

        mock_iterable.assert_track_event_called(event=IterableEvent.COMMENT_REPLY,
                                                email=comment_author.email,
                                                user_uuid=comment_author.user_uuid,
                                                data_fields=expected_data_fields)


def test_new_author_comment_notifies_users_who_saved_case(load_db, initialize_data, monkeypatch):
    session = load_db
    case_author = create_test_user(session=session)
    user_who_saved_case = create_test_user(session=session)

    case, content = create_test_case(author_uuid=case_author.user_uuid,
                                     is_paging_case=False,
                                     language=Locale.EN_US.code,
                                     title='Case Title',
                                     caption='Case Caption',
                                     state=CaseState.APPROVED,
                                     session=session)
    anonymous_case, anonymous_content = create_test_case(author_uuid=case_author.user_uuid,
                                                         is_paging_case=False,
                                                         language=Locale.EN_US.code,
                                                         title='Case Title',
                                                         caption='Case Caption',
                                                         state=CaseState.APPROVED,
                                                         is_anonymous=True,
                                                         session=session)
    UserSavedCase.create(case_uuid=case.case_uuid,
                         user_uuid=user_who_saved_case.user_uuid,
                         session=session)
    UserSavedCase.create(case_uuid=case.case_uuid,
                         user_uuid=case_author.user_uuid,
                         session=session)
    UserSavedCase.create(case_uuid=anonymous_case.case_uuid,
                         user_uuid=user_who_saved_case.user_uuid,
                         session=session)
    UserSavedCase.create(case_uuid=anonymous_case.case_uuid,
                         user_uuid=case_author.user_uuid,
                         session=session)
    comment_uuid = do_post_comment(user_uid=case_author.user_uid,
                                   content_uuid=content.content_uuid,
                                   comment_text='reply',
                                   parent_comment_uuid=None).pop('uuid')
    anonymous_comment_uuid = do_post_comment(user_uid=case_author.user_uid,
                                             content_uuid=anonymous_content.content_uuid,
                                             comment_text='reply',
                                             parent_comment_uuid=None).pop('uuid')
    session.commit()

    with MockIterable() as mock_iterable:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI.track_event',
                            mock_iterable.track_event)

        expected_data_fields = {
            'caseCaption': content.caption,
            'caseTitle': content.title,
            'caseUuid': str(case.case_uuid),
            'commentUuid': str(comment_uuid),
            'is_OP': True,
            'caseAuthorEmail': [case_author.email],
            'caseAuthorUsername': [case_author.username],
            'caseAuthorsUUID': [str(case_author.user_uuid)],
            'commenterUUID': str(case_author.user_uuid),
            'receiverUuid': str(user_who_saved_case.user_uuid),
            'groupUuid': None,
            'groupName': None,
            'caseClassification': 'medical',
            'caseMediaUrl': None,
            'commentText': 'reply',
        }

        log_comment_and_notify(user_uuid=case_author.user_uuid,
                               content_uuid=content.content_uuid,
                               comment_uuid=comment_uuid,
                               session=session,
                               iterable=IterableNotifier())

        mock_iterable.assert_track_event_called(event=IterableEvent.COMMENT_SAVED_CASE,
                                                email=user_who_saved_case.email,
                                                user_uuid=user_who_saved_case.user_uuid,
                                                data_fields=expected_data_fields)

    assert session.query(UserNotification) \
        .filter(UserNotification.user_uuid == user_who_saved_case.user_uuid,
                UserNotification.case_uuid == case.case_uuid,
                UserNotification.comment_uuid == comment_uuid,
                UserNotification.notification_type == UserNotificationType.COMMENT_SAVED_CASE_OP) \
        .first()

    assert not session.query(UserNotification) \
        .filter(UserNotification.user_uuid == case_author.user_uuid,
                UserNotification.case_uuid == case.case_uuid,
                UserNotification.comment_uuid == comment_uuid,
                UserNotification.notification_type == UserNotificationType.COMMENT_SAVED_CASE_OP) \
        .first()

    # The case is anonymous
    with MockIterable() as mock_iterable:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI.track_event',
                            mock_iterable.track_event)
        log_comment_and_notify(user_uuid=case_author.user_uuid,
                               content_uuid=anonymous_content.content_uuid,
                               comment_uuid=anonymous_comment_uuid,
                               session=session,
                               iterable=IterableNotifier())

        assert session.query(UserNotification) \
            .filter(UserNotification.user_uuid == user_who_saved_case.user_uuid,
                    UserNotification.case_uuid == anonymous_case.case_uuid,
                    UserNotification.comment_uuid == anonymous_comment_uuid,
                    UserNotification.notification_type == UserNotificationType.COMMENT_SAVED_CASE_OP) \
            .first()

        expected_data_fields = {
            'caseCaption': anonymous_content.caption,
            'caseTitle': anonymous_content.title,
            'caseUuid': str(anonymous_case.case_uuid),
            'commentUuid': str(anonymous_comment_uuid),
            'is_OP': True,
            'receiverUuid': str(user_who_saved_case.user_uuid),
            'groupUuid': None,
            'groupName': None,
            'caseClassification': 'medical',
            'caseMediaUrl': None,
            'commentText': 'reply',
        }

        mock_iterable.assert_track_event_called(event=IterableEvent.COMMENT_SAVED_CASE,
                                                email=user_who_saved_case.email,
                                                user_uuid=user_who_saved_case.user_uuid,
                                                data_fields=expected_data_fields)


def test_new_comment_notifies_users_who_saved_case(load_db, initialize_data, monkeypatch):
    session = load_db
    case_author = create_test_user(session=session)
    comment_author = create_test_user(session=session)
    receiver = create_test_user(session=session)

    case, content = create_test_case(author_uuid=case_author.user_uuid,
                                     is_paging_case=False,
                                     language=Locale.EN_US.code,
                                     title="Case Title",
                                     caption="Case Caption",
                                     state=CaseState.APPROVED,
                                     session=session)

    comment_uuid = do_post_comment(user_uid=comment_author.user_uid,
                                   content_uuid=content.content_uuid,
                                   comment_text='reply',
                                   parent_comment_uuid=None).pop('uuid')
    session.commit()

    # Test successful notification
    UserSavedCase.create(case_uuid=case.case_uuid,
                         user_uuid=receiver.user_uuid,
                         session=session)
    session.commit()

    with MockIterable() as mock_iterable:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI.track_event',
                            mock_iterable.track_event)

        expected_data_fields = {
            'caseCaption': content.caption,
            'caseTitle': content.title,
            'caseUuid': str(case.case_uuid),
            'commentUuid': str(comment_uuid),
            'is_OP': False,
            'caseAuthorEmail': [case_author.email],
            'caseAuthorUsername': [case_author.username],
            'caseAuthorsUUID': [str(case_author.user_uuid)],
            'commenterUUID': str(comment_author.user_uuid),
            'receiverUuid': str(receiver.user_uuid),
            'groupUuid': None,
            'groupName': None,
            'caseClassification': 'medical',
            'caseMediaUrl': None,
            'commentText': 'reply',
        }

        log_comment_and_notify(user_uuid=comment_author.user_uuid,
                               content_uuid=content.content_uuid,
                               comment_uuid=comment_uuid,
                               session=session,
                               iterable=IterableNotifier())
        mock_iterable.assert_track_event_called(event=IterableEvent.COMMENT_SAVED_CASE,
                                                email=receiver.email,
                                                user_uuid=receiver.user_uuid,
                                                data_fields=expected_data_fields)
    assert session.query(UserNotification) \
        .filter(UserNotification.user_uuid == receiver.user_uuid,
                UserNotification.case_uuid == case.case_uuid,
                UserNotification.comment_uuid == comment_uuid,
                UserNotification.notification_type == UserNotificationType.COMMENT_SAVED_CASE) \
        .first()

    assert not session.query(UserNotification) \
        .filter(UserNotification.user_uuid == case_author.user_uuid,
                UserNotification.case_uuid == case.case_uuid,
                UserNotification.comment_uuid == comment_uuid,
                UserNotification.notification_type == UserNotificationType.COMMENT_SAVED_CASE) \
        .first()


def test_group_case_comment_notifies_users_saved_case(load_db,
                                                      test_user,
                                                      create_group,
                                                      test_group_case,
                                                      initialize_data,
                                                      monkeypatch):
    session = load_db
    group = create_group
    case_author = test_user
    user_who_saved_case = create_test_user(session=session)
    another_user = create_test_user(session=session)

    case, content = test_group_case
    GroupManagement.add_user_to_group(user_uuid=case_author['userUuid'],
                                      group_uuid=case.group_uuid,
                                      session=session)
    GroupManagement.add_user_to_group(user_uuid=user_who_saved_case.user_uuid,
                                      group_uuid=case.group_uuid,
                                      session=session)
    GroupManagement.add_user_to_group(user_uuid=another_user.user_uuid,
                                      group_uuid=case.group_uuid,
                                      session=session)
    user_save_case(session, case.case_uuid, user_who_saved_case.user_uuid)
    session.commit()

    comment_uuid1 = do_post_comment(user_uid=case_author['userUid'],
                                    content_uuid=content.content_uuid,
                                    comment_text='reply').pop('uuid')
    session.commit()

    # Test successful notification - is_OP is True
    with MockIterable() as mock_iterable:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI.track_event',
                            mock_iterable.track_event)
        log_comment_and_notify(user_uuid=case_author['userUuid'],
                               content_uuid=content.content_uuid,
                               comment_uuid=comment_uuid1,
                               session=session,
                               iterable=IterableNotifier())

        expected_data_fields = {
            'caseCaption': content.caption,
            'caseTitle': content.title,
            'caseUuid': str(case.case_uuid),
            'commentUuid': str(comment_uuid1),
            'is_OP': True,
            'caseAuthorEmail': [case_author['email']],
            'caseAuthorUsername': [case_author['username']],
            'caseAuthorsUUID': [case_author['userUuid']],
            'commenterUUID': str(case_author['userUuid']),
            'receiverUuid': str(user_who_saved_case.user_uuid),
            'groupUuid': str(group.groupUuid),
            'groupName': group.groupName,
            'caseClassification': 'medical',
            'caseMediaUrl': None,
            'commentText': 'reply',
        }
        mock_iterable.assert_track_event_called(event=IterableEvent.COMMENT_SAVED_CASE,
                                                email=user_who_saved_case.email,
                                                user_uuid=user_who_saved_case.user_uuid,
                                                data_fields=expected_data_fields)
    assert session.query(UserNotification) \
        .filter(UserNotification.user_uuid == user_who_saved_case.user_uuid,
                UserNotification.case_uuid == case.case_uuid,
                UserNotification.comment_uuid == comment_uuid1,
                UserNotification.notification_type == UserNotificationType.COMMENT_SAVED_CASE_OP) \
        .first()

    # Test successful notification - is_OP is False
    comment_uuid2 = do_post_comment(user_uid=another_user.user_uid,
                                    content_uuid=content.content_uuid,
                                    comment_text='reply').pop('uuid')

    with MockIterable() as mock_iterable:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI.track_event',
                            mock_iterable.track_event)
        log_comment_and_notify(user_uuid=another_user.user_uuid,
                               content_uuid=content.content_uuid,
                               comment_uuid=comment_uuid2,
                               session=session,
                               iterable=IterableNotifier())

        expected_data_fields = {
            'caseCaption': content.caption,
            'caseTitle': content.title,
            'caseUuid': str(case.case_uuid),
            'commentUuid': str(comment_uuid2),
            'is_OP': False,
            'caseAuthorEmail': [case_author['email']],
            'caseAuthorUsername': [case_author['username']],
            'caseAuthorsUUID': [case_author['userUuid']],
            'commenterUUID': str(another_user.user_uuid),
            'receiverUuid': str(user_who_saved_case.user_uuid),
            'groupUuid': str(group.groupUuid),
            'groupName': group.groupName,
            'caseClassification': 'medical',
            'caseMediaUrl': None,
            'commentText': 'reply',
        }
        mock_iterable.assert_track_event_called(event=IterableEvent.COMMENT_SAVED_CASE,
                                                email=user_who_saved_case.email,
                                                user_uuid=user_who_saved_case.user_uuid,
                                                data_fields=expected_data_fields)
    assert session.query(UserNotification) \
        .filter(UserNotification.user_uuid == user_who_saved_case.user_uuid,
                UserNotification.case_uuid == case.case_uuid,
                UserNotification.comment_uuid == comment_uuid2,
                UserNotification.notification_type == UserNotificationType.COMMENT_SAVED_CASE) \
        .first()

    session.query(UserNotification).filter(UserNotification.group_uuid == case.group_uuid).delete()
    session.query(GroupMember).filter(GroupMember.group_uuid == case.group_uuid).delete()
    session.flush()


def test_new_comment_doesnt_notify_commenter_himself_who_saved_case(load_db, initialize_data, monkeypatch):
    session = load_db
    case_author = create_test_user(session=session)
    comment_author = create_test_user(session=session)
    another_receiver = create_test_user(session=session)

    case, content = create_test_case(author_uuid=case_author.user_uuid,
                                     is_paging_case=False,
                                     language=Locale.EN_US.code,
                                     title="Case Title",
                                     caption="Case Caption",
                                     state=CaseState.APPROVED,
                                     session=session)

    comment_uuid = do_post_comment(user_uid=comment_author.user_uid,
                                   content_uuid=content.content_uuid,
                                   comment_text='reply',
                                   parent_comment_uuid=None).pop('uuid')
    session.commit()

    # Test notification on commenter and another user who both save the case
    UserSavedCase.create(case_uuid=case.case_uuid,
                         user_uuid=comment_author.user_uuid,
                         session=session)

    UserSavedCase.create(case_uuid=case.case_uuid,
                         user_uuid=another_receiver.user_uuid,
                         session=session)
    session.commit()

    with MockIterable() as mock_iterable:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI.track_event',
                            mock_iterable.track_event)
        log_comment_and_notify(user_uuid=comment_author.user_uuid,
                               content_uuid=content.content_uuid,
                               comment_uuid=comment_uuid,
                               session=session,
                               iterable=IterableNotifier())
        mock_iterable.assert_track_event_called(event=IterableEvent.COMMENT_SAVED_CASE,
                                                email=another_receiver.email,
                                                user_uuid=another_receiver.user_uuid)
    assert session.query(UserNotification) \
        .filter(UserNotification.user_uuid == another_receiver.user_uuid,
                UserNotification.case_uuid == case.case_uuid,
                UserNotification.comment_uuid == comment_uuid,
                UserNotification.notification_type == UserNotificationType.COMMENT_SAVED_CASE) \
        .first()

    assert not session.query(UserNotification) \
        .filter(UserNotification.user_uuid == case_author.user_uuid,
                UserNotification.case_uuid == case.case_uuid,
                UserNotification.comment_uuid == comment_uuid,
                UserNotification.notification_type == UserNotificationType.COMMENT_SAVED_CASE) \
        .first()

    assert not session.query(UserNotification) \
        .filter(UserNotification.user_uuid == comment_author.user_uuid,
                UserNotification.case_uuid == case.case_uuid,
                UserNotification.comment_uuid == comment_uuid,
                UserNotification.notification_type == UserNotificationType.COMMENT_SAVED_CASE) \
        .first()


def test_new_diagnosis_notifies_users(load_db, approved_case_and_content, users, monkeypatch):
    case, content = approved_case_and_content
    session = load_db

    users_commented_case = users[:3]
    users_saved_case = users[2:5]
    users_liked_case = [users[0], users[2], users[4], users[5]]

    for each in users_commented_case:
        user_comment_case(session, content.content_uuid, each.user_uuid)

    for each in users_saved_case:
        user_save_case(session, case.case_uuid, each.user_uuid)

    for each in users_liked_case:
        user_like_case(session, case.case_uuid, each.user_uuid)

    # all_users = [u1, u2, u3, u4, u5, u6]
    # users_commented_case = [u1, u2, u3]
    # users_saved_case = [u3, u4, u5]
    # users_liked_case = [u1, u3, u5, u6]
    # We want to send "COMMENTED_CASE_DIAGNOSIS" to u1, u2, u3
    #            send "SAVED_CASE_DIAGNOSIS" to u4, u5
    #            send "LIKED_CASE_DIAGNOSIS" to u6

    case_author = session.query(CaseAuthor).filter(CaseAuthor.case_uuid == case.case_uuid).one()

    with MockIterable() as mock_iterable:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI.track_event',
                            mock_iterable.track_event)
        log_case_update(case_uuid=str(case.case_uuid),
                        author_uuid=case_author.author_uuid,
                        previous_label='unresolved',
                        current_label='resolved',
                        is_diagnosis=True,
                        session=session,
                        iterable=IterableNotifier())
        assert mock_iterable.call_count == 6

    for each_user in users_commented_case:
        assert session.query(UserNotification) \
            .filter(UserNotification.user_uuid == each_user.user_uuid,
                    UserNotification.case_uuid == case.case_uuid,
                    UserNotification.notification_type == UserNotificationType.COMMENTED_CASE_DIAGNOSIS) \
            .count() == 1

    for each_user in users_saved_case[1:]:
        assert session.query(UserNotification) \
            .filter(UserNotification.user_uuid == each_user.user_uuid,
                    UserNotification.case_uuid == case.case_uuid,
                    UserNotification.notification_type == UserNotificationType.SAVED_CASE_DIAGNOSIS) \
            .count() == 1

    assert session.query(UserNotification) \
        .filter(UserNotification.user_uuid == users_saved_case[0].user_uuid,
                UserNotification.case_uuid == case.case_uuid,
                UserNotification.notification_type == UserNotificationType.SAVED_CASE_DIAGNOSIS) \
        .one_or_none() is None

    for each_user in users_liked_case[:-1]:
        assert session.query(UserNotification) \
            .filter(UserNotification.user_uuid == each_user.user_uuid,
                    UserNotification.case_uuid == case.case_uuid,
                    UserNotification.notification_type == UserNotificationType.LIKED_CASE_DIAGNOSIS) \
            .one_or_none() is None

    assert session.query(UserNotification) \
        .filter(UserNotification.user_uuid == users_liked_case[-1].user_uuid,
                UserNotification.case_uuid == case.case_uuid,
                UserNotification.notification_type == UserNotificationType.LIKED_CASE_DIAGNOSIS) \
        .count() == 1


def test_new_post_diagnosis_should_not_notify_users(load_db, approved_post_and_content, users, monkeypatch):
    post, content = approved_post_and_content
    session = load_db

    users_commented_post = users[:3]
    users_saved_post = users[2:5]
    users_liked_post = [users[0], users[2], users[4], users[5]]

    for each in users_commented_post:
        user_comment_case(session, content.content_uuid, each.user_uuid)

    for each in users_saved_post:
        user_save_case(session, post.case_uuid, each.user_uuid)

    for each in users_liked_post:
        user_like_case(session, post.case_uuid, each.user_uuid)

    # all_users = [u1, u2, u3, u4, u5, u6]
    # users_commented_case = [u1, u2, u3]
    # users_saved_case = [u3, u4, u5]
    # users_liked_case = [u1, u3, u5, u6]
    # We should not send any notifications to all_users

    post_author = session.query(CaseAuthor).filter(CaseAuthor.case_uuid == post.case_uuid).one()

    with MockIterable() as mock_iterable:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI.track_event',
                            mock_iterable.track_event)
        log_case_update(case_uuid=str(post.case_uuid),
                        author_uuid=post_author.author_uuid,
                        previous_label='unresolved',
                        current_label='resolved',
                        is_diagnosis=True,
                        session=session,
                        iterable=IterableNotifier())
        mock_iterable.assert_not_called()

    for each_user in users_commented_post:
        assert session.query(UserNotification) \
            .filter(UserNotification.user_uuid == each_user.user_uuid,
                    UserNotification.case_uuid == post.case_uuid,
                    UserNotification.notification_type == UserNotificationType.COMMENTED_CASE_DIAGNOSIS) \
            .count() == 0

    for each_user in users_saved_post[1:]:
        assert session.query(UserNotification) \
            .filter(UserNotification.user_uuid == each_user.user_uuid,
                    UserNotification.case_uuid == post.case_uuid,
                    UserNotification.notification_type == UserNotificationType.SAVED_CASE_DIAGNOSIS) \
            .count() == 0

    assert session.query(UserNotification) \
        .filter(UserNotification.user_uuid == users_saved_post[0].user_uuid,
                UserNotification.case_uuid == post.case_uuid,
                UserNotification.notification_type == UserNotificationType.SAVED_CASE_DIAGNOSIS) \
        .one_or_none() is None

    for each_user in users_liked_post[:-1]:
        assert session.query(UserNotification) \
            .filter(UserNotification.user_uuid == each_user.user_uuid,
                    UserNotification.case_uuid == post.case_uuid,
                    UserNotification.notification_type == UserNotificationType.LIKED_CASE_DIAGNOSIS) \
            .one_or_none() is None

    assert session.query(UserNotification) \
        .filter(UserNotification.user_uuid == users_liked_post[-1].user_uuid,
                UserNotification.case_uuid == post.case_uuid,
                UserNotification.notification_type == UserNotificationType.LIKED_CASE_DIAGNOSIS) \
        .count() == 0


def test_new_group_case_diagnosis_notifies_users(load_db, test_user, test_group_case, users, monkeypatch):
    case, content = test_group_case
    session = load_db

    user_commented_case = users[0]
    user_saved_case = users[1]
    user_liked_case = users[2]

    user_comment_case(session, content.content_uuid, user_commented_case.user_uuid)
    user_save_case(session, case.case_uuid, user_saved_case.user_uuid)
    user_like_case(session, case.case_uuid, user_liked_case.user_uuid)

    # all_users = [u1, u2, u3]
    # users_commented_case = u1
    # users_saved_case = u2
    # users_liked_case = u3
    # We want to send "COMMENTED_CASE_DIAGNOSIS" to u1
    #            send "SAVED_CASE_DIAGNOSIS" to u2
    #            send "LIKED_CASE_DIAGNOSIS" to u3

    case_author = session.query(CaseAuthor).filter(CaseAuthor.case_uuid == case.case_uuid).one()
    group = GroupManagement.get_group(group_uuid=case.group_uuid, session=session)
    with MockIterable() as mock_iterable:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI.track_event',
                            mock_iterable.track_event)
        log_case_update(case_uuid=str(case.case_uuid),
                        author_uuid=case_author.author_uuid,
                        previous_label='unresolved',
                        current_label='resolved',
                        is_diagnosis=True,
                        session=session,
                        iterable=IterableNotifier())
        assert mock_iterable.call_count == 3

        expected_data_fields1 = {
            'caseTitle': content.title,
            'caseUuid': str(case.case_uuid),
            'caseCurrentStatus': 'resolved',
            'casePreviousStatus': 'unresolved',
            'diagnosisUpdateAdded': True,
            'authorUsername': test_user['username'],
            'groupUuid': str(case.group_uuid),
            'groupName': group.groupName,
            'caseMediaUrl': None,
        }

    assert session.query(UserNotification) \
        .filter(UserNotification.user_uuid == user_commented_case.user_uuid,
                UserNotification.case_uuid == case.case_uuid,
                UserNotification.notification_type == UserNotificationType.COMMENTED_CASE_DIAGNOSIS) \
        .count() == 1
    mock_iterable.assert_track_event_called(event=IterableEvent.CASE_NEW_UPDATE,
                                            email=user_commented_case.email,
                                            user_uuid=user_commented_case.user_uuid,
                                            data_fields=expected_data_fields1)

    assert session.query(UserNotification) \
        .filter(UserNotification.user_uuid == user_saved_case.user_uuid,
                UserNotification.case_uuid == case.case_uuid,
                UserNotification.notification_type == UserNotificationType.SAVED_CASE_DIAGNOSIS) \
        .count() == 1
    mock_iterable.assert_track_event_called(event=IterableEvent.CASE_NEW_UPDATE,
                                            email=user_saved_case.email,
                                            user_uuid=user_saved_case.user_uuid,
                                            data_fields=expected_data_fields1)

    assert session.query(UserNotification) \
        .filter(UserNotification.user_uuid == user_liked_case.user_uuid,
                UserNotification.case_uuid == case.case_uuid,
                UserNotification.notification_type == UserNotificationType.LIKED_CASE_DIAGNOSIS) \
        .count() == 1
    mock_iterable.assert_track_event_called(event=IterableEvent.CASE_NEW_UPDATE,
                                            email=user_liked_case.email,
                                            user_uuid=user_liked_case.user_uuid,
                                            data_fields=expected_data_fields1)


def test_new_accepted_answer_notifies_users(load_db, test_user, approved_case_and_content, users, monkeypatch):
    case, content = approved_case_and_content
    session = load_db

    accepted_answer_author = users[0]
    users_commented_case = users[:2]
    users_liked_case = users[2:5]
    users_saved_case = [users[0], users[2], users[4], users[5]]

    comment_uuid = do_post_comment(user_uid=accepted_answer_author.user_uid,
                                   content_uuid=content.content_uuid,
                                   comment_text='Accepted Answer',
                                   parent_comment_uuid=None).pop('uuid')
    comment = Comment.get_comment(comment_uuid=comment_uuid, session=session)
    comment.is_accepted_answer = True
    session.merge(comment)
    session.commit()

    for each in users_commented_case:
        user_comment_case(session, content.content_uuid, each.user_uuid)

    for each in users_saved_case:
        user_save_case(session, case.case_uuid, each.user_uuid)

    for each in users_liked_case:
        user_like_case(session, case.case_uuid, each.user_uuid)

    # all_users = [u1, u2, u3, u4, u5, u6]
    # accepted_answer_author = u1
    # users_commented_case = [u1, u2, u3]
    # users_liked_case = [u3, u4, u5]
    # users_saved_case = [u1, u3, u5, u6]
    # We want to send "NEW_ACCEPTED_ANSWER_SELECTED" to u1
    #            send "NEW_ACCEPTED_ANSWER_COMMENTED_CASE" to u2, u3
    #            send "NEW_ACCEPTED_ANSWER_LIKED_CASE" to u4, u5
    #            send "NEW_ACCEPTED_ANSWER_SAVED_CASE" to u6

    author_uuid = accepted_answer_author.user_uuid
    with MockIterable() as mock_iterable:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI.track_event',
                            mock_iterable.track_event)

        expected_data_fields = {
            'caseTitle': content.title,
            'caseCaption': content.caption,
            'caseMediaUrl': None,
            'caseUuid': str(case.case_uuid),
            'commentUuid': str(comment_uuid),
            'authorUsername': test_user.get('username'),
            'deletionReason': None,
        }

        notifies_users_of_new_accepted_answer(source_user_uuid=author_uuid,
                                              comment_uuid=comment_uuid,
                                              case_uuid=str(case.case_uuid),
                                              session=session,
                                              iterable=IterableNotifier())
        mock_iterable.assert_track_event_called(event=IterableEvent.CASE_NEW_ACCEPTED_ANSWER,
                                                email=users[1].email,
                                                user_uuid=str(users[1].user_uuid),
                                                data_fields=expected_data_fields)

        assert mock_iterable.call_count == 6

    assert session.query(UserNotification) \
        .filter(UserNotification.user_uuid == accepted_answer_author.user_uuid,
                UserNotification.case_uuid == case.case_uuid,
                UserNotification.notification_type == UserNotificationType.NEW_ACCEPTED_ANSWER_SELECTED) \
        .count() == 1

    assert session.query(UserNotification) \
        .filter(UserNotification.user_uuid == accepted_answer_author.user_uuid,
                UserNotification.case_uuid == case.case_uuid) \
        .count() == 1

    for each_user in users_commented_case[1:]:
        assert session.query(UserNotification) \
            .filter(UserNotification.user_uuid == each_user.user_uuid,
                    UserNotification.case_uuid == case.case_uuid,
                    UserNotification.notification_type == UserNotificationType.NEW_ACCEPTED_ANSWER_COMMENTED_CASE) \
            .count() == 1

        assert session.query(UserNotification) \
            .filter(UserNotification.user_uuid == each_user.user_uuid,
                    UserNotification.case_uuid == case.case_uuid) \
            .count() == 1

    for each_user in users_liked_case[1:]:
        assert session.query(UserNotification) \
            .filter(UserNotification.user_uuid == each_user.user_uuid,
                    UserNotification.case_uuid == case.case_uuid,
                    UserNotification.notification_type == UserNotificationType.NEW_ACCEPTED_ANSWER_LIKED_CASE) \
            .count() == 1
        assert session.query(UserNotification) \
            .filter(UserNotification.user_uuid == each_user.user_uuid,
                    UserNotification.case_uuid == case.case_uuid) \
            .count() == 1

    assert session.query(UserNotification) \
        .filter(UserNotification.user_uuid == users_saved_case[-1].user_uuid,
                UserNotification.case_uuid == case.case_uuid,
                UserNotification.notification_type == UserNotificationType.NEW_ACCEPTED_ANSWER_SAVED_CASE) \
        .count() == 1
    assert session.query(UserNotification) \
        .filter(UserNotification.user_uuid == users_saved_case[-1].user_uuid,
                UserNotification.case_uuid == case.case_uuid) \
        .count() == 1


def test_new_post_accepted_answer_should_not_notify_users(load_db, test_user,
                                                          approved_post_and_content,
                                                          users, monkeypatch):
    post, content = approved_post_and_content
    session = load_db

    accepted_answer_author = users[0]
    users_commented_post = users[:2]
    users_liked_post = users[2:5]
    users_saved_post = [users[0], users[2], users[4], users[5]]

    comment_uuid = do_post_comment(user_uid=accepted_answer_author.user_uid,
                                   content_uuid=content.content_uuid,
                                   comment_text='Accepted Answer',
                                   parent_comment_uuid=None).pop('uuid')
    comment = Comment.get_comment(comment_uuid=comment_uuid, session=session)
    comment.is_accepted_answer = True
    session.merge(comment)
    session.commit()

    for each in users_commented_post:
        user_comment_case(session, content.content_uuid, each.user_uuid)

    for each in users_saved_post:
        user_save_case(session, post.case_uuid, each.user_uuid)

    for each in users_liked_post:
        user_like_case(session, post.case_uuid, each.user_uuid)

    # all_users = [u1, u2, u3, u4, u5, u6]
    # accepted_answer_author = u1
    # users_commented_post = [u1, u2, u3]
    # users_liked_post = [u3, u4, u5]
    # users_saved_post = [u1, u3, u5, u6]
    # We should not send any notifications to any of all_users

    author_uuid = accepted_answer_author.user_uuid
    with MockIterable() as mock_iterable:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI.track_event',
                            mock_iterable.track_event)

        notifies_users_of_new_accepted_answer(source_user_uuid=author_uuid,
                                              comment_uuid=comment_uuid,
                                              case_uuid=str(post.case_uuid),
                                              session=session,
                                              iterable=IterableNotifier())
        mock_iterable.assert_not_called()

    assert session.query(UserNotification) \
        .filter(UserNotification.user_uuid == accepted_answer_author.user_uuid,
                UserNotification.case_uuid == post.case_uuid,
                UserNotification.notification_type == UserNotificationType.NEW_ACCEPTED_ANSWER_SELECTED) \
        .count() == 0

    assert session.query(UserNotification) \
        .filter(UserNotification.user_uuid == accepted_answer_author.user_uuid,
                UserNotification.case_uuid == post.case_uuid) \
        .count() == 0

    for each_user in users_commented_post[1:]:
        assert session.query(UserNotification) \
            .filter(UserNotification.user_uuid == each_user.user_uuid,
                    UserNotification.case_uuid == post.case_uuid,
                    UserNotification.notification_type == UserNotificationType.NEW_ACCEPTED_ANSWER_COMMENTED_CASE) \
            .count() == 0

        assert session.query(UserNotification) \
            .filter(UserNotification.user_uuid == each_user.user_uuid,
                    UserNotification.case_uuid == post.case_uuid) \
            .count() == 0

    for each_user in users_liked_post[1:]:
        assert session.query(UserNotification) \
            .filter(UserNotification.user_uuid == each_user.user_uuid,
                    UserNotification.case_uuid == post.case_uuid,
                    UserNotification.notification_type == UserNotificationType.NEW_ACCEPTED_ANSWER_LIKED_CASE) \
            .count() == 0
        assert session.query(UserNotification) \
            .filter(UserNotification.user_uuid == each_user.user_uuid,
                    UserNotification.case_uuid == post.case_uuid) \
            .count() == 0

    assert session.query(UserNotification) \
        .filter(UserNotification.user_uuid == users_saved_post[-1].user_uuid,
                UserNotification.case_uuid == post.case_uuid,
                UserNotification.notification_type == UserNotificationType.NEW_ACCEPTED_ANSWER_SAVED_CASE) \
        .count() == 0
    assert session.query(UserNotification) \
        .filter(UserNotification.user_uuid == users_saved_post[-1].user_uuid,
                UserNotification.case_uuid == post.case_uuid) \
        .count() == 0


def test_accepted_answer_deleted_notifies_users(load_db, approved_case_and_content, test_user, monkeypatch):
    session = load_db

    case_author_uuid = test_user.get('userUuid')
    commenter = create_test_user(session=session)
    case, content = approved_case_and_content

    comment_uuid = do_post_comment(user_uid=commenter.user_uid,
                                   content_uuid=content.content_uuid,
                                   comment_text='Accepted Answer',
                                   parent_comment_uuid=None).pop('uuid')
    comment = Comment.get_comment(comment_uuid=comment_uuid, session=session)
    comment.is_accepted_answer = True
    comment.rejection_reason = CommentRejectionReason.UNSUPPORTED
    session.merge(comment)
    session.commit()

    with MockIterable() as mock_iterable:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI.track_event',
                            mock_iterable.track_event)
        notifies_users_of_accepted_answer_deleted(source_user_uuid='',
                                                  comment_uuid=comment_uuid,
                                                  case_uuid=str(case.case_uuid),
                                                  session=session,
                                                  iterable=IterableNotifier())

        expected_data_fields = {
            'caseTitle': content.title,
            'caseUuid': str(case.case_uuid),
            'authorUsername': test_user.get('username'),
            'deletionReason': 'unsupported',
        }

        mock_iterable.assert_track_event_called(event=IterableEvent.CASE_ACCEPTED_ANSWER_DELETED,
                                                email=test_user.get('email'),
                                                user_uuid=case_author_uuid,
                                                data_fields=expected_data_fields)
        assert mock_iterable.call_count == 1

    assert session.query(UserNotification) \
        .filter(UserNotification.user_uuid == case_author_uuid,
                UserNotification.case_uuid == case.case_uuid,
                UserNotification.notification_type == UserNotificationType.ACCEPTED_ANSWER_DELETED) \
        .count() == 1


def test_post_accepted_answer_deleted_should_not_notify_users(load_db, approved_post_and_content,
                                                              test_user, monkeypatch):
    session = load_db

    post_author_uuid = test_user.get('userUuid')
    commenter = create_test_user(session=session)
    post, content = approved_post_and_content

    comment_uuid = do_post_comment(user_uid=commenter.user_uid,
                                   content_uuid=content.content_uuid,
                                   comment_text='Accepted Answer',
                                   parent_comment_uuid=None).pop('uuid')
    comment = Comment.get_comment(comment_uuid=comment_uuid, session=session)
    comment.is_accepted_answer = True
    comment.rejection_reason = CommentRejectionReason.UNSUPPORTED
    session.merge(comment)
    session.commit()

    with MockIterable() as mock_iterable:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI.track_event',
                            mock_iterable.track_event)
        notifies_users_of_accepted_answer_deleted(source_user_uuid='',
                                                  comment_uuid=comment_uuid,
                                                  case_uuid=str(post.case_uuid),
                                                  session=session,
                                                  iterable=IterableNotifier())

        mock_iterable.assert_not_called()
        assert mock_iterable.call_count == 0

    assert session.query(UserNotification) \
        .filter(UserNotification.user_uuid == post_author_uuid,
                UserNotification.case_uuid == post.case_uuid,
                UserNotification.notification_type == UserNotificationType.ACCEPTED_ANSWER_DELETED) \
        .count() == 0


def test_accepted_answer_not_chosen_notifies_users(load_db, approved_case_and_content, test_user, monkeypatch):
    session = load_db

    case_author_uuid = test_user.get('userUuid')
    case, content = approved_case_and_content

    with MockIterable() as mock_iterable:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI.track_event',
                            mock_iterable.track_event)
        notifies_users_of_accepted_answer_not_chosen(case_uuid=str(case.case_uuid),
                                                     session=session,
                                                     iterable=IterableNotifier())

        expected_data_fields = {
            "caseUuid": str(case.case_uuid),
            "caseSubmissionDate": datetime.fromisoformat(str(case.created_at)).strftime('%Y-%m-%d %H:%M:%S'),
            "caseTitle": content.title,
            "authorUsername": test_user.get('username'),
            "acceptedAnswerSet": False,
            "numberOfComments": 0,
            "diagnosisUpdateAdded": False,
            "caseCaption": content.caption,
            "caseMediaUrl": None,
        }
        mock_iterable.assert_track_event_called(event=IterableEvent.CASE_ACCEPTED_ANSWER_NOT_CHOSEN,
                                                email=test_user.get('email'),
                                                user_uuid=case_author_uuid,
                                                data_fields=expected_data_fields)
        assert mock_iterable.call_count == 1

    assert session.query(UserNotification) \
        .filter(UserNotification.user_uuid == case_author_uuid,
                UserNotification.case_uuid == case.case_uuid,
                UserNotification.notification_type == UserNotificationType.CASE_NOT_ACCEPTED_ANSWER_CHOSEN) \
        .count() == 1


def test_post_accepted_answer_not_chosen_should_not_notify_users(load_db, approved_post_and_content,
                                                                 test_user, monkeypatch):
    session = load_db

    post_author_uuid = test_user.get('userUuid')
    post, content = approved_post_and_content

    with MockIterable() as mock_iterable:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI.track_event',
                            mock_iterable.track_event)
        notifies_users_of_accepted_answer_not_chosen(case_uuid=str(post.case_uuid),
                                                     session=session,
                                                     iterable=IterableNotifier())
        mock_iterable.assert_not_called()

    assert session.query(UserNotification) \
        .filter(UserNotification.user_uuid == post_author_uuid,
                UserNotification.case_uuid == post.case_uuid,
                UserNotification.notification_type == UserNotificationType.CASE_NOT_ACCEPTED_ANSWER_CHOSEN) \
        .count() == 0


def test_new_accepted_answer_from_anonymous_case_notifies_user(load_db, monkeypatch):
    session = load_db
    case_author = create_test_user(session=session)
    accepted_answer_author = create_test_user(session=session)

    anonymous_case, anonymous_content = create_test_case(author_uuid=case_author.user_uuid,
                                                         is_paging_case=False,
                                                         language=Locale.EN_US.code,
                                                         title="Case Title",
                                                         caption="Case Caption",
                                                         state=CaseState.APPROVED,
                                                         is_anonymous=True,
                                                         session=session)

    comment_uuid = do_post_comment(user_uid=accepted_answer_author.user_uid,
                                   content_uuid=anonymous_content.content_uuid,
                                   comment_text='Accepted Answer',
                                   parent_comment_uuid=None).pop('uuid')
    comment = Comment.get_comment(comment_uuid=comment_uuid, session=session)
    comment.is_accepted_answer = True
    session.merge(comment)
    session.commit()

    author_uuid = accepted_answer_author.user_uuid
    with MockIterable() as mock_iterable:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI.track_event',
                            mock_iterable.track_event)
        notifies_users_of_new_accepted_answer(source_user_uuid=author_uuid,
                                              comment_uuid=comment_uuid,
                                              case_uuid=str(anonymous_case.case_uuid),
                                              session=session,
                                              iterable=IterableNotifier())
        expected_data_fields = {
            'caseTitle': anonymous_content.title,
            'caseUuid': str(anonymous_case.case_uuid),
            'commentUuid': str(comment_uuid),
            'deletionReason': None,
            'caseCaption': 'Case Caption',
            'caseMediaUrl': None,
        }
        mock_iterable.assert_track_event_called(event=IterableEvent.CASE_NEW_ACCEPTED_ANSWER_SELECTED,
                                                email=accepted_answer_author.email,
                                                user_uuid=accepted_answer_author.user_uuid,
                                                data_fields=expected_data_fields)


def test_new_accepted_answer_from_case_notifies_user(load_db, monkeypatch):
    session = load_db
    case_author = create_test_user(session=session)
    accepted_answer_author = create_test_user(session=session)

    case, content = create_test_case(author_uuid=case_author.user_uuid,
                                     is_paging_case=False,
                                     language=Locale.EN_US.code,
                                     title="Case Title",
                                     caption="Case Caption",
                                     state=CaseState.APPROVED,
                                     is_anonymous=False,
                                     session=session)

    comment_uuid = do_post_comment(user_uid=accepted_answer_author.user_uid,
                                   content_uuid=content.content_uuid,
                                   comment_text='Accepted Answer',
                                   parent_comment_uuid=None).pop('uuid')
    comment = Comment.get_comment(comment_uuid=comment_uuid, session=session)
    comment.is_accepted_answer = True
    session.merge(comment)
    session.commit()

    author_uuid = accepted_answer_author.user_uuid
    with MockIterable() as mock_iterable:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI.track_event',
                            mock_iterable.track_event)
        notifies_users_of_new_accepted_answer(source_user_uuid=author_uuid,
                                              comment_uuid=comment_uuid,
                                              case_uuid=str(case.case_uuid),
                                              session=session,
                                              iterable=IterableNotifier())
        expected_data_fields = {
            'caseTitle': content.title,
            'caseUuid': str(case.case_uuid),
            'commentUuid': str(comment_uuid),
            'deletionReason': None,
            'caseCaption': 'Case Caption',
            'caseMediaUrl': None,
            'authorUsername': case_author.username,
        }
        mock_iterable.assert_track_event_called(event=IterableEvent.CASE_NEW_ACCEPTED_ANSWER_SELECTED,
                                                email=accepted_answer_author.email,
                                                user_uuid=accepted_answer_author.user_uuid,
                                                data_fields=expected_data_fields)


def test_new_accepted_answer_from_post_should_not_notify_user(load_db, monkeypatch):
    session = load_db
    post_author = create_test_user(session=session)
    accepted_answer_author = create_test_user(session=session)

    post, post_content = create_test_case(author_uuid=post_author.user_uuid,
                                          is_paging_case=False,
                                          language=Locale.EN_US.code,
                                          title="Case Title",
                                          caption="Case Caption",
                                          state=CaseState.APPROVED,
                                          case_classification=CaseClassification.NONMEDICAL,
                                          session=session)

    comment_uuid = do_post_comment(user_uid=accepted_answer_author.user_uid,
                                   content_uuid=post_content.content_uuid,
                                   comment_text='Accepted Answer',
                                   parent_comment_uuid=None).pop('uuid')
    comment = Comment.get_comment(comment_uuid=comment_uuid, session=session)
    comment.is_accepted_answer = True
    session.merge(comment)
    session.commit()

    author_uuid = accepted_answer_author.user_uuid
    with MockIterable() as mock_iterable:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI.track_event',
                            mock_iterable.track_event)
        notifies_users_of_new_accepted_answer(source_user_uuid=author_uuid,
                                              comment_uuid=comment_uuid,
                                              case_uuid=str(post.case_uuid),
                                              session=session,
                                              iterable=IterableNotifier())

        mock_iterable.assert_not_called()


def test_comment_delete_notifies_author(load_db, initialize_data, monkeypatch):
    session = load_db
    moderator = create_test_user(session=session)
    comment_author = create_test_user(session=session)

    case, content = create_test_case(author_uuid=moderator.user_uuid,
                                     is_paging_case=False,
                                     language=Locale.EN_US.code,
                                     title="Case Title",
                                     caption="Case Caption",
                                     state=CaseState.APPROVED,
                                     session=session)

    comment_uuid = do_post_comment(user_uid=comment_author.user_uid,
                                   content_uuid=content.content_uuid,
                                   comment_text='Comment to delete',
                                   parent_comment_uuid=None).pop('uuid')
    session.commit()

    with MockIterable() as mock_iterable:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI.track_event',
                            mock_iterable.track_event)
        log_comment_delete_and_notify(author_uuid=comment_author.user_uuid,
                                      moderator_uuid=moderator.user_uuid,
                                      comment_uuid=comment_uuid,
                                      session=session,
                                      iterable=IterableNotifier())
        mock_iterable.assert_track_event_called(event=IterableEvent.COMMENT_DELETED,
                                                email=comment_author.email,
                                                user_uuid=comment_author.user_uuid)
    session.commit()
    assert session.query(UserNotification) \
        .filter(UserNotification.user_uuid == comment_author.user_uuid,
                UserNotification.case_uuid == case.case_uuid,
                UserNotification.comment_uuid == comment_uuid,
                UserNotification.notification_type == UserNotificationType.COMMENT_DELETE) \
        .first()


def test_verification_logs_event(load_db, initialize_data, monkeypatch):
    session = load_db
    moderator = create_test_user(session=session)
    user = create_test_user(session=session)

    session.commit()

    with MockIterable() as mock_iterable:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI.track_event',
                            mock_iterable.track_event)
        log_user_status_changed_and_notify_user(user_uuid=user.user_uuid,
                                                moderator_uid=moderator.user_uid,
                                                session=session,
                                                iterable=IterableNotifier())
        mock_iterable.assert_track_event_called(event=IterableEvent.USER_STATUS_CHANGED,
                                                email=user.email,
                                                user_uuid=user.user_uuid)


def test_notify_users_activity_reminder(load_db, initialize_data, approved_case_and_content, monkeypatch):
    case, content = approved_case_and_content
    session = load_db

    user = create_test_user(session=session)
    un = UserNotification.create(user_uuid=user.user_uuid,
                                 source_uuid=user.user_uuid,
                                 case_uuid=case.case_uuid,
                                 session=session,
                                 state=UserNotificationState.NEW,
                                 notification_type=UserNotificationType.APPROVE)

    # Test notifying user who has not received a reminder yet
    with MockIterable() as mock_iterable:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI.track_event',
                            mock_iterable.track_event)
        notify_users_activity_reminder(session=session, iterable=IterableNotifier())
        mock_iterable.assert_track_event_called(event=IterableEvent.ACTIVITY_REMINDER,
                                                email=user.email,
                                                user_uuid=user.user_uuid)
    ar = session.query(ActivityReminder).filter(ActivityReminder.user_uuid == user.user_uuid).one()
    assert ar.last_sent is not None

    # Test user who was recently notified does not get notified again
    with MockIterable() as mock_iterable:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI.track_event',
                            mock_iterable.track_event)
        notify_users_activity_reminder(session=session, iterable=IterableNotifier())
        mock_iterable.assert_not_called()

    # Test user who was notified more than two days ago can be notified again
    ar.last_sent = utc_now(timezone=timezone.utc) - timedelta(days=3)
    with MockIterable() as mock_iterable:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI.track_event',
                            mock_iterable.track_event)
        notify_users_activity_reminder(session=session, iterable=IterableNotifier())
        mock_iterable.assert_track_event_called(event=IterableEvent.ACTIVITY_REMINDER,
                                                email=user.email,
                                                user_uuid=user.user_uuid)

    # Test user with acknowledged notifications only is not notified
    ar.last_sent = utc_now(timezone=timezone.utc) - timedelta(days=3)
    mark_single_user_notification_read(user_uid=user.user_uid,
                                       notification_uuid=un.notification_uuid,
                                       session=session)
    with MockIterable() as mock_iterable:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI.track_event',
                            mock_iterable.track_event)
        notify_users_activity_reminder(session=session, iterable=IterableNotifier())
        mock_iterable.assert_not_called()


def test_notify_profession_change_approved(load_db, initialize_data, monkeypatch):
    session = load_db
    user = create_test_user(session=session)

    with MockIterable() as mock_iterable:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI.track_event',
                            mock_iterable.track_event)

        notify_profession_changed_approved(user_uuid=user.user_uuid,
                                           session=session,
                                           iterable=IterableNotifier())
        mock_iterable.assert_track_event_called(event=IterableEvent.PROFESSION_CHANGE_APPROVED,
                                                email=user.email,
                                                user_uuid=user.user_uuid)
    assert session.query(UserNotification) \
        .filter(UserNotification.user_uuid == user.user_uuid,
                UserNotification.notification_type == UserNotificationType.PROFESSION_CHANGE_APPROVED) \
        .first()


def test_notify_group_invite(load_db, initialize_data, monkeypatch, create_group):
    session = load_db
    g = create_group
    user = create_test_user(session=session)
    inviter = create_test_user(session=session)

    gmf = GroupManagement.invite_user_to_group(email=user.email,
                                               user_uuid=user.user_uuid,
                                               inviter_uuid=inviter.user_uuid,
                                               group_uuid=g.groupUuid,
                                               session=session)

    with MockIterable() as mock_iterable:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI.track_event',
                            mock_iterable.track_event)

        notify_user_of_group_invite(group_filter_uuid=gmf.group_filter_uuid,
                                    session=session,
                                    iterable=IterableNotifier())
        mock_iterable.assert_track_event_called(event=IterableEvent.GROUP_INVITE,
                                                email=user.email,
                                                user_uuid=user.user_uuid)


def test_notify_group_invite_accepted(load_db, initialize_data, monkeypatch, create_group):
    session = load_db
    g = create_group
    user_1 = create_test_user(session=session)
    user_2 = create_test_user(session=session)
    user_3 = create_test_user(session=session)
    inviter = create_test_user(session=session)

    # Invited by group creator
    GroupManagement.invite_user_to_group(email=user_1.email,
                                         user_uuid=user_1.user_uuid,
                                         inviter_uuid=g.groupCreatorUuid,
                                         group_uuid=g.groupUuid,
                                         session=session)
    GroupManagement.add_user_to_group(user_uuid=user_1.user_uuid, group_uuid=g.groupUuid, session=session)

    with MockIterable() as mock_iterable:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI.track_event',
                            mock_iterable.track_event)

        notify_group_invite_accepted(g.groupUuid,
                                     user_1.user_uuid,
                                     session=session,
                                     iterable=IterableNotifier())
        group_creator = session.query(User).get(g.groupCreatorUuid)
        mock_iterable.assert_track_event_called_once(event=IterableEvent.GROUP_INVITE_ACCEPTED,
                                                     email=group_creator.email,
                                                     user_uuid=group_creator.user_uuid)
    assert session.query(UserNotification) \
        .filter(UserNotification.user_uuid == g.groupCreatorUuid,
                UserNotification.notification_type == UserNotificationType.GROUP_INVITE_ACCEPTED,
                UserNotification.group_uuid == g.groupUuid,
                UserNotification.source_uuid == user_1.user_uuid) \
        .one_or_none()
    GroupManagement.remove_user_from_group(user_uuid=user_1.user_uuid, group_uuid=g.groupUuid, session=session)

    # Invited by other user
    GroupManagement.invite_user_to_group(email=user_2.email,
                                         user_uuid=user_2.user_uuid,
                                         inviter_uuid=inviter.user_uuid,
                                         group_uuid=g.groupUuid,
                                         session=session)
    GroupManagement.add_user_to_group(user_uuid=user_2.user_uuid, group_uuid=g.groupUuid, session=session)

    with MockIterable() as mock_iterable:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI.track_event',
                            mock_iterable.track_event)

        notify_group_invite_accepted(g.groupUuid,
                                     user_2.user_uuid,
                                     session=session,
                                     iterable=IterableNotifier())
        # Notifies user who invited the new member
        mock_iterable.assert_track_event_called_once(event=IterableEvent.GROUP_INVITE_ACCEPTED,
                                                     email=inviter.email,
                                                     user_uuid=inviter.user_uuid)
        #  Notifies group creator
        group_creator = session.query(User).get(g.groupCreatorUuid)
        mock_iterable.assert_track_event_called_once(event=IterableEvent.GROUP_INVITE_ACCEPTED,
                                                     email=group_creator.email,
                                                     user_uuid=group_creator.user_uuid)
    assert session.query(UserNotification) \
        .filter(UserNotification.user_uuid == inviter.user_uuid,
                UserNotification.notification_type == UserNotificationType.GROUP_INVITE_ACCEPTED,
                UserNotification.group_uuid == g.groupUuid,
                UserNotification.source_uuid == user_2.user_uuid) \
        .one_or_none()
    assert session.query(UserNotification) \
        .filter(UserNotification.user_uuid == g.groupCreatorUuid,
                UserNotification.notification_type == UserNotificationType.GROUP_INVITE_ACCEPTED,
                UserNotification.group_uuid == g.groupUuid,
                UserNotification.source_uuid == user_2.user_uuid) \
        .one_or_none()
    GroupManagement.remove_user_from_group(user_uuid=user_2.user_uuid, group_uuid=g.groupUuid, session=session)

    # Joined group as a new user
    GroupManagement.add_user_to_group(user_uuid=user_3.user_uuid, group_uuid=g.groupUuid, session=session)

    with MockIterable() as mock_iterable:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI.track_event',
                            mock_iterable.track_event)

        notify_group_invite_accepted(g.groupUuid,
                                     user_3.user_uuid,
                                     session=session,
                                     iterable=IterableNotifier())
        #  Notifies group creator
        group_creator = session.query(User).get(g.groupCreatorUuid)
        mock_iterable.assert_track_event_called_once(event=IterableEvent.GROUP_INVITE_ACCEPTED,
                                                     email=group_creator.email,
                                                     user_uuid=group_creator.user_uuid)
    assert session.query(UserNotification) \
        .filter(UserNotification.user_uuid == g.groupCreatorUuid,
                UserNotification.notification_type == UserNotificationType.GROUP_INVITE_ACCEPTED,
                UserNotification.group_uuid == g.groupUuid,
                UserNotification.source_uuid == user_3.user_uuid) \
        .one_or_none()
    GroupManagement.remove_user_from_group(user_uuid=user_3.user_uuid, group_uuid=g.groupUuid, session=session)


def test_notify_users_of_not_chosen_diagnosis_cases(load_db, initialize_data, monkeypatch, test_user, create_group):
    session = load_db
    g = create_group
    case_author_uuid = test_user.get('userUuid')
    case_author_email = test_user.get('email')

    # Case without diagnosis sends notification
    case_1, content_1 = create_test_case(author_uuid=case_author_uuid,
                                         published_at=datetime.now() - timedelta(days=3.5),
                                         session=session)
    with MockIterable() as mock_iterable:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI.track_event',
                            mock_iterable.track_event)

        expected_data_fields = {
            'caseUuid': str(case_1.case_uuid),
            'caseSubmissionDate': str(case_1.created_at),
            'caseTitle': content_1.title,
            'authorUsername': test_user.get('username'),
            'acceptedAnswerSet': False,
            'numberOfComments': 0,
            'diagnosisUpdateAdded': False,
            'caseMediaUrl': None,
        }
        notify_users_of_not_chosen_diagnosis_cases(session=session,
                                                   iterable=IterableNotifier())

        mock_iterable.assert_track_event_called(event=IterableEvent.DIAGNOSIS_NOT_CHOSEN,
                                                email=case_author_email,
                                                user_uuid=case_author_uuid,
                                                data_fields=expected_data_fields)

        mock_iterable.assert_track_event_called_once(event=IterableEvent.DIAGNOSIS_NOT_CHOSEN,
                                                     email=case_author_email,
                                                     user_uuid=case_author_uuid)
    assert session.query(UserNotification) \
        .filter(UserNotification.notification_type == UserNotificationType.CASE_NOT_DIAGNOSIS_CHOSEN,
                UserNotification.user_uuid == case_author_uuid,
                UserNotification.case_uuid == case_1.case_uuid) \
        .one_or_none()

    # Case posted over 4 days ago does not notify
    case_2, _ = create_test_case(author_uuid=case_author_uuid,
                                 published_at=datetime.now() - timedelta(days=4.5),
                                 session=session)
    with MockIterable() as mock_iterable:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI.track_event',
                            mock_iterable.track_event)
        notify_users_of_not_chosen_diagnosis_cases(session=session,
                                                   iterable=IterableNotifier())
        mock_iterable.assert_not_called()
    assert not session.query(UserNotification) \
        .filter(UserNotification.notification_type == UserNotificationType.CASE_NOT_DIAGNOSIS_CHOSEN,
                UserNotification.user_uuid == case_author_uuid,
                UserNotification.case_uuid == case_2.case_uuid) \
        .one_or_none()

    # Case posted under 3 days ago does not notify
    case_3, _ = create_test_case(author_uuid=case_author_uuid,
                                 published_at=datetime.now() - timedelta(days=2.5),
                                 session=session)
    with MockIterable() as mock_iterable:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI.track_event',
                            mock_iterable.track_event)
        notify_users_of_not_chosen_diagnosis_cases(session=session,
                                                   iterable=IterableNotifier())
        mock_iterable.assert_not_called()
    assert not session.query(UserNotification) \
        .filter(UserNotification.notification_type == UserNotificationType.CASE_NOT_DIAGNOSIS_CHOSEN,
                UserNotification.user_uuid == case_author_uuid,
                UserNotification.case_uuid == case_3.case_uuid) \
        .one_or_none()

    # Resolved case does not notify
    case_4, _ = create_test_case(author_uuid=case_author_uuid,
                                 published_at=datetime.now() - timedelta(days=3.5),
                                 session=session)
    resolved_label = Label.get_resolved(session=session)
    CaseLabel.create(case_uuid=case_4.case_uuid, label_uuid=resolved_label.label_uuid, session=session)
    with MockIterable() as mock_iterable:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI.track_event',
                            mock_iterable.track_event)
        notify_users_of_not_chosen_diagnosis_cases(session=session,
                                                   iterable=IterableNotifier())
        mock_iterable.assert_not_called()
    assert not session.query(UserNotification) \
        .filter(UserNotification.notification_type == UserNotificationType.CASE_NOT_DIAGNOSIS_CHOSEN,
                UserNotification.user_uuid == case_author_uuid,
                UserNotification.case_uuid == case_4.case_uuid) \
        .one_or_none()

    # Case with diagnosis does not notify
    case_5, content_5 = create_test_case(author_uuid=case_author_uuid,
                                         published_at=datetime.now() - timedelta(days=3.5),
                                         session=session)
    ContentUpdate.create(session=session,
                         content_uuid=content_5.content_uuid,
                         text="Case diagnosis",
                         update_type=ContentUpdateType.DIAGNOSIS)
    with MockIterable() as mock_iterable:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI.track_event',
                            mock_iterable.track_event)
        notify_users_of_not_chosen_diagnosis_cases(session=session,
                                                   iterable=IterableNotifier())
        mock_iterable.assert_not_called()
    assert not session.query(UserNotification) \
        .filter(UserNotification.notification_type == UserNotificationType.CASE_NOT_DIAGNOSIS_CHOSEN,
                UserNotification.user_uuid == case_author_uuid,
                UserNotification.case_uuid == case_5.case_uuid) \
        .one_or_none()

    # Group case does not notify
    case_6, _ = create_test_case(author_uuid=case_author_uuid,
                                 published_at=datetime.now() - timedelta(days=3.5),
                                 group_uuid=g.groupUuid,
                                 session=session)
    with MockIterable() as mock_iterable:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI.track_event',
                            mock_iterable.track_event)
        notify_users_of_not_chosen_diagnosis_cases(session=session,
                                                   iterable=IterableNotifier())
        mock_iterable.assert_not_called()
    assert not session.query(UserNotification) \
        .filter(UserNotification.notification_type == UserNotificationType.CASE_NOT_DIAGNOSIS_CHOSEN,
                UserNotification.user_uuid == case_author_uuid,
                UserNotification.case_uuid == case_5.case_uuid) \
        .one_or_none()


def test_should_not_notify_users_of_not_chosen_diagnosis_posts(load_db, initialize_data,
                                                               monkeypatch, test_user, create_group):
    session = load_db
    g = create_group
    post_author_uuid = test_user.get('userUuid')

    post_1, content_1 = create_test_case(author_uuid=post_author_uuid,
                                         published_at=datetime.now() - timedelta(days=3.5),
                                         case_classification=CaseClassification.NONMEDICAL,
                                         session=session)
    with MockIterable() as mock_iterable:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI.track_event',
                            mock_iterable.track_event)

        notify_users_of_not_chosen_diagnosis_cases(session=session,
                                                   iterable=IterableNotifier())
        mock_iterable.assert_not_called()

    assert not session.query(UserNotification) \
        .filter(UserNotification.notification_type == UserNotificationType.CASE_NOT_DIAGNOSIS_CHOSEN,
                UserNotification.user_uuid == post_author_uuid,
                UserNotification.case_uuid == post_1.case_uuid) \
        .one_or_none()

    # Post posted over 4 days ago does not notify
    post_2, _ = create_test_case(author_uuid=post_author_uuid,
                                 published_at=datetime.now() - timedelta(days=4.5),
                                 case_classification=CaseClassification.NONMEDICAL,
                                 session=session)
    with MockIterable() as mock_iterable:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI.track_event',
                            mock_iterable.track_event)
        notify_users_of_not_chosen_diagnosis_cases(session=session,
                                                   iterable=IterableNotifier())
        mock_iterable.assert_not_called()
    assert not session.query(UserNotification) \
        .filter(UserNotification.notification_type == UserNotificationType.CASE_NOT_DIAGNOSIS_CHOSEN,
                UserNotification.user_uuid == post_author_uuid,
                UserNotification.case_uuid == post_2.case_uuid) \
        .one_or_none()

    # Post posted under 3 days ago does not notify
    post_3, _ = create_test_case(author_uuid=post_author_uuid,
                                 published_at=datetime.now() - timedelta(days=2.5),
                                 case_classification=CaseClassification.NONMEDICAL,
                                 session=session)
    with MockIterable() as mock_iterable:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI.track_event',
                            mock_iterable.track_event)
        notify_users_of_not_chosen_diagnosis_cases(session=session,
                                                   iterable=IterableNotifier())
        mock_iterable.assert_not_called()
    assert not session.query(UserNotification) \
        .filter(UserNotification.notification_type == UserNotificationType.CASE_NOT_DIAGNOSIS_CHOSEN,
                UserNotification.user_uuid == post_author_uuid,
                UserNotification.case_uuid == post_3.case_uuid) \
        .one_or_none()

    # Resolved Post does not notify
    post_4, _ = create_test_case(author_uuid=post_author_uuid,
                                 published_at=datetime.now() - timedelta(days=3.5),
                                 case_classification=CaseClassification.NONMEDICAL,
                                 session=session)
    resolved_label = Label.get_resolved(session=session)
    CaseLabel.create(case_uuid=post_4.case_uuid, label_uuid=resolved_label.label_uuid, session=session)
    with MockIterable() as mock_iterable:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI.track_event',
                            mock_iterable.track_event)
        notify_users_of_not_chosen_diagnosis_cases(session=session,
                                                   iterable=IterableNotifier())
        mock_iterable.assert_not_called()
    assert not session.query(UserNotification) \
        .filter(UserNotification.notification_type == UserNotificationType.CASE_NOT_DIAGNOSIS_CHOSEN,
                UserNotification.user_uuid == post_author_uuid,
                UserNotification.case_uuid == post_4.case_uuid) \
        .one_or_none()

    # Post with diagnosis does not notify
    post_5, content_5 = create_test_case(author_uuid=post_author_uuid,
                                         published_at=datetime.now() - timedelta(days=3.5),
                                         case_classification=CaseClassification.NONMEDICAL,
                                         session=session)
    ContentUpdate.create(session=session,
                         content_uuid=content_5.content_uuid,
                         text="Case diagnosis",
                         update_type=ContentUpdateType.DIAGNOSIS)
    with MockIterable() as mock_iterable:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI.track_event',
                            mock_iterable.track_event)
        notify_users_of_not_chosen_diagnosis_cases(session=session,
                                                   iterable=IterableNotifier())
        mock_iterable.assert_not_called()
    assert not session.query(UserNotification) \
        .filter(UserNotification.notification_type == UserNotificationType.CASE_NOT_DIAGNOSIS_CHOSEN,
                UserNotification.user_uuid == post_author_uuid,
                UserNotification.case_uuid == post_5.case_uuid) \
        .one_or_none()

    # Group post does not notify
    post_6, _ = create_test_case(author_uuid=post_author_uuid,
                                 published_at=datetime.now() - timedelta(days=3.5),
                                 group_uuid=g.groupUuid,
                                 case_classification=CaseClassification.NONMEDICAL,
                                 session=session)
    with MockIterable() as mock_iterable:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI.track_event',
                            mock_iterable.track_event)
        notify_users_of_not_chosen_diagnosis_cases(session=session,
                                                   iterable=IterableNotifier())
        mock_iterable.assert_not_called()
    assert not session.query(UserNotification) \
        .filter(UserNotification.notification_type == UserNotificationType.CASE_NOT_DIAGNOSIS_CHOSEN,
                UserNotification.user_uuid == post_author_uuid,
                UserNotification.case_uuid == post_5.case_uuid) \
        .one_or_none()
