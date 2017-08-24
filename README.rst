gumiyabot
=========

Standalone Twitch + Bancho IRC bot for handling osu! beatmap requests.

.. image:: https://travis-ci.org/pmrowla/gumiyabot.svg?branch=master
    :target: https://travis-ci.org/pmrowla/gumiyabot

This package is used in `Gumiya`_ and is provided for users that wish to run their own bot instance and customize the bot's functionality.
If you only want a beatmap request bot, but do not need to modify or customize it, you may wish to just use stock `Gumiya`_ instead.

.. _`Gumiya`: https://gumiya.pmrowla.com

:License: MIT

Features
--------
* Support for linking a single twitch channel and single osu! account
* Beatmap requests
* PP info for beatmap requests (requires a Tillerino API key)

Requirements
------------
* `Twitch IRC`_ token - note that if you are using the token for your own Twitch account, the bot will connect to Twitch chat using your own account.
  It is recommended to register a secondary Twitch account for the bot.
* `Bancho (osu!) IRC`_ credentials - note that multiaccounting in osu! is forbidden, and a bannable offense.
  This includes registering a bot-specific osu! account without explicit permission from osu! staff.
  Therefore, it is recommended to run the bot under your own osu! account.
  This will not affect any functionality, you will just receive map requests as in game PMs from yourself.

.. _`Twitch IRC`: https://help.twitch.tv/customer/portal/articles/1302780-twitch-irc
.. _`Bancho (osu!) IRC`: https://osu.ppy.sh/p/irc


Installation
------------
Via pip

    pip install gumiyabot

Usage
-----

1. Generate a new config.ini

    gumiyabot --new-config

2. Edit config.ini as needed (see configuration section below)
3. Run the bot

    gumiyabot config.ini

Configuration
-------------
See `config.ini.example`_ for details on configuration options.

.. _`config.ini.example`: https://github.com/pmrowla/gumiyabot/blog/master/config.ini.example
