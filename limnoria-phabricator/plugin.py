###
# Copyright (c) 2017, elexis
# All rights reserved.
#
#
###

import supybot.utils as utils
from supybot.commands import *
import supybot.plugins as plugins
import supybot.ircmsgs as ircmsgs
import supybot.ircutils as ircutils
import supybot.callbacks as callbacks
import http.client, urllib.parse

import time, datetime
import json
import re
from collections import OrderedDict

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

    def __init__(self, irc):
        self.__parent = super(Phabricator, self)
        self.__parent.__init__(irc)

        callbacks.Plugin.__init__(self, irc)

    # Read public messages (contrary to the function name)
    def doPrivmsg(self, irc, msg):
        if not callbacks.addressed(irc.nick, msg):
            printDifferential(irc, msg.args[0], msg.args[1])

Class = Phabricator

phabricatorHost = "code.wildfiregames.com"
token = "<insertyourtokenhere>"
ignoredUsers = ["Harbormaster", "Vulcan"]
storyLimit = 20
sleepTime = 12

def queryPHIDs(phids):

    if len(phids) == 0:
        return []

    return queryAPI("/api/phid.query", { "phids[]": phids })

def queryAPI(path, params):

    #print("QUERY", path, params)
    params["api.token"] = token

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Charset": "utf-8"
    }

    conn = http.client.HTTPSConnection(phabricatorHost)
    conn.request("GET", path, urllib.parse.urlencode(params, True), headers)
    response = conn.getresponse()

    if (response.status != 200):
        print(response.status, response.reason)
        conn.close()
        return None

    data = response.read()
    conn.close()
    data = json.loads(data.decode("utf-8"))

    if data["error_code"] is not None:
        print(data["error_info"])
        return None

    return data.get("result")

def queryAuthorNames(authorPHIDs):

    results = queryPHIDs(authorPHIDs)

    if results is None:
        return {}

    authorNames = {}
    for authorPHID in results:
        authorNames[authorPHID] = results[authorPHID]["name"]

    return authorNames

def queryObjects(objectPHIDs):

    results = queryPHIDs(objectPHIDs)

    if results is None:
        return []

    objects = {}

    for objectPHID in results:

        obj = results[objectPHID]

        objects[objectPHID] = \
            obj["type"], \
            obj["name"], \
            obj["fullName"][len(obj["name"] + ": "):], \
            obj["uri"]

    return objects

def queryDifferential(IDs):

    return queryAPI("/api/differential.query", {
        "ids[]": IDs
    })

def queryFeed(chronokey, limit):

    results = queryAPI("/api/feed.query", {
        "before": chronokey,
        'limit': limit
    })

    if results is None:
        return []

    stories = []
    authorPHIDs = []
    objectPHIDs = []
    allTransactionPHIDs = []

    for storyPHID in results:

        epoch = int(results[storyPHID]["epoch"])
        cronkey = int(results[storyPHID]["chronologicalKey"])

        authorPHID = results[storyPHID]["authorPHID"]
        if authorPHID not in authorPHIDs:
            authorPHIDs.append(authorPHID)

        objectPHID  = results[storyPHID]["data"]["objectPHID"]
        if objectPHID not in objectPHIDs:
            objectPHIDs.append(objectPHID)

        transactionPHIDs = list(results[storyPHID]["data"]["transactionPHIDs"].keys())
        allTransactionPHIDs += transactionPHIDs

        stories.append((storyPHID, cronkey, epoch, authorPHID, objectPHID, transactionPHIDs))

    return stories, objectPHIDs, authorPHIDs, allTransactionPHIDs

# Enriches the queried stories with author and object names
def queryFeedExtended(chronokey, limit):

    stories, objectPHIDs, authorPHIDs, allTransactionPHIDs = queryFeed(chronokey, limit)
    authorNames = queryAuthorNames(authorPHIDs)
    objects = queryObjects(objectPHIDs)

    # AFAICS we can't do anything with the transaction PHIDs! Not even getting the sub-URL of the modified object
    #transactions = queryObjects(allTransactionPHIDs)

    # Sort by timestamp
    storiesSorted = sorted(stories, key=lambda story: story[1])

    strings = []
    for story in storiesSorted:

        storyPHID, cronkey, epoch, authorPHID, objectPHID, transactionPHIDs = story
        objType, objID, objTitle, objLink = objects[objectPHID]
        authorName = authorNames[authorPHID]

        # Update chronokey
        previous = chronokey
        chronokey = updateChronokey(chronokey, cronkey)
        if previous != chronokey:
            print("New chronokey", chronokey)

        # We already have a bot showing commits
        if objType == "CMIT":
            print("Skipping commit", objID, objTitle)
            continue

        # TODO: display Pastes properly
        if objType == "PSTE":
            print("Skipping paste ", objID, objTitle)
            continue

        if objType != "DREV":
            print("Unexpected object type '" + objType + "'", objectPHID)
            continue

        if authorName in ignoredUsers:
            print("Skipping blocked user", authorName)
            continue

        if False and epoch < time.time():
            print("Skipping story that occured before starting the program:", objTitle, objLink)
            continue

        # TODO: differentiate between creation, update and closing

        strings.append(
            "News from 0 A.D.:" + " " +
            objID + " " +
            "(" + objTitle + ") updated by " + authorName + " " +
            "<" + objLink + ">.")

    return chronokey, strings

# Go forward in history. Use min for backwards.
def updateChronokey(key1, key2):
    return max(key1, key2)

def pollNewStories(chronokey):

    while True:
        print("Polling new stories after", chronokey)

        chronokey, strings = queryFeedExtended(chronokey, storyLimit)

        for strng in strings:
            print(strng)

        print("Sleeping", str(sleepTime), "seconds")
        time.sleep(sleepTime)

# Only display stories that occured after this nonunix timestamp
chronokey = 6376865859769256111
pollNewStories(chronokey)

def printDifferential(irc, channel, txt):

    matches = re.findall(r"\b(D\d*)\b", txt)
    revisions = list(map(lambda d : d[1:], matches))
    revisions = OrderedDict.fromkeys(revisions, True)
    # TODO: keep order
    if len(revisions) == 0:
        return

    results = queryDifferential(revisions)
    for result in results:
        irc.sendMsg(ircmsgs.privmsg(channel, "D" + result["id"] + ": " + result["title"] + " [" + result["statusName"] + "] – <" + result["uri"] + ">"))
