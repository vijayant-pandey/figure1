import bson
import json as js


def convert_bson(d):
    """
    Returns a dictionary where bson object IDs have been converted to strings
    :param d: the bson object to convert
    :return: dictionary[string, string]
    """
    if type(d) == bson.objectid.ObjectId:
        return str(bson.objectid.ObjectId(d))
    elif type(d) == str:
        sanitized_string = ""
        for character in d:
            if not ord(character):
                continue
            sanitized_string = sanitized_string + character
        try:
            return js.loads(sanitized_string)
        except Exception as e:
            pass
        return sanitized_string
    elif type(d) == list:
        a = []
        for item in d:
            a.append(convert_bson(item))
        return a
    elif type(d) == dict:
        for nextItem in d:
            key = convert_bson(nextItem)
            d[key] = convert_bson(d[key])
    return d
