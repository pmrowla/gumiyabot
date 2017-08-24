# -*- coding: utf-8 -*-
"""
Gumiya Bancho (osu!) irc3 plugin.
"""
import asyncio

import irc3


# Bancho does not comply with the IRC spec (thanks peppy) so we need to account
# for that or else the irc3 module will not read any data
class BanchoConnection(irc3.IrcConnection):
    """asyncio protocol to handle Bancho connections"""

    def data_received(self, data):
        """Handle data received from Bancho.

        Bancho does not send trailing carriage returns at the end of IRC
        commands (i.e. it ends a command with \n instead of \r\n).
        """
        if not data.endswith(b'\r\n'):
            data = data.rstrip(b'\n') + b'\r\n'
        return super(BanchoConnection, self).data_received(data)


@irc3.plugin
class BaseBanchoPlugin:

    def __init__(self, bot):
        self.bot = bot
        self.bancho_queue = self.bot.config.get('bancho_queue')
        asyncio.ensure_future(self.get_bancho_msg())

    @irc3.event(irc3.rfc.CONNECTED)
    def connected(self, **kw):
        self.bot.log.info('[bancho] Connected to bancho as {}'.format(self.bot.nick))

    @asyncio.coroutine
    def get_bancho_msg(self):
        while True:
            (target, msg) = yield from self.bancho_queue.get()
            self.bot.privmsg(target, msg)
