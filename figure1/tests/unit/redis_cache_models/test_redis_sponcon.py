from figure1.store import UserSponsoredContentStore, UserRFYFeedConfig, SponsoredContentCache, UserKeyManagement
from figure1.pro.tracking.domain import handle_views


def test_sponcon_order():
    list_of_items = ['a', 'b', 'c']

    user_uuid = 'some_user_uuid'

    store = UserSponsoredContentStore(user_uuid=user_uuid)
    store.write_sponcon_list(items=list_of_items)

    item1 = store.get_next_item()
    assert item1 == 'a'

    item2 = store.get_next_item()
    assert item2 == 'b'

    item3 = store.get_next_item()
    assert item3 == 'c'


def test_sponcon_update(test_user):
    SponsoredContentCache.write_sponsored_content(['a', 'b', 'c'])
    list_of_items = ['a', 'b', 'c']
    handle_views(user_uid=test_user.get('userUid'), detail_views=False, feed_data={
        'views': [{
            'feedTypeUuid': "testfeed",
            'caseUuids': ['i', 'b', 'z', 'x']
        }]
    })

    store = UserSponsoredContentStore(user_uuid=test_user.get('userUuid'))
    store.write_sponcon_list(items=list_of_items)

    item1 = store.get_next_item()
    assert item1 == 'a'

    store.write_sponcon_list(['d'])

    item3 = store.get_next_item()
    assert item3 == 'c'

    item4 = store.get_next_item()
    assert item4 == 'd'

    k = UserKeyManagement.delete_user_keys()
    assert k > 0
