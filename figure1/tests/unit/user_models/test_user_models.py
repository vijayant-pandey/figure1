import pytest
from pydantic import ValidationError

from figure1.common.helpers import UserDocument


def test_user_author_model(test_user, load_db):
    """
    The required fields are needed by either the admin tool or for comments. The tree structure should not be necessary
    but is used by the admin tool for the moment
    :param test_user:
    :param load_db:
    :return:
    """
    session = load_db
    required_fields = ['isPartner',
                       'isVerified',
                       'username',
                       'userUuid',
                       'userUid',
                       'treeUuid',
                       'userType',
                       'isDeleted',
                       'countryUuid',
                       'stateUuid',
                       'caseCommentDisplayName',
                       'profileDisplayName',
                       'displayName']
    required_tree_fields = ['onboardingDisplayName',
                            'caseCommentDisplayName',
                            'profileDisplayName',
                            'profession',
                            'specialty',
                            'subspecialty']
    author_doc = UserDocument.get_compact_user_data(user_uuid=test_user.get("userUuid"), session=session)
    for r in required_fields:
        assert r in author_doc.keys()
    tree = author_doc.get('tree')
    for t in required_tree_fields:
        assert t in tree.keys()
