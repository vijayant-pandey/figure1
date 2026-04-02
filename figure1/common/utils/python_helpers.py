from re import IGNORECASE
from re import MULTILINE
from re import compile
from re import escape
from re import sub
from typing import Iterator
from typing import List
from typing import Optional

from urllib3.util import Url
from urllib3.util import parse_url

url_regex = compile(r'(?<!\()(https?://[^.-][a-zA-Z0-9-.]+[^.-]\.\S{2,})\b[.,:;?!]*(?!\()', IGNORECASE | MULTILINE)


def find_all_urls(text) -> set:
    """
    Given a string of text, return a set of urls, an empty set is returned if no urls are found
    :param text:
    :return:
    """
    urls = url_regex.findall(text)
    url_set = set()
    if urls:
        for u in urls:
            url_set.add(u)
    return url_set


def markdown_all_urls(text) -> str:
    """
    Returns a string with the urls marked down
    :param text: string to search for urls
    :return:
    """
    urls = find_all_urls(text)
    for url in urls:
        md_url = markdown_url(url)
        if md_url is None:
            continue
        text = sub(escape(url), repl=md_url, string=text)
    return text


def markdown_url(url, link_text=None) -> Optional[str]:
    """
    Given a url, return it marked down with the domain in the text portion
    :param url:
    :param link_text: Optional, visible text used, otherwise the domain is used.
    :return:
    """
    parsed_url: Url = parse_url(url)
    if not parsed_url:
        return None
    if link_text is not None:
        return f"[{link_text}]({parsed_url.url})"
    return f"[{parsed_url.hostname}]({parsed_url.url})"


def replace_dict_key_value(replace_key, replace_value, search_dict, search_value=None, search_key=None):
    """
    Recursively search through a dictionary for a key and replace it. The search_dict is modified in place, so
    the return is None.
    This also supports embedded lists of dictionaries, but only one level, so a list of lists of dicts is not supported,
      though a list of dicts that contain lists is fine.
    One of either search_key or search_value is required, the dictionary is untouched if neither is passed
    :param search_key: The key in the dictionary to search for
    :param search_value: The value in the dictionary to search for
    :param replace_key: If you want to replace a different key value than you search for, then use this.
    :param replace_value: The new value you want this key to have
    :param search_dict: The dictionary to search through
    :return:
    """
    if not isinstance(search_dict, dict):
        return
    if isinstance(search_dict, dict):
        for k in search_dict.keys():
            if k == search_key or search_dict[k] == search_value:
                if replace_key in search_dict:
                    search_dict[replace_key] = replace_value
                    return

            if isinstance(search_dict[k], list):
                for i in search_dict[k]:
                    if isinstance(i, dict):
                        replace_dict_key_value(search_dict=i,
                                               search_key=search_key,
                                               search_value=search_value,
                                               replace_key=replace_key,
                                               replace_value=replace_value)

            if isinstance(search_dict[k], dict):
                replace_dict_key_value(search_dict=search_dict[k],
                                       search_key=search_key,
                                       search_value=search_value,
                                       replace_key=replace_key,
                                       replace_value=replace_value)


def split_list_to_smaller_lists(items, chunk_size=100) -> Iterator[List]:
    """
    Split a list into lists of smaller chunks. This is a generator, so each iteration yields a list of <chunk_size>
    until there are fewer items than chunksize, the final iteration yields a list of equal or smaller size than the
    chunk size.

    :param list: The list to split.
    :param chunk_size: The maximum size of the returned list
    :return:
    :rtype: Iterable
    """
    split_list = [items[i * chunk_size:(i + 1) * chunk_size]
                  for i in range((len(items) + chunk_size - 1) // chunk_size)]
    for i in split_list:
        yield i
