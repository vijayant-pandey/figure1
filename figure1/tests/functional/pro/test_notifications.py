import time
from typing import Callable
from contextlib import contextmanager

import pytest

from figure1.common.iterable.domain import sync_user_device_notification_to_iterable
from figure1.common.models.db import UserNotification
from figure1.common.models.db import User
from figure1.common.types.notification import UserNotificationState
from figure1.common.types.notification import UserNotificationType
from figure1.exceptions import IterableUnsupportedDeviceType


def _get_fs_doc(documents, collections, fs, doc_filter: Callable[[dict], bool] = None):
    count = 0
    for d, c in zip(documents, collections):
        fs = fs.collection(c).document(d)
    doc = fs.get()
    while not doc.exists or (doc_filter and not doc_filter(doc.to_dict())):
        doc = fs.get()
        count += 1
        if count >= 15:
            raise TimeoutError
        time.sleep(1)
    return doc.to_dict()


@contextmanager
def assert_not_raises(exception):
    try:
        yield
    except exception:
        raise pytest.fail(f"The exception should not raise: {exception}".exception)


class MockIterableAPI:
    def __init__(self):
        self.iterable_api_disabled = False

    def get_iterable_user_by_email(self, email, wait_for_user=False):
        return {
            'user': {
                'dataFields':
                    {
                        'devices': [
                            {'token': '',
                             'deviceLanguage': 'pt'}
                        ]
                    }
            }
        }

    def register_device_token(self, email, device_type,
                              device_token, device_language, notification_enabled):
        pass


def test_sync_user_notification(client, headers, load_db, test_notification, get_firestore_client):
    session = load_db
    fs = get_firestore_client
    user = User.get_user_by_uuid(user_uuid=test_notification.user_uuid, session=session)
    user_uid = user.user_uid
    user_uuid = str(user.user_uuid)

    response = client.get(f"/pro/v1/activity/{user_uid}", headers=headers)
    assert response.status_code == 200

    doc = _get_fs_doc(documents=[user_uid, str(test_notification.notification_uuid)],
                      collections=['userNotificationDB', 'notifications'],
                      fs=fs)
    assert doc['notificationUuid'] == str(test_notification.notification_uuid)
    assert doc['state'] == 'new'
    assert doc['notificationType'] == 'approve'
    assert doc['type'] == 'approve'
    assert doc['targetUser']['userUuid'] == user_uuid
    assert doc['sourceUser']['userUuid'] == user_uuid
    assert doc['case']['caseUuid'] == str(test_notification.case_uuid)
    assert doc['caseUuid'] == str(test_notification.case_uuid)
    assert doc['sourceUuid'] == user_uuid
    assert doc['userUuid'] == user_uuid
    assert doc['longMessage'] == 'Your case was approved'
    assert doc['markdownMessage'] == 'Your case was approved'

    metadata = _get_fs_doc(documents=[user_uid],
                           collections=['userNotificationDB'],
                           fs=fs)
    assert metadata['allCount'] == 1
    assert metadata['newCount'] == 1


def test_mark_user_notifications_acknowledged(client, headers, load_db, test_notification, get_firestore_client):
    session = load_db
    fs = get_firestore_client
    user = User.get_user_by_uuid(user_uuid=test_notification.user_uuid, session=session)
    user_uid = user.user_uid
    user_uuid = str(user.user_uuid)

    response = client.post(f"/pro/v1/activity/{user_uid}/acknowledged/{test_notification.notification_uuid}",
                           headers=headers)
    assert response.status_code == 200

    doc = _get_fs_doc(documents=[user_uid, str(test_notification.notification_uuid)],
                      collections=['userNotificationDB', 'notifications'],
                      fs=fs,
                      doc_filter=lambda x: x['state'] == 'acknowledged')
    assert doc['notificationUuid'] == str(test_notification.notification_uuid)
    assert doc['state'] == 'acknowledged'
    assert doc['notificationType'] == 'approve'
    assert doc['type'] == 'approve'
    assert doc['targetUser']['userUuid'] == user_uuid
    assert doc['sourceUser']['userUuid'] == user_uuid
    assert doc['case']['caseUuid'] == str(test_notification.case_uuid)
    assert doc['caseUuid'] == str(test_notification.case_uuid)
    assert doc['sourceUuid'] == user_uuid
    assert doc['userUuid'] == user_uuid
    assert doc['longMessage'] == 'Your case was approved'
    assert doc['markdownMessage'] == 'Your case was approved'

    metadata = _get_fs_doc(documents=[user_uid],
                           collections=['userNotificationDB'],
                           fs=fs)
    assert metadata['allCount'] == 1
    assert metadata['newCount'] == 0


def test_mark_a_single_user_notifications_read(client, headers, load_db, test_notification, get_firestore_client):
    session = load_db
    fs = get_firestore_client
    user = User.get_user_by_uuid(user_uuid=test_notification.user_uuid, session=session)
    user_uid = user.user_uid
    user_uuid = str(user.user_uuid)

    response = client.post(f"/pro/v1/activity/{user_uid}/read/{test_notification.notification_uuid}", headers=headers)
    assert response.status_code == 200

    doc = _get_fs_doc(documents=[user_uid, str(test_notification.notification_uuid)],
                      collections=['userNotificationDB', 'notifications'],
                      fs=fs,
                      doc_filter=lambda x: x['state'] == 'read')
    assert doc['notificationUuid'] == str(test_notification.notification_uuid)
    assert doc['state'] == 'read'
    assert doc['notificationType'] == 'approve'
    assert doc['type'] == 'approve'
    assert doc['targetUser']['userUuid'] == user_uuid
    assert doc['sourceUser']['userUuid'] == user_uuid
    assert doc['case']['caseUuid'] == str(test_notification.case_uuid)
    assert doc['caseUuid'] == str(test_notification.case_uuid)
    assert doc['sourceUuid'] == user_uuid
    assert doc['userUuid'] == user_uuid
    assert doc['longMessage'] == 'Your case was approved'
    assert doc['markdownMessage'] == 'Your case was approved'

    metadata = _get_fs_doc(documents=[user_uid],
                           collections=['userNotificationDB'],
                           fs=fs)
    assert metadata['allCount'] == 1
    assert metadata['newCount'] == 0


def test_mark_all_user_notifications_read(client, headers, load_db,
                                          approved_case_and_content, test_user, get_firestore_client):
    session = load_db
    fs = get_firestore_client
    user_uid = test_user.get('userUid')
    user_uuid = test_user.get('userUuid')
    case, _ = approved_case_and_content
    case_uuid = str(case.case_uuid)

    n1 = UserNotification.create(user_uuid=user_uuid,
                                 source_uuid=user_uuid,
                                 case_uuid=case_uuid,
                                 session=session,
                                 state=UserNotificationState.NEW,
                                 notification_type=UserNotificationType.APPROVE)
    n2 = UserNotification.create(user_uuid=user_uuid,
                                 source_uuid=user_uuid,
                                 case_uuid=case_uuid,
                                 session=session,
                                 state=UserNotificationState.NEW,
                                 notification_type=UserNotificationType.APPROVE)
    session.commit()

    response = client.post(f"/pro/v1/activity/{user_uid}/read", headers=headers)
    assert response.status_code == 200

    doc1 = _get_fs_doc(documents=[user_uid, str(n1.notification_uuid)],
                       collections=['userNotificationDB', 'notifications'],
                       fs=fs,
                       doc_filter=lambda x: x['state'] == 'read')
    doc2 = _get_fs_doc(documents=[user_uid, str(n2.notification_uuid)],
                       collections=['userNotificationDB', 'notifications'],
                       fs=fs,
                       doc_filter=lambda x: x['state'] == 'read')
    assert doc1['notificationUuid'] == str(n1.notification_uuid)
    assert doc1['state'] == 'read'
    assert doc1['notificationType'] == 'approve'
    assert doc1['type'] == 'approve'
    assert doc1['targetUser']['userUuid'] == user_uuid
    assert doc1['sourceUser']['userUuid'] == user_uuid
    assert doc1['case']['caseUuid'] == case_uuid
    assert doc1['caseUuid'] == case_uuid
    assert doc1['sourceUuid'] == user_uuid
    assert doc1['userUuid'] == user_uuid
    assert doc1['longMessage'] == 'Your case was approved'
    assert doc1['markdownMessage'] == 'Your case was approved'

    assert doc2['notificationUuid'] == str(n2.notification_uuid)
    assert doc2['state'] == 'read'
    assert doc2['notificationType'] == 'approve'
    assert doc2['type'] == 'approve'
    assert doc2['targetUser']['userUuid'] == user_uuid
    assert doc2['sourceUser']['userUuid'] == user_uuid
    assert doc2['case']['caseUuid'] == case_uuid
    assert doc2['caseUuid'] == case_uuid
    assert doc2['sourceUuid'] == user_uuid
    assert doc2['userUuid'] == user_uuid
    assert doc2['longMessage'] == 'Your case was approved'
    assert doc2['markdownMessage'] == 'Your case was approved'

    metadata = _get_fs_doc(documents=[user_uid],
                           collections=['userNotificationDB'],
                           fs=fs)
    assert metadata['allCount'] == 2
    assert metadata['newCount'] == 0


def test_sync_user_device_notification_to_iterable(monkeypatch):
    notification_enabled = True
    monkeypatch.setattr('figure1.common.iterable.domain.IterableAPI', MockIterableAPI)

    # invalid device type
    with pytest.raises(IterableUnsupportedDeviceType):
        device = {
            "device_id": "dev1",
            "device_type": "not supported",
            "fcm_token": "token1"
        }
        sync_user_device_notification_to_iterable("email@email.com", device, notification_enabled)

    # valid device type
    with assert_not_raises(IterableUnsupportedDeviceType):
        device = {
            "device_id": "dev1",
            "device_type": "ios",
            "fcm_token": "token1"
        }
        sync_user_device_notification_to_iterable("email@email.com", device, notification_enabled)

        device = {
            "device_id": "dev1",
            "device_type": "android",
            "fcm_token": "token1"
        }
        sync_user_device_notification_to_iterable("email@email.com", device, notification_enabled)

        device = {
            "device_id": "dev1",
            "device_type": "web",
            "fcm_token": "token1"
        }
        sync_user_device_notification_to_iterable("email@email.com", device, notification_enabled)


def test_update_user_device_notification_endpoint(client, headers, load_db, test_notification, monkeypatch):
    monkeypatch.setattr('figure1.common.iterable.domain.IterableAPI', MockIterableAPI)
    session = load_db
    user = User.get_user_by_uuid(user_uuid=test_notification.user_uuid, session=session)
    user_uuid = str(user.user_uuid)

    # missing device
    response = client.post(f"/pro/v1/notification/device/{user_uuid}",
                           headers=headers,
                           json={"notification_enabled": True})
    assert response.status_code == 422

    # missing notification_enabled
    response = client.post(f"/pro/v1/notification/device/{user_uuid}",
                           headers=headers,
                           json={"device": {"device_id": "dev1",
                                            "device_type": "android",
                                            "fcm_token": "token1"
                                            }})
    assert response.status_code == 422

    # invalid devices
    response = client.post(f"/pro/v1/notification/device/{user_uuid}",
                           headers=headers,
                           json={"device": {"device_id": "dev1"},
                                 "notification_enabled": True})
    assert response.status_code == 422

    response = client.post(f"/pro/v1/notification/device/{user_uuid}",
                           headers=headers,
                           json={"device": {"device_id": "dev1",
                                            "device_type": "invalid_type",
                                            "fcm_token": "token1"},
                                 "notification_enabled": True})
    assert response.status_code == 422

    # valid request
    response = client.post(f"/pro/v1/notification/device/{user_uuid}",
                           headers=headers,
                           json={"device": {"device_id": "dev1",
                                            "device_type": "android",
                                            "fcm_token": "token1"
                                            },
                                 "notification_enabled": True})
    assert response.status_code == 200
