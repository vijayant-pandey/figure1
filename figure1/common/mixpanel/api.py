from mementos import mementos
from mixpanel import Mixpanel

from figure1.configuration import app_settings


class MixpanelAPI(mementos):
    mixpanel_api_disabled = False
    client = None

    def __init__(self):
        api_key = app_settings.mixpanel_api_key

        if not api_key:
            self.mixpanel_api_disabled = True
        else:
            self.client = Mixpanel(api_key)
