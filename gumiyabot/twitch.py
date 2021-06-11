# -*- coding: utf-8 -*-
"""
twitch_osu_bot Twitch chat irc3 plugin.
"""
from __future__ import unicode_literals

import asyncio
import math
import re

import async_timeout

import irc3
from irc3.plugins.command import command

from osuapi import OsuApi, AHConnector
from osuapi.enums import OsuMod
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

    def join(self, channel):
        self.bot.log.info('[twitch] Trying to join channel {}'.format(channel))
        self.bot.join(channel)

    def part(self, channel):
        self.bot.log.info('[twitch] Leaving channel {}'.format(channel))
        self.bot.part(channel)

    @asyncio.coroutine
    def _get_pp(self, beatmap, mods=OsuMod.NoMod):
        if self.tillerino:
            try:
                with async_timeout.timeout(15):
                    data = yield from self.tillerino.beatmapinfo(beatmap.beatmap_id, mods=mods.value)
                if data:
                    if 'starDiff' in data:
                        # use Tillerino star rating since it factors in mods
                        beatmap.difficultyrating = data['starDiff']
                    pp = {
                        float(acc): pp_val
                        for acc, pp_val in data.get('ppForAcc', {}).items()
                    }
                    if pp:
                        beatmap.pp = pp
                        return pp
            except (HTTPError, asyncio.TimeoutError) as e:
                self.bot.log.debug('[twitch] {}'.format(e))
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
    def _beatmap_msg(self, beatmap, mods=OsuMod.NoMod):
        if mods == OsuMod.NoMod:
            mod_string = ''
        else:
            mod_string = ' +{:s}'.format(mods)
        beatmap = self._apply_mods(beatmap, mods)
        # get pp before generating message since it may update star rating based on
        yield from self._get_pp(beatmap, mods=mods)
        msg = '[{}] {} - {} [{}] (by {}){}, ♫ {:g}, ★ {:.2f}'.format(
            beatmap.approved.name.capitalize(),
            beatmap.artist,
            beatmap.title,
            beatmap.version,
            beatmap.creator,
            mod_string,
            beatmap.bpm,
            round(beatmap.difficultyrating, 2),
        )
        if beatmap.pp:
            msg = ' | '.join([
                msg,
                '95%: {}pp'.format(round(beatmap.pp[.95])),
                '98%: {}pp'.format(round(beatmap.pp[.98])),
                '100%: {}pp'.format(round(beatmap.pp[1.0])),
            ])
        return msg

    @asyncio.coroutine
    def _request_mapset(self, match, mask, target, mods=OsuMod.NoMod, **kwargs):
        try:
            with async_timeout.timeout(15):
                mapset = yield from self.osu.get_beatmaps(
                    beatmapset_id=match.group('mapset_id'),
                    include_converted=0)
            if not mapset:
                return (None, None)
            mapset = sorted(mapset, key=lambda x: x.difficultyrating)
        except (HTTPError, asyncio.TimeoutError) as e:
            self.bot.log.debug('[twitch] {}'.format(e))
            return (None, None)
        try:
            beatmap = self.validate_beatmaps(mapset, **kwargs)[-1]
        except BeatmapValidationError as e:
            return (None, e.reason)
        msg = yield from self._beatmap_msg(beatmap, mods=mods)
        return (beatmap, msg)

    @asyncio.coroutine
    def _request_beatmap(self, match, mask, target, mods=OsuMod.NoMod, **kwargs):
        try:
            with async_timeout.timeout(10):
                beatmaps = yield from self.osu.get_beatmaps(
                    beatmap_id=match.group('beatmap_id'),
                    include_converted=0)
            if not beatmaps:
                return (None, None)
        except (HTTPError, asyncio.TimeoutError) as e:
            self.bot.log.debug('[twitch] {}'.format(e))
            return (None, None)
        try:
            beatmap = self.validate_beatmaps(beatmaps, **kwargs)[0]
        except BeatmapValidationError as e:
            return (None, e.reason)
        msg = yield from self._beatmap_msg(beatmap, mods=mods)
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

    def _bancho_msg(self, mask, beatmap, mods=OsuMod.NoMod):
        m, s = divmod(beatmap.total_length, 60)
        if mods == OsuMod.NoMod:
            mod_string = ''
        else:
            mod_string = ' +{:s}'.format(mods)
        bancho_msg = ' '.join([
            '{} >'.format(mask.nick),
            '[http://osu.ppy.sh/b/{} {} - {} [{}]]{}'.format(
                beatmap.beatmap_id,
                beatmap.artist,
                beatmap.title,
                beatmap.version,
                mod_string,
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

    def _parse_mods(self, mods):
        mod_dict = {
            'NF': OsuMod.NoFail, 'EZ': OsuMod.Easy, 'HD': OsuMod.Hidden, 'HR': OsuMod.HardRock,
            'SD': OsuMod.SuddenDeath, 'DT': OsuMod.DoubleTime, 'RX': OsuMod.Relax, 'HT': OsuMod.HalfTime,
            'NC': OsuMod.Nightcore, 'FL': OsuMod.Flashlight, 'SO': OsuMod.SpunOut, 'AP': OsuMod.Autopilot,
            'PF': OsuMod.Perfect,
        }
        if (len(mods) % 2) != 0:
            mods = mods[:-1]
        mod_flags = OsuMod.NoMod
        for mod in [mods.upper()[i:i + 2] for i in range(0, len(mods), 2)]:
            mod_flags |= mod_dict.get(mod, OsuMod.NoMod)
        return mod_flags

    def _mod_ar(self, ar, ar_mul, speed_mul):
        ar0_ms = 1800
        ar5_ms = 1200
        ar10_ms = 450
        ar_ms_step1 = (ar0_ms - ar5_ms) / 5.0
        ar_ms_step2 = (ar5_ms - ar10_ms) / 5.0

        ar_ms = ar5_ms
        ar *= ar_mul
        if ar < 5.0:
            ar_ms = ar0_ms - ar_ms_step1 * ar
        else:
            ar_ms = ar5_ms - ar_ms_step2 * (ar - 5.0)
        # cap between 0-10 before applying HT/DT
        ar_ms = min(ar0_ms, max(ar10_ms, ar_ms))
        ar_ms /= speed_mul
        if ar_ms > ar5_ms:
            ar = (ar0_ms - ar_ms) / ar_ms_step1
        else:
            ar = 5.0 + (ar5_ms - ar_ms) / ar_ms_step2
        return ar

    def _mod_od(self, od, od_mul, speed_mul):
        od0_ms = 79.5
        od10_ms = 19.5
        od_ms_step = (od0_ms - od10_ms) / 10.0

        od *= od_mul
        od_ms = od0_ms - math.ceil(od_ms_step * od)
        # cap between 0-10 before applying HT/DT
        od_ms = min(od0_ms, max(od10_ms, od_ms))
        od_ms /= speed_mul
        od = (od0_ms - od_ms) / od_ms_step
        return od

    def _apply_mods(self, beatmap, mods=OsuMod.NoMod):
        """Return a copy of beatmap with difficulty modifiers applied"""
        if mods == OsuMod.NoMod:
            return beatmap

        modded = beatmap

        if (OsuMod.DoubleTime | OsuMod.Nightcore) in mods and OsuMod.HalfTime not in mods:
            speed_mul = 1.5
        elif OsuMod.HalfTime in mods and (OsuMod.DoubleTime | OsuMod.Nightcore) not in mods:
            speed_mul = .75
        else:
            speed_mul = 1.0
        modded.bpm *= speed_mul

        if OsuMod.HardRock in mods and OsuMod.Easy not in mods:
            od_ar_hp_mul = 1.4
            cs_mul = 1.3
        elif OsuMod.Easy in mods and OsuMod.HardRock not in mods:
            od_ar_hp_mul = .5
            cs_mul = .5
        else:
            od_ar_hp_mul = 1.0
            cs_mul = 1.0
        modded.diff_approach = self._mod_ar(beatmap.diff_approach, od_ar_hp_mul, speed_mul)
        modded.diff_overall = self._mod_ar(beatmap.diff_overall, od_ar_hp_mul, speed_mul)
        modded.diff_drain = min(10.0, beatmap.diff_drain * od_ar_hp_mul)
        modded.diff_size = min(10.0, beatmap.diff_size * cs_mul)

        return modded

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
            mod_pattern = r'(\S*\s+\+?(?P<mods>[A-Za-z]+))?'
            m = re.search(''.join([pattern, mod_pattern]), data)
            if m:
                if m.group('mods'):
                    mod_flags = self._parse_mods(m.group('mods'))
                else:
                    mod_flags = OsuMod.NoMod
                (beatmap, msg) = yield from callback(m, mask, target, mods=mod_flags, **kwargs)
                if beatmap:
                    bancho_msg = self._bancho_msg(mask, beatmap, mods=mod_flags)
                    if not bancho_target:
                        bancho_target = self.bancho_nick
                    yield from self.bancho_queue.put((bancho_target, bancho_msg))
                if msg:
                    self.bot.privmsg(target, msg)
                break

    @command
    @asyncio.coroutine
    def stats(self, mask, target, args, default_user=None):
        """Check stats for an osu! player

            %%stats [<username>]...
        """
        self.bot.log.debug('[twitch] !stats {}'.format(args))
        if target.is_channel:
            dest = target
        else:
            dest = mask
        osu_username = ' '.join(args.get('<username>')).strip()
        if not osu_username:
            if default_user:
                osu_username = default_user
            else:
                osu_username = self.bancho_nick
        try:
            with async_timeout.timeout(10):
                users = yield from self.osu.get_user(osu_username)
        except (HTTPError, asyncio.TimeoutError) as e:
            self.bot.log.debug('[twitch] {}'.format(e))
            users = []
        if not users:
            self.bot.privmsg(dest, 'Could not find osu! user {}'.format(osu_username))
            return
        user = users[0]
        msg = ' | '.join([
            user.username,
            'PP: {:,} (#{:,})'.format(user.pp_raw, user.pp_rank),
            'Acc: {:g}%'.format(round(user.accuracy, 2)),
            'Score: {:,}'.format(user.total_score),
            'Plays: {:,} (lv{})'.format(user.playcount, math.floor(user.level)),
            'https://osu.ppy.sh/users/{}'.format(user.user_id),
        ])
        self.bot.privmsg(dest, msg)
