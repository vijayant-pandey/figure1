import logging

import bson
import enum
import pymongo

import figure1.common.utils.mongo_utils as mu

from datetime import datetime, timedelta, timezone


class LegacyFollowingType(enum.Enum):
    USER = 2
    IMAGE = 3
    COLLECTION = 4


class LegacyGroup(enum.Enum):
    ORTHOPEDICS_SUBCOMMUNITY = '5e222725d2e91c9df15ab0f8'


class UsersPrequelModel:

    def __init__(self):
        self.mongo_client = pymongo.MongoClient("mongo:27017")
        self.figure1 = self.mongo_client["figure1"]
        self.users = self.figure1["users"]
        self.following = self.figure1["following"]
        self.collections = self.figure1["f1collections"]
        self.verifications = self.figure1["verificationrequests"]
        self.group_memberships = self.figure1["groupMemberships"]

    def get_user(self, user_id):
        """
        Gets the user which matches the user_id.  If a user is not found returns None.
        """
        query_fields = {
            "created": 1,
            "modifiedAt": 1,
            "username": 1,
            "email": 1,
            "targetableCountry": 1,
            "verified": 1,
            "admin": 1,
            "specialtyCategory": 1,
            "specialtyObject": 1,
            "isDeletedAccount": 1,
            "bio": 1,
            "institution": 1,
            "fullName": 1,
            "link": 1,
            "lastAccessed": 1,
            "isInstitutionalAccount": 1,
            "isEmailVerified": 1,
            "emailPreferences": 1,
            "avatarFilename": 1,
        }

        if not bson.objectid.ObjectId.is_valid(user_id):
            raise ValueError(f"user_id {user_id} is not a valid ID")
        else:
            u = self.users.find_one({"_id": bson.objectid.ObjectId(user_id)}, query_fields)
            if u is None:
                return None
            else:
                user = mu.convert_bson(u)
                return UsersPrequelModel._sanitize_user(user)

    def get_recent_users(self, days):
        """
        Gets users which have been accessed or created in the last :days: days
        Returns dicts with a subset of user properties
        """
        dt = datetime.now(tz=timezone.utc) - timedelta(days=days)
        query = {
            "$or": [{"lastAccessed": {'$gt': dt}}, {"created": {'$gt': dt}}]
        }
        query_args = {
            "sort": [("_id", pymongo.DESCENDING)]
        }
        query_fields = {
            "verified": 1,
            "lastAccessed": 1,
        }

        for i in self.users.find(query, query_fields, **query_args):
            u = mu.convert_bson(i)
            res = {'_id': u['_id']}
            UsersPrequelModel._set_property_or_default(res, u, 'verified', None, bool, required=False)
            UsersPrequelModel._set_property_or_default(res, u, 'lastAccessed', None, datetime, required=False)
            yield res

    def get_all_users(self, cursor=None):
        """
        Gets all users regardless of access and creation date
        Returns dicts with a subset of user properties
        """
        if cursor:
            query = {'_id': {'$lt': bson.objectid.ObjectId(cursor)}}
        else:
            query = {}

        query_args = {
            "sort": [("_id", pymongo.DESCENDING)]
        }
        query_fields = {
            "verified": 1,
            "lastAccessed": 1,
        }

        for i in self.users.find(query, query_fields, **query_args):
            u = mu.convert_bson(i)
            res = {'_id': u['_id']}
            UsersPrequelModel._set_property_or_default(res, u, 'verified', None, bool, required=False)
            UsersPrequelModel._set_property_or_default(res, u, 'lastAccessed', None, datetime, required=False)
            yield res

    def get_verification(self, user_id):
        """
        Gets the verification request for a user which matches the user_id.  If a request is not found returns None.
        Note that unverified users can have a verification_request record.
        """
        query_fields = {
            "npi": 1,
            "firstName": 1,
            "lastName": 1,
        }

        if not bson.objectid.ObjectId.is_valid(user_id):
            raise ValueError(f"user_id {user_id} is not a valid ID")
        else:
            b = self.verifications.find_one({"user": bson.objectid.ObjectId(user_id)}, query_fields)
        if b is None:
            return None

        v = mu.convert_bson(b)
        res = {}
        UsersPrequelModel._set_property_or_default(res, v, 'firstName', None, str, required=False)
        UsersPrequelModel._set_property_or_default(res, v, 'lastName', None, str, required=False)
        if v.get('npi'):
            try:
                res['npi'] = int(v['npi'])
            except ValueError:
                pass
        return res

    def get_followed_cases(self, user_id):
        """
        Gets the cases that a user is following.
        """
        if not bson.objectid.ObjectId.is_valid(user_id):
            raise ValueError(f"user_id {user_id} is not a valid ID")
        query = {
            'type': LegacyFollowingType.IMAGE.value,
            'user': bson.objectid.ObjectId(user_id)
        }
        query_fields = {
            "followedID": 1,
            "followedImage": 1,
        }
        for b in self.following.find(query, query_fields):
            f = mu.convert_bson(b)
            if f.get('followedID'):
                yield f.get('followedID')
            else:
                yield f.get('followedImage')

    def get_saved_cases(self, user_id):
        """
        Gets the case_ids of cases that a user has saved.
        """
        if not bson.objectid.ObjectId.is_valid(user_id):
            raise ValueError(f"user_id {user_id} is not a valid ID")
        query_fields = {"caseIDs": 1}

        cases = []
        for b in self.collections.find({'author': bson.objectid.ObjectId(user_id)}, query_fields):
            c = mu.convert_bson(b)
            cases.extend([x[0] for x in c.get('caseIDs')])
        return cases

    def get_followed_users(self, user_id):
        """
        Gets the user_ids of users that a user is following.
        """
        if not bson.objectid.ObjectId.is_valid(user_id):
            raise ValueError(f"user_id {user_id} is not a valid ID")
        query = {
            'type': LegacyFollowingType.USER.value,
            'user': bson.objectid.ObjectId(user_id)
        }
        query_fields = {"followedID": 1}
        for b in self.following.find(query, query_fields):
            u = mu.convert_bson(b)
            yield u.get('followedID')

    def get_group_memberships(self, user_id):
        """
        Gets the groups that a user is a member of.
        """
        if not bson.objectid.ObjectId.is_valid(user_id):
            raise ValueError(f"user_id {user_id} is not a valid ID")
        query = {
            'userID': bson.objectid.ObjectId(user_id),
            'deletedAt': None
        }
        query_fields = {"groupID": 1}
        for b in self.group_memberships.find(query, query_fields):
            u = mu.convert_bson(b)
            if u.get('groupID') in [g.value for g in LegacyGroup]:
                yield LegacyGroup(u.get('groupID'))

    @staticmethod
    def _sanitize_user(user):
        _dict = {'_id': user['_id']}

        UsersPrequelModel._set_property_or_default(_dict, user, 'created', None, datetime)
        UsersPrequelModel._set_property_or_default(_dict, user, 'modifiedAt', None, datetime, required=False)
        UsersPrequelModel._set_property_or_default(_dict, user, 'username', "", str)
        UsersPrequelModel._set_property_or_default(_dict, user, 'email', "", str)
        UsersPrequelModel._set_property_or_default(_dict, user, 'targetableCountry', "", str)
        UsersPrequelModel._set_property_or_default(_dict, user, 'verified', False, bool)
        UsersPrequelModel._set_property_or_default(_dict, user, 'admin', False, bool)
        UsersPrequelModel._set_property_or_default(_dict, user, 'isDeletedAccount', False, bool, required=False)
        UsersPrequelModel._set_property_or_default(_dict, user, 'bio', None, str, required=False)
        UsersPrequelModel._set_property_or_default(_dict, user, 'institution', None, str, required=False)
        UsersPrequelModel._set_property_or_default(_dict, user, 'fullName', None, str, required=False)
        UsersPrequelModel._set_property_or_default(_dict, user, 'link', None, str, required=False)
        UsersPrequelModel._set_property_or_default(_dict, user, 'lastAccessed', None, datetime, required=False)
        UsersPrequelModel._set_property_or_default(_dict, user, 'isInstitutionalAccount', False, bool, required=False)
        UsersPrequelModel._set_property_or_default(_dict, user, 'isEmailVerified', False, bool, required=False)
        UsersPrequelModel._set_property_or_default(_dict, user, 'emailPreferences', {}, dict, required=False)
        UsersPrequelModel._set_property_or_default(_dict, user, 'avatarFilename', None, str, required=False)

        _dict['specialtyProfession'] = UsersPrequelModel._get_nested_property_or_default(
            func=lambda s: s.get('specialtyObject').get('category').get('strings').get('en').get('label'),
            _dict=user,
            id=user['_id'],
            property_name='specialtyObject.category.strings.en.label',
            default_value=None,
            expected_type=str)
        label = UsersPrequelModel._get_nested_property_or_default(
            func=lambda s: s.get('specialtyObject').get('strings').get('en').get('label'),
            _dict=user,
            id=user['_id'],
            property_name='specialtyObject.strings.en.label',
            default_value=None,
            expected_type=str)
        list_label = UsersPrequelModel._get_nested_property_or_default(
            func=lambda s: s.get('specialtyObject').get('strings').get('en').get('listLabel'),
            _dict=user,
            id=user['_id'],
            property_name='specialtyObject.strings.en.listLabel',
            default_value=None,
            expected_type=str)
        _dict['specialtyType'] = list_label if list_label else label

        if len(_dict['targetableCountry']) > 3:
            _dict['targetableCountry'] = None

        return _dict

    @staticmethod
    def _set_property_or_default(output_dict, _dict, property_name, default_value, expected_type=None, required=True):
        id = _dict.get("_id")

        if property_name not in _dict:
            if required:
                logging.warning(f"Missing property '{property_name}' on id: {id}")
            value = default_value
        elif expected_type is not None and type(_dict[property_name]) is not expected_type:
            if expected_type is str:
                value = str(_dict[property_name])
            else:
                logging.warning(f"Invalid type for '{property_name}' on id: {id}")
                value = default_value
        elif expected_type is str and not _dict[property_name]:
            value = default_value
        else:
            value = _dict[property_name]

        output_dict[property_name] = value

    @staticmethod
    def _get_nested_property_or_default(func, _dict, id, property_name, default_value, expected_type=None):
        try:
            value = func(_dict)
            if not value or (expected_type is not None and type(value) is not expected_type):
                return default_value
        except Exception as e:
            logging.warning(f"Failed to get property '{property_name}' for id {id}: {e}")
            return default_value

        return func(_dict)
