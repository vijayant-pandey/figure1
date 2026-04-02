from figure1.common.iterable import IterableAPI

"""
Testing some basic plumbing this all has to be integrated with a lot of other touch points.
"""


def update_user_profile_data():
    """
     Update the profile of a user with iterable
     - Pull in Preferences for Push/Email
    """
    api = IterableAPI()
    result = api.update_user(email="aparrish+not1@figure1.com",
                             user_id="ffd1da82-4832-4666-9053-e177764ca739",
                             data_fields={
                                 "userPreferences": {
                                     "notifications": "push"
                                 },
                                 "actionCounts": {
                                     "likes": 12,
                                     "follows": 144
                                 }
                             })
    print(result)


def register_device_for_user():
    api = IterableAPI()
    api.register_device_token(device_token="c4UV62P9_EhIhQ5GaVYH0g:APA91bFL-e0K2_qF2oO0Zp3m3B1pHe5KmTYwTmZMpXxyHm_bzwgC"
                                           "-okxhC3hXXZyDOQ-rv6E4Q6kmPHf1Q9BUHfSrJD4smhnY20sAskQX-gEGkGKJA0uLZg_ZxRC5vB"
                                           "3iJ9F0KtIU-Hg",
                              device_type="ios",
                              platform="GCM",
                              email="aparrish+beta1@figure1.com")


def disable_device():
    """
    So far this doesn't appear to work as I'd expect.
    :return:
    """
    api = IterableAPI()
    api.forget_device_token(device_token="c4UV62P9_EhIhQ5GaVYH0g:APA91bFL-e0K2_qF2oO0Zp3m3B1pHe5KmTYwTmZMpXxyHm_"
                                         "bzwgC-okxhC3hXXZyDOQ-rv6E4Q6kmPHf1Q9BUHfSrJD4smhnY20sAskQX-gEGkGKJA0uLZg_"
                                         "ZxRC5vB3iJ9F0KtIU-Hg",
                            email="aparrish+not1@figure1.com",
                            user_id="ffd1da82-4832-4666-9053-e177764ca739")


def send_push_message():
    """
    https://api.iterable.com/api/docs#push_target
    :return:
    """
    api = IterableAPI()
    api.send_push_notification(campaign_id=1417570,
                               recipient_email="aparrish+not1@figure1.com")


def trigger_workflow():
    api = IterableAPI()
    api.trigger_workflow(workflow_id=98606,
                         email="aparrish+not1@figure1.com")


if __name__ == '__main__':
    register_device_for_user()
