###
# Copyright (c) 2017, elexis
# All rights reserved.
#
#
###

import supybot.utils as utils
from supybot.commands import *
import supybot.plugins as plugins
import supybot.ircutils as ircutils
import supybot.callbacks as callbacks

import http.client, urllib.parse
import time
import json

try:
    from supybot.i18n import PluginInternationalization
    _ = PluginInternationalization('Phabricator')
except ImportError:
    # Placeholder that allows to run the plugin on a bot
    # without the i18n module
    _ = lambda x: x


class Phabricator(callbacks.Plugin):
    """GPL 3.0"""
    threaded = True


Class = Phabricator

phabricatorURL = "code.wildfiregames.com"
token = "<insertyourtokenhere>"

def queryFeed(params):
    queryAPI("/api/feed.query", params)

def queryAPI(path, params):

    headers = {
    }

    conn = http.client.HTTPSConnection(phabricatorURL)
    conn.request("POST", path, urllib.parse.urlencode(params), headers)
    response = conn.getresponse()

    if (response.status != 200):
        print(response.status, response.reason)
        conn.close()
        return

    data = response.read()
    conn.close()

    results = json.loads(data.decode("utf-8")).get("result")

    for result in results:
        print(result)

queryFeed({
    'before': time.time() - 24 * 60 * 60,
    "api.token": token,
    'limit': 2
});
