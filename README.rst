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
* Python 3.5+
* `Twitch IRC`_ token - note that if you are using the token for your own Twitch account, the bot will connect to Twitch chat using your own account.
  It is recommended to register a secondary Twitch account for the bot.
* `Bancho (osu!) IRC`_ credentials - note that multiaccounting in osu! is forbidden, and a bannable offense.
  This includes registering a bot-specific osu! account without explicit permission from osu! staff.
  Therefore, it is recommended to run the bot under your own osu! account.
  This will not affect any functionality, you will just receive map requests as in game PMs from yourself.
* `osu! API`_ key

.. _`Twitch IRC`: https://help.twitch.tv/customer/portal/articles/1302780-twitch-irc
.. _`Bancho (osu!) IRC`: https://osu.ppy.sh/p/irc
.. _`osu! API`: https://osu.ppy.sh/p/api


Installation
------------
Via pip ::

    pip install gumiyabot

Alternatively, you can clone the source repository and run the bot module directly ::

    pip install -r requirements.txt
    python -m gumiyabot

Running the bot
---------------

1. Generate a new config.ini ::

    gumiyabot --new-config

2. Edit config.ini as needed (see configuration section below)
3. Run the bot ::

    gumiyabot config.ini

Configuration
-------------
See `config.ini.example`_ for details on configuration options.

.. _`config.ini.example`: https://github.com/pmrowla/gumiyabot/blob/master/config.ini.example

Twitch usage
------------

* Map requests can be linked in the format ``<beatmap or mapset URL> +HDDT``.
  The bot accepts beatmap and mapset URLs from both the old and new osu! web sites.
  PP information is dependent on Tillerino.
  When mods are used, the bot output will always the display the modified AR, OD and BPM, but displaying modified star rating is dependent on Tillerino.
  If Tillerino is unavailable, or if Tillerino does not have a calculated PP and difficulty for a certain map + mod combination, the nomod star rating will be used.
* Player stats can be queried with ``!stats <player name>``

Developing
----------

If you need to extend either of the base plugin classes, there are some things to note beforehand:

* Your subclass must have an ``__init__`` method.
  If you do not need to add any custom functionality, it should just call ``super(MyPluginClass, self).__init__()``.
* Any ``irc3.event`` or ``irc3.command`` decorated method from the base plugin class must be overridden in your subclass.
  If you want the base plugin's event or command handling, just call ``super()`` from your subclass.
* For examples, see the `Gumiya IRC plugins`_

.. _`Gumiya IRC plugins`: https://github.com/pmrowla/gumiya/tree/master/twitch_osu_bot/irc
