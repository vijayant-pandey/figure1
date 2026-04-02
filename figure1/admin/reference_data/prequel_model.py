import logging

import pymongo
import figure1.common.utils.mongo_utils as mu


class ReferenceDataPrequelModel:
    def __init__(self):
        self.mongo_client = pymongo.MongoClient("mongo:27017")
        self.figure1 = self.mongo_client["figure1"]
        self.specialties = self.figure1["specialties"]

    def get_specialties(self):
        query_fields = {
            "_id": 1,
            "category": 1,
            "strings": 1,
        }

        resp = []
        logging.info("Getting specialties from mongo...")
        for i in self.specialties.find({}, query_fields):
            specialty = mu.convert_bson(i)
            resp.append(self._sanitize_specialty(specialty))

        return resp

    @staticmethod
    def _sanitize_specialty(specialty):
        id = specialty['_id'],
        dict = {'_id': id}

        dict['profession'] = ReferenceDataPrequelModel._get_nested_property_or_default(
            func=lambda s: s.get('category').get('strings').get('en').get('label'),
            dict=specialty,
            id=id,
            property_name='profession',
            default_value="",
            expected_type=str)

        dict['singular_label'] = ReferenceDataPrequelModel._get_nested_property_or_default(
            func=lambda s: s.get('strings').get('en').get('singularLabel'),
            dict=specialty,
            id=id,
            property_name='singular_label',
            default_value="",
            expected_type=str)

        dict['plural_label'] = ReferenceDataPrequelModel._get_nested_property_or_default(
            func=lambda s: s.get('strings').get('en').get('pluralLabel'),
            dict=specialty,
            id=id,
            property_name='plural_label',
            default_value="",
            expected_type=str)

        dict['indefinite_article'] = ReferenceDataPrequelModel._get_nested_property_or_default(
            func=lambda s: s.get('strings').get('en').get('indefiniteArticle'),
            dict=specialty,
            id=id,
            property_name='indefinite_article',
            default_value="",
            expected_type=str)

        label = ReferenceDataPrequelModel._get_nested_property_or_default(
            func=lambda s: s.get('strings').get('en').get('label'),
            dict=specialty,
            id=id,
            property_name='label',
            default_value="",
            expected_type=str)
        list_label = ReferenceDataPrequelModel._get_nested_property_or_default(
            func=lambda s: s.get('strings').get('en').get('listLabel'),
            dict=specialty,
            id=id,
            property_name='label',
            default_value="",
            expected_type=str)
        # label and type_name are set based on which label/list_label values are present.
        dict['label'] = label if label else list_label
        dict['type_name'] = list_label if list_label else label

        return dict

    @staticmethod
    def _set_property_or_default(output, input, property_name, default_value, expected_type=None):
        if property_name not in input:
            logging.info(f"Missing property '{property_name}' on id: {id}")
            value = default_value
        elif expected_type is not None and type(input[property_name]) is not expected_type:
            logging.warning(f"Invalid type for '{property_name}' on id: {id}")
            value = default_value
        else:
            value = input[property_name]

        output[property_name] = value

    @staticmethod
    def _get_nested_property_or_default(func, dict, id, property_name, default_value, expected_type=None):
        try:
            value = func(dict)
            if not value or (expected_type is not None and type(value) is not expected_type):
                logging.info(f"Missing property '{property_name}' on id: {id}")
                return default_value
        except Exception as e:
            logging.warning(f"Failed to get property '{property_name}' for id {id}: {e}")
            return default_value

        return func(dict)
