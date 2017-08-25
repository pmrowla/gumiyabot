# -*- coding: utf-8 -*-
"""
twitch_osu_bot Twitch chat irc3 plugin.
"""
from __future__ import unicode_literals

import asyncio
import re

import irc3

from osuapi import OsuApi, AHConnector
from osuapi.errors import HTTPError

from .utils import TillerinoApi


class BeatmapValidationError(Exception):

    def __init__(self, reason):
        self.reason = reason


@irc3.plugin
class BaseTwitchPlugin:

    def __init__(self, bot):
        self.bot = bot
        self.bancho_queue = self.bot.config.get('bancho_queue')
        self.bancho_nick = self.bot.config.get('bancho_nick')
        self.osu = OsuApi(
            self.bot.config.get('osu_api_key'),
            connector=AHConnector())
        tillerino_key = self.bot.config.get('tillerino_api_key')
        if tillerino_key:
            self.tillerino = TillerinoApi(tillerino_key)
        else:
            self.tillerino = None
        self.twitch_channel = self.bot.config.get('twitch_channel')
        if not self.twitch_channel.startswith('#'):
            self.twitch_channel = '#{}'.format(self.twitch_channel)

    @irc3.event(irc3.rfc.CONNECTED)
    def connected(self, **kw):
        self.bot.log.info('[twitch] Connected to twitch as {}'.format(self.bot.nick))
        self.join(self.twitch_channel)

    @asyncio.coroutine
    def _get_pp(self, beatmap):
        if self.tillerino:
            data = yield from self.tillerino.beatmapinfo(beatmap.beatmap_id)
            if data:
                pp = {}
                for entry in data['ppForAcc']['entry']:
                    pp[float(entry['key'])] = float(entry['value'])
                if pp:
                    beatmap.pp = pp
                    return pp
        beatmap.pp = None
        return None

    def validate_beatmaps(self, beatmaps, **kwargs):
        """Return subset of maps in beatmaps that pass validation criteria

        Raises:
            BeatmapValidationError if a map fails validation

        Override this method in subclasses as needed
        """
        return beatmaps

    @asyncio.coroutine
    def _beatmap_msg(self, beatmap):
        msg = '[{}] {} - {} [{}] (by {}), ♫ {:g}, ★ {:.2f}'.format(
            beatmap.approved.name.capitalize(),
            beatmap.artist,
            beatmap.title,
            beatmap.version,
            beatmap.creator,
            beatmap.bpm,
            round(beatmap.difficultyrating, 2),
        )
        pp = yield from self._get_pp(beatmap)
        if pp:
            msg = ' | '.join([
                msg,
                '95%: {}pp'.format(round(pp[.95])),
                '98%: {}pp'.format(round(pp[.98])),
                '100%: {}pp'.format(round(pp[1.0])),
            ])
        return msg

    @asyncio.coroutine
    def _request_mapset(self, match, mask, target, **kwargs):
        try:
            mapset = yield from self.osu.get_beatmaps(
                beatmapset_id=match.group('mapset_id'),
                include_converted=0)
            if not mapset:
                return (None, None)
            mapset = sorted(mapset, key=lambda x: x.difficultyrating)
        except HTTPError:
            return (None, None)
        try:
            beatmap = self.validate_beatmaps(mapset, **kwargs)[-1]
        except BeatmapValidationError as e:
            return (None, e.reason)
        msg = yield from self._beatmap_msg(beatmap)
        return (beatmap, msg)

    @asyncio.coroutine
    def _request_beatmap(self, match, mask, target, **kwargs):
        try:
            beatmaps = yield from self.osu.get_beatmaps(
                beatmap_id=match.group('beatmap_id'),
                include_converted=0)
            if not beatmaps:
                return (None, None)
        except HTTPError as e:
            self.bot.log.debug('[twitch] {}'.format(e))
            return (None, None)
        try:
            beatmap = self.validate_beatmaps(beatmaps, **kwargs)[0]
        except BeatmapValidationError as e:
            return (None, e.reason)
        msg = yield from self._beatmap_msg(beatmap)
        return (beatmap, msg)

    def _badge_list(self, badges):
        """Parse twitch badge ircv3 tags into a list"""
        b_list = []
        for x in badges.split(','):
            (badge, version) = x.split('/', 1)
            b_list.append(badge)
        return b_list

    def _is_sub(self, privmsg_tags):
        """Check if twitch irc3 tags include sub (or mod) badge"""
        badges = self._badge_list(privmsg_tags.get('badges', ''))
        if any(b in badges for b in ['broadcaster', 'moderator', 'subscriber']):
            return True
        elif privmsg_tags.get('mod', 0) == 1:
            return True
        elif privmsg_tags.get('subscriber', 0) == 1:
            return True

    @asyncio.coroutine
    def _request_beatmapsets(self, match, mask, target, **kwargs):
        """Handle "new" osu web style beatmapsets links"""
        if match.group('beatmap_id'):
            return self._request_beatmap(match, mask, target, **kwargs)
        else:
            return self._request_mapset(match, mask, target, **kwargs)

    def _bancho_msg(self, mask, beatmap):
        m, s = divmod(beatmap.total_length, 60)
        bancho_msg = ' '.join([
            '{} >'.format(mask.nick),
            '[http://osu.ppy.sh/b/{} {} - {} [{}]]'.format(
                beatmap.beatmap_id,
                beatmap.artist,
                beatmap.title,
                beatmap.version,
            ),
            '{}:{:02d} ★ {:.2f} ♫ {:g} AR{:g} OD{:g}'.format(
                m, s,
                round(beatmap.difficultyrating, 2),
                beatmap.bpm,
                round(beatmap.diff_approach, 1),
                round(beatmap.diff_overall, 1),
            ),
        ])
        if beatmap.pp:
            bancho_msg = ' | '.join([
                bancho_msg,
                '95%: {}pp'.format(round(beatmap.pp[.95])),
                '98%: {}pp'.format(round(beatmap.pp[.98])),
                '100%: {}pp'.format(round(beatmap.pp[1.0])),
            ])
        return bancho_msg

    @irc3.event(irc3.rfc.PRIVMSG)
    @asyncio.coroutine
    def request_beatmap(self, tags=None, mask=None, target=None, data=None, bancho_target=None, **kwargs):
        if not target.is_channel or not data:
            return
        patterns = [
            (r'https?://osu\.ppy\.sh/b/(?P<beatmap_id>\d+)',
             self._request_beatmap),
            (r'https?://osu\.ppy\.sh/s/(?P<mapset_id>\d+)',
             self._request_mapset),
            (r'https?://osu\.ppy\.sh/beatmapsets/(?P<mapset_id>\d+)(#(?P<mode>\w+))?(/(?P<beatmap_id>\d+))?',
             self._request_beatmapsets),
        ]
        for pattern, callback in patterns:
            m = re.match(pattern, data)
            if m:
                (beatmap, msg) = yield from callback(m, mask, target, **kwargs)
                if beatmap:
                    bancho_msg = self._bancho_msg(mask, beatmap)
                    if not bancho_target:
                        bancho_target = self.bancho_nick
                    yield from self.bancho_queue.put((bancho_target, bancho_msg))
                if msg:
                    self.bot.privmsg(target, msg)
                break

    def join(self, channel):
        self.bot.log.info('[twitch] Trying to join channel {}'.format(channel))
        self.bot.join(channel)

    def part(self, channel):
        self.bot.log.info('[twitch] Leaving channel {}'.format(channel))
        self.bot.part(channel)
