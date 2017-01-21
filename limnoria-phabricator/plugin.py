###
# Copyright (c) 2017, elexis
# All rights reserved.
###

import supybot.utils as utils
from supybot.commands import *
import supybot.plugins as plugins
import supybot.ircmsgs as ircmsgs
import supybot.ircutils as ircutils
import supybot.callbacks as callbacks
import http.client, urllib.parse

import time
import threading
import re
import os.path
from collections import OrderedDict

try:
    from supybot.i18n import PluginInternationalization
    _ = PluginInternationalization('Phabricator')
except ImportError:
    # Placeholder that allows to run the plugin on a bot
    # without the i18n module
    _ = lambda x: x

# This class instructs the IRC bot to post chat messages about
# recently updated Phabricator URLs and
# responds with a title and URL if a differential or revision ID was posted
class Phabricator(callbacks.Plugin):

    def __init__(self, irc):
        self.__parent = super(Phabricator, self)
        self.__parent.__init__(irc)
        callbacks.Plugin.__init__(self, irc)

        self.printer = PhabricatorPrinter(
            self.registryValue("phabricatorURL"),
            self.registryValue("phabricatorToken"),
            self.registryValue("storyLimit"),
            self.registryValue("sleepTime"),
            self.registryValue("newsPrefix"),
            self.registryValue("ignoredUsers"),
            self.registryValue("notifyCommit"),
            self.registryValue("notifyRetitle"),
            self.registryValue("chronokeyFile"))

        # Notify about recent phabricator stories
        thread = threading.Thread(target=self.printer.pollNewStories, args=(irc,), daemon=True)
        thread.start()

    # Respond to channel and private messages
    def doPrivmsg(self, irc, msg):
        self.printer.printDifferentials(irc, msg.args[0], msg.args[1])
        self.printer.printRevisions(irc, msg.args[0], msg.args[1])
        self.printer.printPastes(irc, msg.args[0], msg.args[1])

# Constructs human-readable strings and optionally posts them to IRC.
# Allows testing of the querying and printing without actually connecting to IRC.
class PhabricatorPrinter:

    def __init__(self, phabricatorURL, token, storyLimit, sleepTime, newsPrefix,
                 ignoredUsers, notifyCommit, notifyRetitle, chronokeyFile=None, chronokey=None):

        self.conduitAPI = conduitAPI(phabricatorURL, token)
        self.storyLimit = storyLimit
        self.sleepTime = sleepTime
        self.newsPrefix = newsPrefix
        self.ignoredUsers = ignoredUsers
        self.notifyCommit = notifyCommit
        self.notifyRetitle = notifyRetitle
        self.chronokeyFile = chronokeyFile
        self.chronokey = chronokey

    def bold(self, irc, txt):
        if not irc:
            return txt
        return ircutils.bold(txt)

    # Adds invisible whitespace between characters to
    # avoid people pinging themselves with updates
    def obscureAuthorName(self, authorName):
        return u"\u200B".join(list(authorName))

    # Display the title and URL of all differential IDs appearing in the text (D123)
    # Don't obscure the nickname, so that developers are pinged
    def printDifferentials(self, irc, channel, txt):

        matches = re.findall(r"\b(D\d*)\b", txt)
        revisions = list(map(lambda d : d[1:], matches))
        revisions = OrderedDict.fromkeys(revisions, True)

        if revisions is None or len(revisions) == 0:
            return

        results = self.conduitAPI.queryDifferentials(revisions)

        for result in results:
            strng = self.bold(irc, "D" + result["id"]) + ": " + \
                result["title"] + " [" + result["statusName"] + "] – " + \
                "<" + result["uri"] + ">"

            if irc:
                irc.queueMsg(ircmsgs.privmsg(channel, strng))
            else:
                print(strng)

    # Display the title and URL of all differential IDs appearing in the text (D123)
    def printRevisions(self, irc, channel, txt):

        commitIDs = re.findall(r"\b(rP\d*)\b", txt)
        commitIDs = list(map(lambda d : d[2:], commitIDs))
        commitIDs = OrderedDict.fromkeys(commitIDs, True)

        if commitIDs is None or len(commitIDs) == 0:
            return

        results = self.conduitAPI.queryCommitsByID(commitIDs).get("data")

        if results is None:
            return

        for commitID in commitIDs:
            for commitPHID in results:

                result = results[commitPHID]
                if result["id"] != commitID:
                    continue

                strng = \
                    self.bold(irc, "rP" + result["id"] + ".") + " " + \
                    self.bold(irc, "Author:") + " " + result["authorName"] + ". " + \
                    self.bold(irc, "Commit message:") + " " + result["summary"] + " " + \
                    "<" + result["uri"] + ">"

                if irc:
                    irc.queueMsg(ircmsgs.privmsg(channel, strng))
                else:
                    print(strng)

    # Display the title and URL of all differential IDs appearing in the text (D123)
    def printPastes(self, irc, channel, txt):

        pasteIDs = re.findall(r"\b(P\d*)\b", txt)
        pasteIDs = list(map(lambda d : d[1:], pasteIDs))
        pasteIDs = OrderedDict.fromkeys(pasteIDs, True)

        if pasteIDs is None or len(pasteIDs) == 0:
            return

        results = self.conduitAPI.queryPastesByID(pasteIDs)

        if results is None:
            return

        authorPHIDs = []
        for pastePHID in results:
            authorPHID = results[pastePHID]["authorPHID"]
            if authorPHID not in authorPHIDs:
                authorPHIDs.append(authorPHID)

        authorNames = self.conduitAPI.queryAuthorNames(authorPHIDs)

        for pasteID in pasteIDs:
            for pastePHID in results:

                result = results[pastePHID]
                if result["id"] != pasteID:
                    continue

                strng = \
                    self.bold(irc, "Paste P" + result["id"] + ".") + " " + \
                    self.bold(irc, "Author:") + " " + authorNames[result["authorPHID"]] + ". " + \
                    self.bold(irc, "Title:") + " " + result["title"] + " " + \
                    "<" + result["uri"] + ">"

                if irc:
                    irc.queueMsg(ircmsgs.privmsg(channel, strng))
                else:
                    print(strng)

    # Running in a separate thread, printing most recent updates on phabricator
    def pollNewStories(self, irc):

        chronokey = self.loadChronokey() if self.chronokey is None else self.chronokey

        while True:
            try:
                print("Pulling Stories")
                chronokey, strings = self.queryFeedExtended(irc, chronokey, self.storyLimit)

                for strng in strings:
                    print(strng)
                    if irc:
                        for (channel, c) in irc.state.channels.items():
                            irc.queueMsg(ircmsgs.privmsg(channel, strng))

                time.sleep(self.sleepTime)
            except KeyboardInterrupt:
                return
            except:
                raise

    # Pulls some stories on phabricator that are more recent than the chronokey.
    # Fetches the refered authors and differentials.
    # Returns an array of human-readable strings to be posted in irc and the updated chronokey.
    def queryFeedExtended(self, irc, chronokey, limit):

        stories, objectPHIDs, authorPHIDs = self.conduitAPI.queryFeed(chronokey, limit)
        authorNames = self.conduitAPI.queryAuthorNames(authorPHIDs)
        objects = self.conduitAPI.queryObjects(objectPHIDs)

        # We can't do anything with the transaction PHIDs! Not even getting the sub-URL of the modified object
        # https://secure.phabricator.com/T5873
        # transactions = queryObjects(allTransactionPHIDs)

        # Sort by timestamp
        storiesSorted = sorted(stories, key=lambda story: story[1])
        strings = []
        for story in storiesSorted:

            storyPHID, cronkey, epoch, authorPHID, objectPHID, text = story
            objType, objID, objTitle, objLink = objects[objectPHID]
            authorName = authorNames[authorPHID]

            # Go forward in history. Use min to go backwards.
            previous = chronokey
            chronokey = max(chronokey, cronkey)
            if self.chronokeyFile and previous != chronokey:
                self.saveChronokey(chronokey)

            if self.ignoredUsers is not None and authorName in self.ignoredUsers:
                print("Skipping blocked user", authorName)
                continue

            if authorPHID == "PHID-APPS-PhabricatorDiffusionApplication":
                print("Fallback: Commit without phabricator account: [" + text + "]")
                authorName = self.conduitAPI.queryCommitsByID(objID[len("rP"):]).get("data")[objectPHID]["author"]

            # clumsy parsing of the action, since transactionPHIDs can't be queried yet
            action = text[len(authorName + " "):-len(" " + objID + self.titleSeparator(objType) + objTitle + ".")]

            if objType == "Differential Revision":
                if action == "retitled" and not self.notifyRetitle:
                    print("Skipping retitle of", objID)
                    continue

                # contrary to other actions, this one extends the string by the added reviewer
                if action.startswith("added a reviewer"):
                    print("Skipping unsupported adding of reviewers [" + objID + "]")
                    continue

                strings.append(self.newsPrefix + " " + \
                    self.obscureAuthorName(authorName) + " " + \
                    action + " " + \
                    self.bold(irc, objID) + " (" + objTitle + ") " + \
                    "<" + objLink + ">.")
                continue

            if objType == "Diffusion Commit":
                if action == "committed" and not self.notifyCommit:
                    print("Skipping commit", objID, objTitle)
                    continue

                strings.append(self.newsPrefix + " " + \
                    self.obscureAuthorName(authorName) + " " + \
                    action + " " + \
                    self.bold(irc, objID) + " (" + objTitle + ") " + \
                    "<" + objLink + ">.")
                continue

            if objType == "Paste":
                strings.append(self.newsPrefix + " " + \
                    self.obscureAuthorName(authorName) + " " + \
                    action + " " + \
                    self.bold(irc, objID) + " (" + objTitle + ") " + \
                    "<" + objLink + ">.")
                continue

            print("Unexpected object type '" + objType + "'", objectPHID)

        return chronokey, strings

    def titleSeparator(self, objType):
        if objType == "Paste":
            return " "
        return ": "

    # Remember the chronological entry of the most recently
    # processed or printed update on phabricator
    def loadChronokey(self):

        if not os.path.isfile(self.chronokeyFile):
            print(self.chronokeyFile, "not found, starting at 0")
            return 0

        return int(open(self.chronokeyFile, 'r').read())

    # Save the state immediately after processing a message,
    # so that we don't lose the state after a crash
    def saveChronokey(self, chronokey):
        print("Saving chronokey", chronokey)
        text_file = open(self.chronokeyFile, "w")
        text_file.write(str(chronokey) + "\n")
        text_file.close()


# Provides some abstraction and parsing of the RESTful Phabricator API
import datetime
import json
class conduitAPI:

    def __init__(self, phabricatorURL, token):
        self.token = token
        self.phabricatorURL = phabricatorURL

    # Send an HTTPS GET request to the phabricator location and
    # return the interpreted JSON object
    def queryAPI(self, path, params):

        if self.phabricatorURL is None or self.phabricatorURL == "":
            print("Error: You must configure the Phabricator location!")
            return None

        if self.token is None or self.token == "":
            print("Error: You must configure a Phabricator API token!")
            return None

        params["api.token"] = self.token

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Charset": "utf-8"
        }

        conn = http.client.HTTPSConnection(self.phabricatorURL)
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

    # Return some information about arbitrary objects, like
    # differntials, users, commits, transactions, ...
    def queryPHIDs(self, phids):

        if len(phids) == 0:
            return []

        return self.queryAPI("/api/phid.query", { "phids[]": phids })

    # Retrieve account names of the given author URLs
    def queryAuthorNames(self, authorPHIDs):

        results = self.queryPHIDs(authorPHIDs)

        if results is None:
            return {}

        authorNames = {}
        for authorPHID in results:
            authorNames[authorPHID] = results[authorPHID]["name"]

        return authorNames

    # Fetches information about arbitrary objects,
    # preserves only common properties
    def queryObjects(self, objectPHIDs):

        results = self.queryPHIDs(objectPHIDs)

        if results is None:
            return []

        objects = {}

        for objectPHID in results:

            obj = results[objectPHID]

            fullName = obj["fullName"][len(obj["name"] + " "):]

            if obj["typeName"] == "Differential Revision" or obj["typeName"] == "Diffusion Commit":
                fullName = fullName[len(":"):]

            objects[objectPHID] = \
                obj["typeName"], \
                obj["name"], \
                fullName, \
                obj["uri"]

        return objects

    # Returns title, uri, status name, creation and modified date,
    # author, reviewers, commits and trac tickets of the given numerical differential IDs
    def queryDifferentials(self, IDs):

        return self.queryAPI("/api/differential.query", {
            "ids[]": IDs
        })

    # Returns object PHID, authorName, uri, summary, epoch
    def queryCommitsByID(self, IDs):
        return self.queryAPI("/api/diffusion.querycommits", {
            "ids[]": IDs
        })

    # Returns object PHID, authorName, uri, summary, epoch
    def queryPastesByID(self, IDs):
        return self.queryAPI("/api/paste.query", {
            "ids[]": IDs
        })

    # Fetches some phabricator stories after the given chronological key,
    # Only yields story PHID, author PHIDs and the PHIDs of the associated object
    def queryFeed(self, chronokey, limit):

        results = self.queryAPI("/api/feed.query", {
            "before": chronokey, # TODO: why isn't this "after"?
            'limit': limit,
            'view': "text"
        })

        if results is None:
            return []

        stories = []
        authorPHIDs = []
        objectPHIDs = []
        #allTransactionPHIDs = []

        for storyPHID in results:
            epoch = int(results[storyPHID]["epoch"])
            cronkey = int(results[storyPHID]["chronologicalKey"])

            # If we don't recall the last
            if chronokey == 0 and epoch < datetime.utcnow():
                print("Ignoring outdated story from", cronkey)
                continue

            authorPHID = results[storyPHID]["authorPHID"]
            if authorPHID not in authorPHIDs:
                authorPHIDs.append(authorPHID)

            objectPHID = results[storyPHID]["objectPHID"]

            if objectPHID not in objectPHIDs:
                objectPHIDs.append(objectPHID)

            text = results[storyPHID]["text"]

            # Transactions are not queryable currently!
            # transactionPHIDs = list(results[storyPHID]["data"]["transactionPHIDs"].keys())
            # allTransactionPHIDs += transactionPHIDs

            stories.append((storyPHID, cronkey, epoch, authorPHID, objectPHID, text))

        return stories, objectPHIDs, authorPHIDs #, allTransactionPHIDs

Class = Phabricator
