from figure1.notifications import IterableNotifier
from figure1.notifications import IterableEvent
from figure1.tests.functional.notifications.test_notifier import IterableEventWrapperAssertion


class MockIterable:
    def __init__(self):
        self.called = False
        self.calls = []
        self.call_count = 0

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

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


def test_send_iterable_marketing_sign_up_event(load_db, test_user, monkeypatch):
    session = load_db
    user = test_user
    notifier = IterableNotifier()

    with MockIterable() as mock_iterable:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI.track_event',
                            mock_iterable.track_event)
        notifier.send_marketing_sign_up_event(user_uuid=user.get('userUuid'), session=session)
        mock_iterable.assert_track_event_called(event=IterableEvent.USER_MARKETING_SIGN_UP,
                                                email=user.get('email'),
                                                user_uuid=user.get('userUuid'),
                                                data_fields={
                                                    'userUuid': user.get('userUuid'),
                                                    'email': user.get('email'),
                                                })
