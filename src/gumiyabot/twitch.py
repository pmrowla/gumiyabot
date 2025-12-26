"""
twitch_osu_bot Twitch chat irc3 plugin.
"""

import asyncio
import math
import re

import aiohttp

import irc3
from irc3.plugins.command import command

from ossapi import (
    APIException,
    Beatmap,
    Beatmapset,
    BeatmapsetCompact,
    Mod,
    OssapiAsync,
)
from ossapi.models import BeatmapDifficultyAttributes

from .utils import TillerinoApi


class BeatmapValidationError(Exception):
    def __init__(self, reason):
        self.reason = reason


@irc3.plugin
class BaseTwitchPlugin:
    def __init__(self, bot):
        self.bot = bot
        self.bancho_queue = self.bot.config.get("bancho_queue")
        self.bancho_nick = self.bot.config.get("bancho_nick")
        self.osu = OssapiAsync(
            self.bot.config.get("osu_client_id"),
            self.bot.config.get("osu_client_secret"),
        )
        tillerino_key = self.bot.config.get("tillerino_api_key")
        if tillerino_key:
            self.tillerino = TillerinoApi(tillerino_key)
        else:
            self.tillerino = None
        self.twitch_channel = self.bot.config.get("twitch_channel")
        if not self.twitch_channel.startswith("#"):
            self.twitch_channel = f"#{self.twitch_channel}"

    @irc3.event(irc3.rfc.CONNECTED)
    def connected(self, **kw):
        self.bot.log.info(f"[twitch] Connected to twitch as {self.bot.nick}")
        self.join(self.twitch_channel)

    def join(self, channel):
        self.bot.log.info(f"[twitch] Trying to join channel {channel}")
        self.bot.join(channel)

    def part(self, channel):
        self.bot.log.info(f"[twitch] Leaving channel {channel}")
        self.bot.part(channel)

    async def _get_pp(self, beatmap: Beatmap, mods: Mod = Mod.NM):
        if self.tillerino:
            try:
                async with asyncio.timeout(15):
                    data = await self.tillerino.beatmapinfo(beatmap.id, mods=mods.value)
                if data:
                    pp = {
                        float(acc): pp_val
                        for acc, pp_val in data.get("ppForAcc", {}).items()
                    }
                    if pp:
                        beatmap.pp = pp
                        return pp
            except (aiohttp.ClientError, APIException, TimeoutError) as e:
                self.bot.log.debug(f"[twitch] {e}")
        beatmap.pp = None
        return None

    def validate_beatmaps(
        self,
        beatmaps: list[tuple[Beatmap, BeatmapDifficultyAttributes]],
        mapset: Beatmapset | BeatmapsetCompact,
        **kwargs,
    ) -> list[tuple[Beatmap, BeatmapDifficultyAttributes]]:
        """Return subset of maps in beatmaps that pass validation criteria

        Raises:
            BeatmapValidationError if a map fails validation

        Override this method in subclasses as needed
        """
        return beatmaps

    async def _beatmap_msg(
        self,
        beatmap: Beatmap,
        diff: BeatmapDifficultyAttributes | None = None,
        mods: Mod = Mod.NM,
    ) -> str:
        mapset = await beatmap.beatmapset()
        # get pp before generating message since it may update star rating based on
        await self._get_pp(beatmap, mods=mods)
        msg = "[{}] {} - {} [{}] (by {}){}, ♫ {:g}".format(
            beatmap.status.name.capitalize(),
            mapset.artist,
            mapset.title,
            beatmap.version,
            mapset.creator,
            str(mods),
            beatmap.bpm,
        )
        if diff:
            msg = ", ".join([msg, f"★ {diff.star_rating:.2f}"])
        if beatmap.pp:
            msg = " | ".join(
                [
                    msg,
                    f"95%: {round(beatmap.pp[0.95])}pp",
                    f"98%: {round(beatmap.pp[0.98])}pp",
                    f"100%: {round(beatmap.pp[1.0])}pp",
                ]
            )
        return msg

    async def _request_mapset(self, match, mask, target, mods: Mod = Mod.NM, **kwargs):
        try:
            async with asyncio.timeout(15):
                mapset = await self.osu.beatmapset(
                    beatmapset_id=match.group("mapset_id")
                )
            if not mapset:
                return (None, None, None)
        except (aiohttp.ClientError, APIException, TimeoutError) as e:
            self.bot.log.debug(f"[twitch] {e}")
            return (None, None, None)
        try:
            async with asyncio.timeout(30):
                diffs = [
                    result.attributes if not isinstance(result, BaseException) else None
                    for result in await asyncio.gather(
                        *(
                            self.osu.beatmap_attributes(
                                beatmap_id=beatmap.id, mods=mods
                            )
                            for beatmap in mapset.beatmaps
                        ),
                        return_exceptions=True,
                    )
                ]
        except (aiohttp.ClientError, APIException, TimeoutError) as e:
            self.bot.log.debug(f"[twitch] {e}")
            return (None, None, None)
        beatmaps = sorted(
            zip(
                (self._apply_mods(beatmap, mods=mods) for beatmap in mapset.beatmaps),
                diffs,
            ),
            key=lambda x: x[1].star_rating if x[1] is not None else 0,
        )
        try:
            beatmap, diff = self.validate_beatmaps(beatmaps, mapset=mapset, **kwargs)[
                -1
            ]
        except BeatmapValidationError as e:
            return (None, None, e.reason)
        msg = await self._beatmap_msg(beatmap, diff=diff, mods=mods)
        return (beatmap, diff, msg)

    async def _request_beatmap(self, match, mask, target, mods=Mod.NM, **kwargs):
        try:
            async with asyncio.timeout(10):
                beatmap = await self.osu.beatmap(beatmap_id=match.group("beatmap_id"))
            if not beatmap:
                return (None, None, None)
        except (aiohttp.ClientError, APIException, TimeoutError) as e:
            self.bot.log.debug(f"[twitch] {e}")
            return (None, None, None)
        beatmap = self._apply_mods(beatmap, mods=mods)
        try:
            async with asyncio.timeout(10):
                result = await self.osu.beatmap_attributes(
                    beatmap_id=beatmap.id, mods=mods
                )
                diff = result.attributes if result else None
        except (aiohttp.ClientError, APIException, TimeoutError) as e:
            self.bot.log.debug(f"[twitch] {e}")
            return (None, None, None)
        try:
            beatmap, diff = self.validate_beatmaps(
                [(beatmap, diff)], mapset=await beatmap.mapset(), **kwargs
            )[0]
        except BeatmapValidationError as e:
            return (None, None, e.reason)
        msg = await self._beatmap_msg(beatmap, diff=diff, mods=mods)
        return (beatmap, diff, msg)

    def _badge_list(self, badges):
        """Parse twitch badge ircv3 tags into a list"""
        b_list = []
        if badges:
            for x in badges.split(","):
                (badge, version) = x.split("/", 1)
                b_list.append(badge)
        return b_list

    def _is_sub(self, privmsg_tags):
        """Check if twitch irc3 tags include sub (or mod) badge"""
        badges = self._badge_list(privmsg_tags.get("badges", ""))
        if any(b in badges for b in ["broadcaster", "moderator", "subscriber"]):
            return True
        elif privmsg_tags.get("mod", 0) == 1:
            return True
        elif privmsg_tags.get("subscriber", 0) == 1:
            return True

    async def _request_beatmapsets(self, match, mask, target, **kwargs):
        """Handle "new" osu web style beatmapsets links"""
        if match.group("beatmap_id"):
            return await self._request_beatmap(match, mask, target, **kwargs)
        else:
            return await self._request_mapset(match, mask, target, **kwargs)

    async def _bancho_msg(
        self,
        mask,
        beatmap: Beatmap,
        diff: BeatmapDifficultyAttributes | None = None,
        mods: Mod = Mod.NM,
    ):
        bpm, total_length = self._get_speed_mod(beatmap, mods=mods)
        m, s = divmod(total_length, 60)
        mapset = await beatmap.beatmapset()
        bancho_msg = " ".join(
            [
                f"{mask.nick} >",
                "[http://osu.ppy.sh/b/{} {} - {} [{}]] {}".format(
                    beatmap.id,
                    mapset.artist,
                    mapset.title,
                    beatmap.version,
                    str(mods),
                ),
                f"{m}:{s:02d} ♫ {bpm:g}",
            ]
        )
        if diff:
            bancho_msg = " ".join(
                [
                    bancho_msg,
                    f"★ {diff.star_rating:.2f} CS{round(beatmap.cs, 1):g} AR{round(beatmap.ar, 1):g} OD{round(beatmap.accuracy, 1):g}",
                ]
            )
        if beatmap.pp:
            bancho_msg = " | ".join(
                [
                    bancho_msg,
                    f"95%: {round(beatmap.pp[0.95])}pp",
                    f"98%: {round(beatmap.pp[0.98])}pp",
                    f"100%: {round(beatmap.pp[1.0])}pp",
                ]
            )
        return bancho_msg

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

    def _apply_mods(self, beatmap: Beatmap, mods=Mod.NM) -> Beatmap:
        """Apply mods to beatmap with difficulty attributes."""
        if mods == Mod.NM:
            return beatmap

        if (Mod.DT in mods or Mod.NC in mods) and Mod.HT not in mods:
            speed_mul = 1.5
        elif Mod.HT in mods and Mod.DT not in mods and Mod.NC not in mods:
            speed_mul = 0.75
        else:
            speed_mul = 1.0
        beatmap.bpm *= speed_mul
        beatmap.total_length = round(beatmap.total_length / speed_mul)

        if Mod.HR in mods and Mod.EZ not in mods:
            od_ar_hp_mul = 1.4
            cs_mul = 1.3
        elif Mod.EZ in mods and Mod.HR not in mods:
            od_ar_hp_mul = 0.5
            cs_mul = 0.5
        else:
            od_ar_hp_mul = 1.0
            cs_mul = 1.0
        beatmap.ar = self._mod_ar(beatmap.ar, od_ar_hp_mul, speed_mul)
        beatmap.accuracy = self._mod_od(beatmap.accuracy, od_ar_hp_mul, speed_mul)
        beatmap.drain = min(10.0, beatmap.drain * od_ar_hp_mul)
        beatmap.cs = min(10.0, beatmap.cs * cs_mul)

        return beatmap

    def _get_speed_mod(self, beatmap: Beatmap, mods: Mod = Mod.NM) -> tuple[float, int]:
        """Return modded (bpm, total_length)."""
        if (Mod.DT in mods or Mod.NC in mods) and Mod.HT not in mods:
            speed_mul = 1.5
        elif Mod.HT in mods and not (Mod.DT in mods or Mod.NC in mods):
            speed_mul = 0.75
        else:
            speed_mul = 1.0
        return beatmap.bpm * speed_mul, round(beatmap.total_length / speed_mul)

    @irc3.event(irc3.rfc.PRIVMSG)
    async def request_beatmap(
        self, tags=None, mask=None, target=None, data=None, bancho_target=None, **kwargs
    ):
        if not target.is_channel or not data:
            return
        patterns = [
            (r"https?://osu\.ppy\.sh/b/(?P<beatmap_id>\d+)", self._request_beatmap),
            (r"https?://osu\.ppy\.sh/s/(?P<mapset_id>\d+)", self._request_mapset),
            (
                r"https?://osu\.ppy\.sh/beatmapsets/(?P<mapset_id>\d+)(#(?P<mode>[a-z]+))?(/(?P<beatmap_id>\d+))?",
                self._request_beatmapsets,
            ),
        ]
        for pattern, callback in patterns:
            mod_pattern = r"(/?\s*\+?(?P<mods>[A-Za-z]+))?"
            m = re.search("".join([pattern, mod_pattern]), data)
            if m:
                if m.group("mods"):
                    try:
                        mod_flags = Mod(m.group("mods").upper())
                    except ValueError:
                        mod_flags = Mod.NM
                else:
                    mod_flags = Mod.NM
                beatmap, diff, msg = await callback(
                    m, mask, target, mods=mod_flags, **kwargs
                )
                if beatmap:
                    bancho_msg = await self._bancho_msg(
                        mask, beatmap, diff=diff, mods=mod_flags
                    )
                    if not bancho_target:
                        bancho_target = self.bancho_nick
                    await self.bancho_queue.put((bancho_target, bancho_msg))
                if msg:
                    self.bot.privmsg(target, msg)
                break

    @command
    async def stats(self, mask, target, args, default_user=None):
        """Check stats for an osu! player

        %%stats [<username>]...
        """
        self.bot.log.debug(f"[twitch] !stats {args}")
        if target.is_channel:
            dest = target
        else:
            dest = mask
        osu_username = " ".join(args.get("<username>")).strip()
        if not osu_username:
            if default_user:
                osu_username = default_user
            else:
                osu_username = self.bancho_nick
        try:
            async with asyncio.timeout(10):
                user = await self.osu.user(osu_username)
        except (aiohttp.ClientError, APIException, TimeoutError) as e:
            self.bot.log.debug(f"[twitch] {e}")
        if not user:
            self.bot.privmsg(dest, f"Could not find osu! user {osu_username}")
            return
        rank = (
            f"#{user.statistics.global_rank:,}"
            if user.statistics.global_rank is not None
            else "unranked"
        )
        msg = " | ".join(
            [
                user.username,
                f"PP: {user.statistics.pp:,} ({rank})",
                f"Acc: {user.statistics.hit_accuracy:.2f}%",
                f"Score: {user.statistics.total_score:,}",
                f"Plays: {user.statistics.play_count:,} (lv{user.statistics.level.current})",
                f"https://osu.ppy.sh/users/{user.id}",
            ]
        )
        self.bot.privmsg(dest, msg)
