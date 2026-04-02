import logging
import bson
import pymongo
from datetime import datetime
from jsonschema.exceptions import ValidationError
import figure1.common.utils.mongo_utils as mu
from figure1.common.models.validator import Validate


class CasesPrequelModel:
    comment_threshold = 50

    def __init__(self):
        self.mongo_client = pymongo.MongoClient("mongo:27017")
        self.images = self.mongo_client["figure1"]["images"]
        self.raw_images = self.mongo_client["figure1"]["rawimages"]
        self.quizzes = self.mongo_client["figure1"]["quizzes"]
        self.v = Validate()

    def get_accepted_answer_id(self, case_id):
        if not bson.objectid.ObjectId.is_valid(case_id):
            raise ValueError(f"case_id {case_id} is not a valid ID")

        case = self.images.find_one({"_id": bson.objectid.ObjectId(case_id)}, {"answer": 1})

        if not case or not case.get('answer'):
            return None
        else:
            return case.get('answer').get('commentId')

    def get_case_dates(self, case_id):
        if not bson.objectid.ObjectId.is_valid(case_id):
            raise ValueError(f"case_id {case_id} is not a valid ID")

        case = self.images.find_one(
            {"_id": bson.objectid.ObjectId(case_id)},
            {"created": 1, "modified": 1, "deleted": 1}
        )

        if not case:
            return None
        else:
            return case

    def get_comment_dates(self, case_id, comment_id):
        if not bson.objectid.ObjectId.is_valid(case_id):
            raise ValueError(f"case_id {case_id} is not a valid ID")
        if not bson.objectid.ObjectId.is_valid(comment_id):
            raise ValueError(f"comment_id {comment_id} is not a valid ID")

        case = self.images.find_one(
            {"_id": bson.objectid.ObjectId(case_id)},
            {"comments._id": 1, "comments.created": 1}
        )

        if not case or not case.get('comments'):
            return None

        try:
            return next(c for c in case.get('comments') if c.get('_id') == bson.objectid.ObjectId(comment_id))
        except StopIteration:
            return None

    def get_image_filename(self, legacy_id):
        if not bson.objectid.ObjectId.is_valid(legacy_id):
            raise ValueError(f"legacy_id {legacy_id} is not a valid ID")

        r = self.raw_images.find_one(
            {"_id": bson.objectid.ObjectId(legacy_id)},
            {"name": 1}
        )
        if r is None:
            logging.warning(f"Couldn't find rawimages document for legacy_id {legacy_id}")
            return None
        elif "name" not in r:
            logging.warning(f"Couldn't find name property in rawimages document for legacy_id {legacy_id}")
        else:
            return r['name']

    def get_case_ids(self):
        query = {}
        query_args = {
            "sort": [("_id", pymongo.DESCENDING)]
        }

        for i in self.images.find(query, {"_id": 1, "comments": 1, "followers": 1, "voteCount": 1}, **query_args):
            case = mu.convert_bson(i)
            yield self._sanitize_case(case=case)

    def get_case(self, case_id):
        """
        Gets the legacy case which matches the case_id.  If a case is not found returns None.
        """
        if not bson.objectid.ObjectId.is_valid(case_id):
            raise ValueError(f"case_id {case_id} is not a valid ID")
        else:
            i = self.images.find_one({"_id": bson.objectid.ObjectId(case_id)})
            if i is None:
                return None
            else:
                case = mu.convert_bson(i)
                c_case = self._sanitize_case(case)
                try:
                    self.v.validate(c_case, 'legacy_case')
                except ValidationError as ve:
                    logging.error(f"Validation failed for {case_id}, {ve}")
                    return None
                return c_case

    def get_case_exists(self, case_id):
        """
        Checks if a case_id exists.  If a case is found returns the case id, otherwise returns None.
        """
        if not bson.objectid.ObjectId.is_valid(case_id):
            raise ValueError(f"case_id {case_id} is not a valid ID")
        else:
            i = self.images.find_one({"_id": bson.objectid.ObjectId(case_id)}, {"_id"})
            if i is None:
                return None
            else:
                case = mu.convert_bson(i)
                return case['_id']

    def get_quiz_data(self, case_id):
        """
        Gets the quiz data for a case_id.  If the case is not a quiz, returns None.
        """
        if not bson.objectid.ObjectId.is_valid(case_id):
            raise ValueError(f"case_id {case_id} is not a valid ID")
        else:
            i = self.quizzes.find_one({"imageId": bson.objectid.ObjectId(case_id)})
            if i is None:
                return None
            else:
                return mu.convert_bson(i)

    def _try_convert(self, expected_type, prop):
        if expected_type is int:
            return int(prop)
        elif expected_type is str:
            return str(prop)
        else:
            raise ValueError

    def _sanitize_required_property(self, case, name, expected_type, default_value):
        logger = logging.getLogger(__name__)
        case_id = case["_id"]

        if name not in case:
            logger.debug("Missing property '%s' on case: %s", name, case_id)
            case[name] = default_value
        elif type(case[name]) is not expected_type:
            logger.warning("Invalid type for '%s' on case: %s - Expected %s for value %s, got %s",
                           name, case_id, expected_type, case[name], type(case[name]))
            try:
                case[name] = self._try_convert(expected_type, case[name])
            except ValueError as e:
                logger.warning("Invalid type for '%s' on case: %s - Expected %s for value %s, got %s",
                               name, case_id, expected_type, case[name], type(case[name]))
                case[name] = default_value

    def _sanitize_optional_property(self, case, name, expected_type):
        logger = logging.getLogger(__name__)
        case_id = case["_id"]

        if name in case and type(case[name]) is not expected_type:
            try:
                case[name] = self._try_convert(expected_type, case[name])
            except ValueError:
                logger.warning("Invalid type for '%s' on case: %s - Expected %s for value %s, got %s",
                               name, case_id, expected_type, case[name], type(case[name]))
                case[name] = ""

    def _sanitize_case(self, case):
        self._sanitize_optional_property(case, "url", str)
        self._sanitize_optional_property(case, "title", str)
        self._sanitize_optional_property(case, "caption", str)
        self._sanitize_optional_property(case, "author", str)
        self._sanitize_optional_property(case, "language", str)
        self._sanitize_required_property(case, "voteCount", int, 0)
        self._sanitize_required_property(case, "followers", list, [])
        self._sanitize_optional_property(case, "specialty", str)
        self._sanitize_optional_property(case, "created", datetime)
        self._sanitize_optional_property(case, "modified", datetime)

        case["followCount"] = len(case["followers"])
        case["commentCount"] = len(case["comments"])
        for c in case['comments']:
            c['text'] = str(c['text'])
        if "language" in case:
            case["language"] = case["language"][0:7]
        return case
