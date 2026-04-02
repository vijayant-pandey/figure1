import pytest

from figure1.common.types import FeedCardModel


a_case = {
    'caseUuid': "uuid",
    'authorProfessionLabel': 'authorProfessionLabel',
    'authorProfessionUuid': 'authorProfessionUuid',
    'authorUid': 'authorUid',
    'authorUsername': 'authorUsername',
    'authors': [1, 2, 3],
    'isAnonymous': False,
}


def test_anonymous_feed_card():
    # when isAnonymous is False
    feed_card = FeedCardModel.parse_obj(a_case).dict()

    assert feed_card.get('authorProfessionLabel')
    assert feed_card.get('authorProfessionUuid')
    assert feed_card.get('authorUid')
    assert feed_card.get('authorUsername')
    assert feed_card.get('authors')
    assert feed_card.get('isAnonymous') is False

    # when isAnonymous is True
    a_case.update({'isAnonymous': True})
    feed_card = FeedCardModel.parse_obj(a_case).dict()

    assert feed_card.get('caseUuid')
    assert feed_card.get('authorProfessionLabel')
    assert feed_card.get('authorProfessionUuid')
    assert feed_card.get('authorUid') is None
    assert feed_card.get('authorUsername') is None
    assert feed_card.get('authors')
    assert feed_card.get('isAnonymous') is True
