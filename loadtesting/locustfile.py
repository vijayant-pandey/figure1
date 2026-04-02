import time
from random import choice
from string import ascii_letters, ascii_lowercase, ascii_uppercase, digits

from locust import HttpUser, task, between

def generate_random_email():
    return "".join([choice(ascii_letters) for x in range(25)]) + '@test.com'

def generate_random_name():
    return "".join([choice(ascii_letters) for x in range(10)])


class QuickstartUser(HttpUser):
    wait_time = between(1, 2.5)
    @task
    def create_user(self):
        user_create = {"profession_uuid":"e0911f79-16df-4adb-bd92-b3dffa289460",
                       "last_name": generate_random_name(),
                       "first_name": generate_random_name(),
                       "email": generate_random_email(),
                       "user_uid": generate_random_name(),
                       "screen_id":"registrationStarted"}
        self.client.post("/pro/v1/user/create", json=user_create)