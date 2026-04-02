import logging

import vimeo

from figure1.configuration import app_settings
from figure1.exceptions import VimeoError, VimeoVideoNotFound

logger = logging.getLogger('figure1.vimeo_client')


class VimeoClient():
    def __init__(self):
        self._client_id = app_settings.vimeo_client_id
        self._token = app_settings.vimeo_token
        self._secret = app_settings.vimeo_secret

        if not self._client_id or not self._token or not self._secret:
            raise VimeoError(msg="Client credentials not found")

    @property
    def _client(self):
        c = vimeo.VimeoClient(key=self._client_id, token=self._token, secret=self._secret)
        if not c:
            raise VimeoError("Unable to get vimeo client")
        return c

    def get_video(self, video_id):
        def _get_files_at_quality(quality, reverse=False):
            return sorted([x for x in data.get('files') if x.get('quality') == quality],
                          key=lambda x: x.get('size'),
                          reverse=reverse)

        r = self._client.get(f'/videos/{video_id}', params={"fields": "files"})

        try:
            data = r.json()
        except ValueError as ve:
            raise VimeoError(msg=f"Failed to decode response {ve}")

        if r.status_code == 400:
            raise VimeoError(msg=data.get('msg'))
        elif r.status_code == 404:
            raise VimeoVideoNotFound(msg=f'Could not find video with ID {video_id}')
        if not data:
            raise VimeoVideoNotFound(msg=f'Could not find video with ID {video_id}')

        hls_files = _get_files_at_quality(quality='hls', reverse=False)
        hd_files = _get_files_at_quality(quality='hd', reverse=False)
        sd_files = _get_files_at_quality(quality='sd', reverse=True)

        if hls_files:
            # HLS file does not include width/height metadata, get data from another file to store aspect ratio
            if not hls_files[0].get('height'):
                if hd_files:
                    hls_files[0]['height'] = hd_files[0].get('height')
                    hls_files[0]['width'] = hd_files[0].get('width')
                elif sd_files:
                    hls_files[0]['height'] = sd_files[0].get('height')
                    hls_files[0]['width'] = sd_files[0].get('width')
            return hls_files[0]

        if hd_files:
            return hd_files[0]

        if sd_files:
            return sd_files[0]

        raise VimeoVideoNotFound(msg=f'Could not find video, video_id={video_id}')
