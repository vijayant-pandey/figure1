import re

from urllib3.util import parse_url

from figure1.common.utils import find_all_urls
from figure1.common.utils import markdown_all_urls
from figure1.common.utils import markdown_url
from figure1.common.utils import replace_dict_key_value
from figure1.common.utils import split_list_to_smaller_lists


def _compare_url_to_markdown(url, markdown):
    m = re.match(r'\[(\S+)\]\((\S+)\)', markdown)
    assert m.group(2) == url
    pu = parse_url(url)
    assert m.group(1) == pu.hostname


def _test_urls():
    """
    This is a list of urls to test to ensure we can extract and convert them to markdown correctly. They need to be
    valid, but they don't have to go anywhere.
    :return:
    """
    test_urls = ['http://www.google.ca/query=qasdf',
                 'https://www.amazon.com/gp/browse.html?node=21217041011&ref_=nav_em_sh_heating-cooling_0_2_7_8',
                 'http://www.excite.ca/url=as']
    for u in test_urls:
        yield u


def _test_marked_down_urls():
    """
    This is the same list of urls as test_urls, but returned marked down
    :return:
    """
    for url in _test_urls():
        md = markdown_url(url)
        _compare_url_to_markdown(url, md)
        yield md


def test_search_replace_dict_key():
    """
    Ensure that keys/values are replaced correctly
    :return:
    """
    depth_search = {
        "top_level": {
            "second_level": [
                {
                    "Third": "unique_string",
                    "Third2": "non_unique_string"
                },
                {
                    "Fourth": "unique_fourth_string",
                    "Fourth2": "non_unique_string"
                }
            ],
            "third_level": {
                "third_third_level": "third_unique_string",
                "third_replace_me": "non_unique_string"
            }
        }
    }

    replace_dict_key_value(search_key="Fourth",
                           replace_key="Fourth2",
                           replace_value="non_unique_string_replace",
                           search_dict=depth_search)

    replace_dict_key_value(search_key="third_third_level",
                           replace_key="third_replace_me",
                           replace_value="something_different",
                           search_dict=depth_search)

    replace_dict_key_value(search_key=None,
                           search_value="unique_string",
                           replace_key="Third2",
                           replace_value="replace_string",
                           search_dict=depth_search)
    for i in depth_search["top_level"]["second_level"]:
        if "Fourth2" in i.keys():
            assert i["Fourth2"] == "non_unique_string_replace"
        if "Third2" in i.keys():
            assert i["Third2"] == "replace_string"

    assert depth_search["top_level"]["third_level"]["third_replace_me"] == "something_different"


def test_list_split():
    """
    Should return a generator of lists in size <chunk_size> until the original list is finished.
    """
    test_list = [1, 2, 3, 4, 5, 6, 7, 8, 9]
    it = split_list_to_smaller_lists(test_list, chunk_size=7)
    list_1 = next(it)
    list_2 = next(it)
    assert list_1[0] == 1
    assert list_1[-1] == 7
    assert list_2[0] == 8
    assert list_2[-1] == 9
    assert len(list_1) == 7
    assert len(list_2) == 2


def test_markdown_url_replace():
    """
    Given some urls inserted into the caption, ensure we replace them properly
    :return:
    """
    urls_to_test = list(_test_urls())
    marked_down_urls = list(_test_marked_down_urls())
    test_text = """This is a caption with a url like {0}!
    it also contains a duplicate here {0}?
    this is another url {1} , finally this one {2}."""

    marked_down = markdown_all_urls(test_text.format(*urls_to_test))

    assert marked_down == test_text.format(*marked_down_urls)


def test_find_all_urls():
    """
    Ensure that we can find all the urls in the caption
    :return:
    """
    urls_to_test = list(_test_urls())
    url_not_in_text = ['http://www.google.ca/other']
    test_text = """This is a caption with a url like {0},
        it also contains a duplicate here {0},
        this is another url {1} , finally this one {2}"""

    url_list = list(find_all_urls(test_text.format(*urls_to_test)))
    assert set(url_list) ^ set(urls_to_test) == set()
    assert set(url_list) & set(url_not_in_text) == set()
