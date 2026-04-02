import logging
from urllib.parse import parse_qs, unquote, urlparse
from base64 import b64decode
from typing import Optional

from figure1.configuration import app_settings
from figure1.core import managed_session
from figure1.common.models.db import LegacyCase


def _parse_hello_link(hello_link: str) -> Optional[str]:
    """
    Returns the link contained in a legacy 'hello' link.
    """
    query_args = parse_qs(hello_link)
    r = query_args['r'][0]
    try:
        decoded = b64decode(r + '===').decode('utf-8')
        return unquote(decoded)
    except Exception as e:
        logging.info("Failed to decode %s param for hello link:  %s", r, e)
        return None


def _parse_rd_link(rd_link: str) -> str:
    """
    Returns the legacy case ID contained in a legacy 'rd' link.  If no case ID, returns None.
    """
    return rd_link.rsplit('/', 1)[1]


def _is_hello_link(url_path: str) -> bool:
    return url_path.startswith('/hello')


def _is_rd_link(url_path: str) -> bool:
    return url_path.startswith('/rd/images')


@managed_session
def get_pro_case_link(legacy_link: str, session=None):
    default_link = app_settings.app_url + "/rfy"
    parsed_url = urlparse(legacy_link)

    if _is_hello_link(url_path=parsed_url.path):
        res = _parse_hello_link(parsed_url.query)
        if not res:
            logging.info("Failed to parse hello link: %s", parsed_url.query)
            return default_link
        # Hello link should unwrap to a supported case link (RD link).
        # Recursively call to handle the actual redirection
        return get_pro_case_link(legacy_link=res)

    elif _is_rd_link(url_path=parsed_url.path):
        legacy_id = _parse_rd_link(rd_link=parsed_url.path)
        lc = session.query(LegacyCase) \
            .filter(LegacyCase.legacy_id == legacy_id) \
            .one_or_none()
        if not lc:
            logging.info("Could not find legacy case %s", legacy_id)
            return default_link

        return app_settings.app_url + f"/cases/{lc.case_uuid}"

    else:
        logging.info("Unrecognized legacy link:  %s", parsed_url)
        return default_link
