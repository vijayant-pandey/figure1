import logging
import sys

import requests
from enum import Enum

from pydantic import Field
from pydantic.main import BaseModel
from typing import List, Optional, Union

from figure1.common.models.db import User
from figure1.common.types import GroupModel
from figure1.configuration import app_settings

logger = logging.getLogger('figure1.slack_client')


class SlackIcon(Enum):
    ROCKET = ":rocket:"
    HEALTH_WORKER = ":health_worker:"
    NO_VALUE = None


class SlackColour(Enum):
    GREY = "#dddddd"
    GREEN = "#6c946a"


class MessageField(BaseModel):
    title: str
    value: Optional[str]
    short: bool = True


class SlackAttachment(BaseModel):
    # American spelling 'color' is needed for slack's webhook API
    color: Optional[SlackColour]
    colour: SlackColour
    fallback: str
    pretext: str
    attachment_fields: List[MessageField] = Field(alias='fields')

    def __init__(self, **data):
        super().__init__(**data)
        self.color = self.colour


class SlackMessage(BaseModel):
    username: str
    icon_emoji: SlackIcon
    channel: Optional[str]
    attachments: List[SlackAttachment]


class SlackClient:
    def __init__(self):
        self.slack_enabled = app_settings.slack_enabled
        self.slack_webhook_url = app_settings.slack_webhook_url
        self.username = app_settings.slack_username

    def _api_call(self, slack_message: SlackMessage):
        if app_settings.read_only_dev_mode:
            logger.warning("READ-ONLY MODE: Blocked Slack API call")
            return
            
        if not self.slack_enabled or not self.slack_webhook_url:
            logger.info("Slack messages are disabled, nothing to do")
            return

        if not isinstance(slack_message, SlackMessage):
            raise ValueError("Invalid slack message object passed")

        data = slack_message.json(by_alias=True)
        r = requests.post(self.slack_webhook_url,
                          data=data,
                          headers={
                              "Content-Type": "application/json",
                              "Content-Length": str(sys.getsizeof(data))
                          })
        if r.status_code != 200:
            logger.error(f"Slack webhook returned non 200 status code: {r.status_code}")

    def send_message(self,
                     message: str,
                     fields: [MessageField] = None,
                     colour: SlackColour = SlackColour.GREY,
                     icon: SlackIcon = SlackIcon.NO_VALUE,
                     channel: str = None,
                     entity: Union[User, GroupModel] = None):
        fields = fields or []
        if isinstance(entity, User):
            fields.insert(0, MessageField(title="email", value=entity.email))
            fields.insert(1, MessageField(title="username", value=entity.username))
        if isinstance(entity, GroupModel):
            fields.insert(0, MessageField(title="Name", value=entity.groupName))
            fields.insert(1, MessageField(title="Description", value=entity.groupDescription))
        if channel:
            message = SlackMessage(username=self.username,
                                   icon_emoji=icon.value,
                                   channel=channel,
                                   attachments=[SlackAttachment(colour=colour.value,
                                                                fallback=message,
                                                                pretext=message,
                                                                fields=fields)])
        else:
            logger.warning(f" No channel was provided")
        try:
            self._api_call(slack_message=message)
        except ValueError:
            logger.exception("Failed to send slack message")
