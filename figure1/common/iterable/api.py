import logging
import time
from json import JSONDecodeError
from typing import Any
from typing import Dict
from typing import List

import requests
from pydantic import ValidationError, parse_obj_as
from sqlalchemy.orm import Session

from figure1.common.models.db import StandaloneEmail
from .api_payloads import IterableUpdateEmail
from figure1.common.types import StandaloneEmailKind
from figure1.common.types import SupportedDeviceTypes
from figure1.configuration import app_settings
from figure1.exceptions import IterableAPIException
from figure1.exceptions import IterableMisconfiguredException
from figure1.exceptions import IterableOverloadedException
from figure1.exceptions import IterableUpdateException
from figure1.exceptions import IterableUserNotFound

from .iterable_types import UpdateUserSubscriptionsModel, IterableChannelModel, IterablePostResponseModel

logger = logging.getLogger('figure1.iterable_api')


class IterableAPI:
    """
    Based on this wrapper as a starting point, with some modifications:
    https://raw.githubusercontent.com/carter-j-h/iterable-python-wrapper/master/iterablepythonwrapper/client.py
    """

    def __init__(self):
        """
        This preforms the necessary initialization parameters for the
        Iterable API wrapper. It stores the base URI, the API key for the
        project, and headers that shoudl be consistent across all requests.

        """
        self.iterable_api_disabled = False
        if not app_settings.iterable_api_key and not app_settings.test_mode:
            logger.error("No iterable API key found, disabling API calls")
            self.iterable_api_disabled = True
        self.test_mode = app_settings.test_mode
        self.api_key = app_settings.iterable_api_key
        self.ios_env_name = app_settings.iterable_ios_env_name
        self.android_env_name = app_settings.iterable_android_env_name
        self.web_env_name = app_settings.iterable_web_env_name
        self.base_uri = app_settings.iterable_base_url
        self.request_timeout = 20
        self.headers = {
            "Content-type": "application/json",
            "X-Api-Key": app_settings.iterable_api_key
        }

    def _determine_application(self, device_type):
        if device_type == SupportedDeviceTypes.ANDROID.name.lower():
            return self.android_env_name

        elif device_type == SupportedDeviceTypes.IOS.name.lower():
            return self.ios_env_name

        elif device_type == SupportedDeviceTypes.WEB.name.lower():
            return self.web_env_name

        else:
            raise IterableUpdateException(f"No configured application for the device_type={device_type}")

    def _api_call(self,
                  call,
                  params={},
                  json_data={},
                  method="POST"):
        """
        Callers should backoff and retry for IterableOverloadedException, not for any others.

        :raises ValueError, IterableAPIException, IterableMisconfiguredException, ValidationError:
        :param call: uri for the endpoint being called
        :param params: url parameters, if any
        :param json_data: Payload in a dictionary
        :return:
        """
        if self.test_mode:
            return {"call": call,
                    "data": json_data,
                    "method": method}

        if self.iterable_api_disabled:
            logger.error("Iterable API is disabled, nothing to do")
            return None

        r = requests.request(
            method=method,
            url=self.base_uri + call,
            params=params,
            headers=self.headers,
            json=json_data,
            timeout=self.request_timeout)

        if r.headers.get('content-length') == 2:
            logger.error("Nothing found, iterable returns 200 and an empty body")
            return {}

        try:
            data = r.json()
        except JSONDecodeError as je:
            logger.error("Caught status %s", r.status_code)
            logger.error("Failed to decode json: %s", je)
            raise
        except ValueError as ve:
            logger.error("Caught status %s", r.status_code)
            logger.error("Failed to decode response %s", ve)
            raise

        if r.status_code == 400:
            logger.error("Caught status %s", r.status_code)
            raise IterableAPIException(msg=data.get('msg'),
                                       status=data.get('code'),
                                       return_code=r.status_code)

        if r.status_code == 401:
            logger.error("Caught status %s", r.status_code)
            raise IterableMisconfiguredException(msg=data.get('msg'),
                                                 status=data.get('code'),
                                                 return_code=r.status_code)

        if r.status_code > 500 or data.get('code') == 'RateLimitExceeded':
            logger.error("Caught status %s", r.status_code)
            raise IterableOverloadedException

        return data

    def get_iterable_user_by_email(self, email, wait_for_user=False):
        """
        Get the user object from iterable
        :param email:
        :param wait_for_user: if True, wait for up to 60 seconds for the user to appear in iterable.
        If an integer greater than 0, wait for that many seconds.
        :return:
        """
        call = f"/iterable/profile/email/{email}"
        user = self._api_call(call=call, method="GET")
        if user:
            return user

        if wait_for_user is True:
            return self._wait_for_iterable_user(email)

        elif wait_for_user is not False:
            try:
                wait_timeout = int(wait_for_user)
            except TypeError:
                logger.error("Invalid wait time, using default")
                return self._wait_for_iterable_user(email)
            else:
                return self._wait_for_iterable_user(email=email, timeout=wait_timeout)

        if not user:
            raise IterableUserNotFound

    def unsubscribe_user_from_all_channels(self, email) -> IterablePostResponseModel:
        """
        Given an email address, attempt to unsubscribe a user from all channels.
        This should be done when a user is deleted.
        :param email:
        :return:
        """
        update_model = UpdateUserSubscriptionsModel(email=email)
        for channel in self.list_channels():
            update_model.unsubscribedChannelIds.append(channel.id)
        resp = self._api_call(call=update_model.api_call,
                              method=update_model.api_method,
                              json_data=update_model.dict())
        resp_model = IterablePostResponseModel.parse_obj(resp)
        if resp_model.isError:
            raise IterableUpdateException(msg=resp_model.msg, status=resp_model.code, return_code=500)
        else:
            return resp_model

    def forget_device_token(self,
                            email,
                            device_token,
                            user_id
                            ):

        call = "/iterable/device/disable"

        payload = {
            "email": email,
            "token": device_token,
            "userId": user_id
        }

        return self._api_call(call=call, json_data=payload)

    def register_device_token(self,
                              email,
                              device_token,
                              device_type,
                              platform="GCM",
                              device_language=None,
                              notification_enabled=None
                              ):
        call = "/iterable/device/register"
        try:
            selected_application = self._determine_application(device_type=device_type)
            payload = {
                "email": email,
                "device": {
                    "token": device_token,
                    "applicationName": selected_application,
                    "platform": platform,
                    "dataFields": {"deviceLanguage": device_language,
                                   "notificationEnabled": notification_enabled}
                }
            }
            return self._api_call(call=call, json_data=payload)
        except IterableUpdateException as e:
            logger.error(f"Data we received while trying to register a device token with iterable "
                         f"device_token={device_token}"
                         f"device_type={device_type}"
                         f"platform={platform}"
                         f"{e}")
            raise

    def update_user(self,
                    email=None,
                    data_fields=None,
                    user_id=None,
                    prefer_user_id=None,
                    merge_nested_objects=None):

        """
        The Iterable 'User Update' api updates a user profile with new data
        fields. Missing fields are not deleted and new data is merged.

        The body of the request takes 4 keys:
            1. email-- in the form of a string -- used as the unique identifier by
                the Iterable database.
            2. data fields-- in the form of an object-- these are the additional attributes
             of the user that we want to add or update
            3. userId- in the form of a string-- another field we can use as a lookup
                of the user.
            4. mergeNestedObjects-- in the form of an object-- used to merge top level
                objects instead of overwriting.
        """

        call = f"/iterable/profile/update/{email}"

        payload = {}

        if email is not None:
            payload["email"] = str(email)

        if data_fields is not None:
            payload["dataFields"] = data_fields

        if user_id is not None:
            payload["userId"] = str(user_id)

        if prefer_user_id is not None:
            payload["preferUserId"] = prefer_user_id

        if merge_nested_objects is not None:
            payload["mergeNestedObjects"] = merge_nested_objects

        logger.debug(f"Iterable is sending the payload={payload}")
        return self._api_call(call=call, json_data=payload)

    def bulk_update_user(self, update_object):
        call = "/iterable/profile/bulk_update"
        self.request_timeout = 30
        return self._api_call(call=call, json_data=update_object.dict())

    def bulk_update_user_subscriptions(self, update_object): ### this should not be used, it's an overwriting api endpoint.
        return
        # call = "/api/users/bulkUpdateSubscriptions"
        # self.request_timeout = 30
        # return self._api_call(call=call, json_data=update_object.dict(exclude_unset=True))

    def subscribe_user(self, email, message_type_ids): ### check to see if this is being use
        """
        Callers should retry for IterableOverloadedException, not for any others.
        :param email:
        :param message_type_ids:
        :return:
        """
        call = "/iterable/users/updateSubscriptions"
        message_type_id_set = set()
        if not isinstance(message_type_ids, List):
            logger.error("Message type ids must be passed as a list")
            return None
        user = self.get_iterable_user_by_email(email=email, wait_for_user=True)
        for m in user.get("user", {}).get("dataFields", {}).get("subscribedMessageTypeIds", []):
            message_type_id_set.add(int(m))

        for message_type_id in message_type_ids:
            message_type_id_set.add(int(message_type_id))

        return self._api_call(call=call,
                              json_data={"email": email,
                                         "subscribedMessageTypeIds": list(message_type_id_set)})

    def unsubscribe_user(self, email, message_type_ids, channel_type_ids=None): ### check to see if this is being use
        """
        Callers should retry for IterableOverloadedException, not for any others.
        :param email:
        :param message_type_ids:
        :return:
        """
        call = "/api/users/updateSubscriptions"
        json_data = {
            "email": email
        }
        message_type_id_set = set()
        channel_type_ids_set = set()
        if not isinstance(message_type_ids, List):
            logger.error("Message type ids must be passed as a list")
            return None

        user = self.get_iterable_user_by_email(email=email, wait_for_user=True)
        for m in user.get("user", {}).get("dataFields", {}).get("unsubscribedMessageTypeIds", []):
            message_type_id_set.add(int(m))

        for unsubchannels in user.get("unsubscribedChannelIds", []):
            channel_type_ids_set.add(int(unsubchannels))

        if channel_type_ids:
            for c in channel_type_ids:
                channel_type_ids_set.add(int(c))

        for message_type_id in message_type_ids:
            message_type_id_set.add(int(message_type_id))

        if list(message_type_id_set):
            json_data.update({"unsubscribedMessageTypeIds": list(message_type_id_set)})

        if list(channel_type_ids_set):
            json_data.update({"unsubscribedChannelIds": list(channel_type_ids_set)})

        return self._api_call(call=call,
                              json_data=json_data)

    def trigger_campaign(self,
                         campaign_id=None,
                         recipient_email=None,
                         data_fields: Dict[str, Any] = None):
        """
        triggers an email campaign to a user/users
        :param campaign_id: int
        :param recipient_email:
        :param data_fields:
        :return:
        """

        call = "/iterable/email/trigger"
        payload = {"campaignId": campaign_id, "recipientEmail": recipient_email}
        if data_fields is not None:
            payload["dataFields"] = data_fields
        response = self._api_call(call=call, json_data=payload)
        logger.debug(f"Iterable campaign trigger with response={response}")
        return response

    def update_email(self, old_email, new_email):
        """
        Validates the old and new email, then calls iterable to update

        :param old_email:
        :param new_email:
        :return:
        """
        call = f"/iterable/profile/update/{old_email}"
        try:
            payload = IterableUpdateEmail(currentEmail=old_email, newEmail=new_email)
        except ValidationError as ve:
            logger.error("Email failed to validate - %s", ve)
            raise IterableUpdateException("Email failed to validate %s", ve) from ve

        return self._api_call(call=call, json_data=payload.dict())

    def track_event(self,
                    event_name=None,
                    event_id=None,
                    email=None,
                    created_at=None,
                    data_fields=None,
                    user_id=None,
                    campaign_id=None,
                    template_id=None,
                    event_wrapper=None):

        call = "/iterable/event/trigger"
        if event_wrapper:
            return self._api_call(call=call, json_data=event_wrapper.dict(exclude_none=True))

        payload = {"eventName": str(event_name)}

        if event_id is not None:
            payload["id"] = str(event_id)

        if email is not None:
            payload["email"] = email

        if created_at is not None:
            payload["createdAt"] = created_at

        if data_fields is not None:
            payload["dataFields"] = data_fields

        if user_id is not None:
            payload["userId"] = user_id

        if campaign_id is not None:
            payload["campaignId"] = campaign_id

        if template_id is not None:
            payload["templateId"] = template_id

        response = self._api_call(call=call, json_data=payload)
        logger.info(f"Iterable event tracked with response={response}")
        return response

    def send_standalone_email(self,
                              kind: StandaloneEmailKind,
                              session: Session,
                              recipient_email: str,
                              data_fields: Dict[str, Any] = None):
        call = "/iterable/email/trigger"

        # t = session.query(StandaloneEmail) \
        #     .filter(StandaloneEmail.kind == kind) \
        #     .one_or_none()
        # if not t:
        #     logger.error(f"Could not find campaign ID for standalone email: {kind}")
        #     return

        # payload = {
        #     'campaignId': t.iterable_campaign_id,
        #     'recipientEmail': recipient_email
        # }

        iterable_campaign_id = None
        if kind.value == 'contact_support':
            iterable_campaign_id = app_settings.iterable_contact_support_campaign_id
        elif kind.value == 'reset_password':
            iterable_campaign_id = app_settings.iterable_reset_password_campaign_id
        elif kind.value == 'login_link':
            iterable_campaign_id = app_settings.iterable_login_link_campaign_id

        if not iterable_campaign_id:
            logger.error(f"Could not find campaign ID for standalone email: {kind}")
            return

        payload = {
            'campaignId': iterable_campaign_id,
            'recipientEmail': recipient_email
        }

        if data_fields is not None:
            payload['dataFields'] = data_fields

        response = self._api_call(call=call, json_data=payload)
        return response

    def list_channels(self) -> List[IterableChannelModel]:
        call = "/iterable/channels"
        response = self._api_call(call=call, method="GET")
        return parse_obj_as(List[IterableChannelModel], response.get('channels'))

    def list_message_types(self): ### this is not used
        call = "/api/messageTypes"
        response = self._api_call(call=call, method="GET")

        return response \
            .get('body') \
            .get('messageTypes')

    def list_campaigns(self): ### check to see if this is used
        call = "/api/campaigns"
        response = self._api_call(call=call, method="GET")

        return response \
            .get('body') \
            .get('campaigns')
    
    def validate_registration_email(self, email, first_name, last_name):
        call = "/register/email"
        response = self._api_call(call=call, 
                                  json_data={
                                        "email": email,
                                        "first_name": first_name,
                                        "last_name":last_name,
                                        "signup_source": "figure1"
                                    },
                                  method="POST")

        return response

    def forget_user(self, email): ### this is not used
        call = f"/api/users/forget"
        json_data = {"email": email}
        return self._api_call(call=call, json_data=json_data, method='POST')

    def delete_user(self, email): # changing this to unsub users instead of fully deleting them from iterable in case email is being used by other brands
        # call = f"/api/users/{email}"
        # return self._api_call(call=call, method='DELETE')
        return self.unsubscribe_user_from_all_channels(email)

    def get_fmid(self, email): ### this is not used
        call = f"/v1/figure_user_map/email"
        return self._api_call(call=call, json_data={ "email": email }, method="GET")

    def _wait_for_iterable_user(self,
                                email: str,
                                timeout: int = 120):
        """
        Waits until the user exists in iterable.  Returns the iterable response once found,
         or raises an IterableUserNotFound
        if the user is not found within the timeout.
        :param iterable_client:
        :param email:
        :param timeout: the duration to wait, in seconds
        :return:
        """
        delay = 10
        retries = timeout // delay + 1
        for i in range(retries):
            try:
                return self.get_iterable_user_by_email(email=email)
            except IterableUserNotFound:
                time.sleep(delay)
            if i == retries - 1:
                raise IterableUserNotFound(msg=f"Failed to find iterable user: {email}")
