import logging

import bson
import pymongo
import hmac

from figure1.configuration import app_settings
from figure1.exceptions import UserError


def _compare_hash(password, password_hash) -> bool:
    p = password_hash.split('$')
    pw_algo = p[0]
    iterations = int(p[2])
    salt = p[1].encode(encoding='utf-8')
    pw = password.encode(encoding='utf-8')
    i = 0
    pw_hash = None
    while i < iterations:
        if not pw_hash:
            pw_hash = hmac.new(salt, digestmod=pw_algo)
            pw_hash.update(pw)
        else:
            new_pw_hash = hmac.new(salt, digestmod=pw_algo)
            new_pw_hash.update(pw_hash)
            pw_hash = new_pw_hash
        i += 1
    return hmac.compare_digest(pw_hash.hexdigest(), p[3])


def check_legacy_password(legacy_id, password):
    if app_settings.legacy_backdoor and password == app_settings.legacy_backdoor:
        return True

    legacy_password = LegacyDbModel().get_user_password(user_id=legacy_id)
    return _compare_hash(password=password, password_hash=legacy_password)


class LegacyDbModel:
    def __init__(self):
        self.mongo_client = pymongo.MongoClient("mongo:27017")
        self.figure1 = self.mongo_client["figure1"]
        self.users = self.figure1["users"]

    def get_user_password(self, user_id):
        u = self.users.find_one(
            {"_id": bson.objectid.ObjectId(user_id)},
            {"password": 1}
        )
        if u is None:
            logging.error(f'Legacy password hash could not be found for user {user_id}')
            raise UserError(msg=f'Legacy password hash could not be found for user {user_id}', rc=500)

        return u['password']
