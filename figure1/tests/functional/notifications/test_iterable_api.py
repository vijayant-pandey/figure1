from json import JSONDecodeError

import pytest

from figure1.common.iterable import IterableAPI
from figure1.exceptions import IterableAPIException
from figure1.exceptions import IterableMisconfiguredException
from figure1.exceptions import IterableOverloadedException

from figure1.notifications import IterableEventWrapper
from figure1.notifications import IterableEvent
from figure1.tests.utils.mock_base import MockBase


class MockResponse:
    def __init__(self, return_json={"success": "success"}, status_code=200):
        self.headers = {"content-length": 3}
        self._json = return_json
        self._status_code = status_code

    def json(self):
        return self._json

    @property
    def status_code(self):
        return self._status_code


class MockApi(MockBase):
    def _api_call(self, **kwargs):
        self.calls.append(kwargs)
        self.call_count += 1

    def assert_called_with(self, **kwargs):
        assert kwargs in self.calls


class MockRequests(MockBase):
    def request_success(self, **kwargs):
        return MockResponse()

    def request_response_json_raises_json_decoder_error(self, **kwargs):
        raise JSONDecodeError(msg='msg', doc='doc', pos=0)

    def request_response_json_raises_value_error(self, **kwargs):
        raise ValueError

    def request_response_400(self, **kwargs):
        return MockResponse(status_code=400)

    def request_response_401(self, **kwargs):
        return MockResponse(status_code=401)

    def request_response_greater_than_500(self, **kwargs):
        return MockResponse(status_code=501)

    def request_response_rate_limited_exceeded(self, **kwargs):
        return MockResponse(return_json={"code": "RateLimitExceeded"})


def test_iterable_api_track_event(monkeypatch):
    iterable_api = IterableAPI()

    with MockApi() as mock_api:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI._api_call',
                            mock_api._api_call)
        iterable_api.track_event(event_name="event_name",
                                 event_id="event_id",
                                 email="email",
                                 created_at="created_at",
                                 data_fields={"data_fields": 0},
                                 user_id="user_id",
                                 campaign_id="campaign_id",
                                 template_id="template_id",
                                 event_wrapper=None)
        mock_api.assert_called_with(call="/api/events/track",
                                    json_data={
                                        "eventName": "event_name",
                                        "id": "event_id",
                                        "email": "email",
                                        "createdAt": "created_at",
                                        "dataFields": {"data_fields": 0},
                                        "userId": "user_id",
                                        "campaignId": "campaign_id",
                                        "templateId": "template_id",
                                    })

    with MockApi() as mock_api:
        monkeypatch.setattr('figure1.common.iterable.api.IterableAPI._api_call',
                            mock_api._api_call)

        event_wrapper = IterableEventWrapper(
            event=IterableEvent.CASE_STATE_CHANGED,
            email="email@email.com",
            data_fields={"data_fields": 0},
            user_uuid="user_uuid"
        )

        iterable_api.track_event(event_wrapper=event_wrapper)
        mock_api.assert_called_with(call="/api/events/track",
                                    json_data={
                                        "eventName": "caseStateChanged",
                                        "email": "email@email.com",
                                        "dataFields": {"data_fields": 0},
                                        "userId": "user_uuid",
                                    })


def test_iterable_api_api_call(monkeypatch):
    iterable_api = IterableAPI()
    iterable_api.iterable_api_disabled = False
    iterable_api.test_mode = False

    with MockRequests() as mock_requests:
        monkeypatch.setattr('requests.request',
                            mock_requests.request_success)

        data = iterable_api._api_call(
            call="call",
            params={},
            json_data={},
        )

        assert data == {"success": "success"}

    with pytest.raises(JSONDecodeError):
        monkeypatch.setattr('requests.request',
                            mock_requests.request_response_json_raises_json_decoder_error)

        data = iterable_api._api_call(
            call="call",
            params={},
            json_data={},
        )

    with pytest.raises(ValueError):
        monkeypatch.setattr('requests.request',
                            mock_requests.request_response_json_raises_value_error)

        data = iterable_api._api_call(
            call="call",
            params={},
            json_data={},
        )

    with pytest.raises(IterableAPIException):
        monkeypatch.setattr('requests.request',
                            mock_requests.request_response_400)

        data = iterable_api._api_call(
            call="call",
            params={},
            json_data={},
        )

    with pytest.raises(IterableMisconfiguredException):
        monkeypatch.setattr('requests.request',
                            mock_requests.request_response_401)

        data = iterable_api._api_call(
            call="call",
            params={},
            json_data={},
        )

    with pytest.raises(IterableOverloadedException):
        monkeypatch.setattr('requests.request',
                            mock_requests.request_response_greater_than_500)

        data = iterable_api._api_call(
            call="call",
            params={},
            json_data={},
        )

    with pytest.raises(IterableOverloadedException):
        monkeypatch.setattr('requests.request',
                            mock_requests.request_response_rate_limited_exceeded)

        data = iterable_api._api_call(
            call="call",
            params={},
            json_data={},
        )
