#!/usr/bin/env python
import logging
import os
import random

import requests


def get_proxy_session():
    zone = os.environ.get('LUMINATI_PROXY_ZONE')
    password = os.environ.get('LUMINATI_PROXY_PASS')

    s = requests.session()

    # use no proxy if Luminati credentials are not available
    if zone is None or password is None:
        return s

    port = 22225
    session_id = random.random()
    url_base = f"lum-customer-figure1-zone-{zone}-country-us-session-{session_id}"
    super_proxy_url = ('http://%s:%s@zproxy.lum-superproxy.io:%d' % (url_base, password, port))
    super_proxy_url_for_log = ('http://%s:%s@zproxy.lum-superproxy.io:%d' % (url_base, "<password>", port))
    logging.debug(f"Using proxy: {super_proxy_url_for_log}")

    s.headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_2) AppleWebKit/537.36'
                      ' (KHTML, like Gecko) Chrome/79.0.3945.88 Safari/537.36',
        'Accept': "*/*"
    }
    s.proxies.update(
        {
            "http": super_proxy_url,
            "https": super_proxy_url
        })

    return s
