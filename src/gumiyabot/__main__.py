import argparse
import asyncio
import configparser
import os.path
import sys

import irc3

from .bancho import BanchoConnection


async def run(config_file="config.ini", debug=False):
    config = configparser.ConfigParser()
    config.read(config_file)
    if "gumiya" not in config:
        sys.exit("Error: Invalid config, missing [gumiya] section")
    gumiya_config = config["gumiya"]

    loop = asyncio.get_running_loop()
    bancho_queue = asyncio.Queue()

    config_common = {
        "irc3.plugins.command": {
            "hash": "#",
            "cmd": "!",
            "guard": "irc3.plugins.command.mask_based_policy",
        },
        "irc3.plugins.command.masks": {
            "hash": "#",
            "*": "view",
        },
    }
    if debug:
        config_common["debug"] = True

    twitch_config = dict(
        host="irc.chat.twitch.tv",
        port=6667,
        includes=[
            "irc3.plugins.core",
            "irc3.plugins.autocommand",
            "irc3.plugins.command",
            "irc3.plugins.log",
            "gumiyabot.twitch",
        ],
        autocommands=[
            "CAP REQ :twitch.tv/membership",
            "CAP REQ :twitch.tv/commands",
            "CAP REQ :twitch.tv/tags",
        ],
        nick=gumiya_config["twitch_username"],
        password=gumiya_config["twitch_password"],
        osu_client_id=gumiya_config["osu_client_id"],
        osu_client_secret=gumiya_config["osu_client_secret"],
        tillerino_api_key=gumiya_config.get("tillerino_api_key", fallback=""),
        bancho_nick=gumiya_config["bancho_username"],
        twitch_channel=gumiya_config["twitch_channel"],
    )
    twitch_config.update(config_common)

    bancho_config = dict(
        host="irc.ppy.sh",
        port=6667,
        includes=[
            "irc3.plugins.core",
            "irc3.plugins.command",
            "irc3.plugins.log",
            "gumiyabot.bancho",
        ],
        nick=gumiya_config["bancho_username"],
        password=gumiya_config["bancho_password"],
    )
    bancho_config.update(config_common)
    twitch_bot = irc3.IrcBot(loop=loop, bancho_queue=bancho_queue, **twitch_config)
    twitch_bot.run(forever=False)

    bancho_bot = irc3.IrcBot(
        loop=loop,
        bancho_queue=bancho_queue,
        connection=BanchoConnection,
        **bancho_config,
    )
    bancho_bot.run(forever=False)

    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        return


def generate_config(filename="config.ini"):
    if os.path.exists(filename):
        sys.exit(f"Error: {filename} already exists")
    with open(filename, "w") as f:
        f.write(
            """
[gumiya]

# Twitch bot IRC username and password (required)
#
# See https://help.twitch.tv/customer/portal/articles/1302780-twitch-irc for
# details on obtaining a Twitch IRC oauth token
#
# Ex:
#   twitch_username = GumiyaBot
#   twitch_password = oauth:abcd1234
twitch_username =
twitch_password =

# Twitch channel name (required)
#
# This may be different from twitch_username if you are running the bot on
# its own twitch account
#
# Ex:
#   twitch_channel = GumiyaBot
twitch_channel =

# Bancho (osu!) IRC username and password (required)
#
# See https://osu.ppy.sh/p/irc to obtain a Bancho IRC password
#
# Ex:
#   bancho_username = GumiyaBot
#   bancho_password = abcd1234
bancho_username =
bancho_password =

# osu! OAuth client key (required)
#
# See https://osu.ppy.sh/home/account/edit#oauth to configure an osu! OAuth
# client
#
# Ex:
#   osu_client_id = 1234
#   osu_client_secret = abcd1234
osu_client_id =
osu_client_secret =
""".strip()
        )
        print(f"Created {filename}")


def main():
    parser = argparse.ArgumentParser(
        description="Twitch+Bancho IRC bot for handling osu! map requests",
        prog="gumiyabot",
    )
    parser.add_argument(
        "--new-config",
        action="store_true",
        dest="new_config",
        help="Generate a new default config.ini",
    )
    parser.add_argument(
        "config_file",
        nargs="?",
        default="config.ini",
        help=(
            "Path to configuration file, if omitted the bot looks for config.ini"
            " in the current working directory"
        ),
    )
    parser.add_argument(
        "-d",
        "--debug",
        "--verbose",
        action="store_true",
        dest="debug",
        help="Verbose debugging output",
    )
    args = parser.parse_args()
    if args.new_config:
        generate_config()
    else:
        if not os.path.exists(args.config_file):
            parser.error("could not find configuration file")
        asyncio.run(run(config_file=args.config_file, debug=args.debug))


if __name__ == "__main__":
    main()
