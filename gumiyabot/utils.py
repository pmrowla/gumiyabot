# -*- coding: utf-8 -*-
#
import aiohttp


class TillerinoApi(object):

    API_BASE = 'https://api.tillerino.org'
    BEATMAP_INFO = '/'.join((API_BASE, 'beatmapinfo'))
    BOT_INFO = '/'.join((API_BASE, 'botinfo'))
    USER_BY_ID = '/'.join((API_BASE, 'userbyid'))

    def __init__(self, key):
        self.key = key
        self.session = aiohttp.ClientSession()

    async def _get(self, url, params={}):
        params.update({'k': self.key})
        async with self.session.get(url, params=params) as r:
            if r.status == 200:
                return r.json()
            else:
                return None

    async def beatmapinfo(self, beatmap_id, mods=0, wait=None):
        """Get beatmapinfo from Tillerino API"""
        params = {'beatmapid': beatmap_id, 'mods': mods}
        if wait:
            params['wait'] = wait
        return self._get(self.BEATMAP_INFO, params=params)
