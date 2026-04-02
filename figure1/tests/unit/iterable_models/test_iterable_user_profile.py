import pytest
from pydantic import ValidationError
from figure1.common.models.db import User
from figure1.common.iterable import generate_iterable_user_object
from figure1.notifications import IterableNotifier
from figure1.common.types import ScreenTrackingData
from figure1.notifications.iterable import ItblUserProfile
from figure1.common.iterable import IterableUpdateEmail


def test_invalid_email_iter_user(load_db, test_user_invalid_email):
    session = load_db
    invalid_email = test_user_invalid_email
    with pytest.raises(ValidationError):
        generate_iterable_user_object(user_uuid=invalid_email.user_uuid, session=session)


def test_iterable_user_object(load_db):
    session = load_db
    u = User.q.first()
    i = generate_iterable_user_object(user_uuid=u.user_uuid, session=session)
    assert isinstance(i, ItblUserProfile)


def test_iter_user_registration_event(load_db):
    u = User.q.first()
    resp = IterableNotifier().send_registration_tracking_event(user=u, screen_name='registrationStarted')
    assert resp.get('data').get('dataFields').get('email') == u.email


def test_iter_user_case_event(load_db):
    u = User.q.first()
    sct = ScreenTrackingData(screen_id='caseCreated', case_data={'caption': 'test1', 'title': 'test2'})
    resp = IterableNotifier().send_case_draft_event(user=u, screen_name='caseCreated', case_data=sct.caseDraftData)
    assert resp.get('data').get('dataFields').get('caseCaption') == 'test1'


def test_iter_update_email():
    known_good_emails = ['auko2jz47.com@chello.at']
    known_bad_emails = ['asdf_dd@gmailcom']

    for e in known_good_emails:
        assert IterableUpdateEmail(currentEmail=e, newEmail=e)

    for be in known_bad_emails:
        with pytest.raises(ValidationError):
            IterableUpdateEmail(currentEmail=be, newEmail=be)
