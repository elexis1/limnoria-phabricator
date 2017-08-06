###
# Copyright (c) 2017, elexis
# All rights reserved.
###

import ssl
import supybot.conf as conf
import supybot.ircmsgs as ircmsgs
import supybot.ircutils as ircutils
import supybot.callbacks as callbacks
import http.client
import urllib.parse
import html

import time
import datetime
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

        self.syncedChannels = []
        self.thread = None

        self.conduitAPI = ConduitAPI(
            self.registryValue("phabricatorURL"),
            self.registryValue("phabricatorToken"),
            self.registryValue("acceptInvalidSSLCert"),
        )

        self.formatting = PhabricatorStringFormatting(True, self.registryValue("obscureUsernames"), False)

        self.storyPrinter = PhabricatorStoryPrinter(
            conduitAPI=self.conduitAPI,
            formatting=self.formatting,
            channels=self.registryValue("channels"),
            storyLimit=self.registryValue("storyLimit"),
            historyForwards=self.registryValue("historyForwards"),
            timestampAfter=self.registryValue("timestampAfter"),
            timestampBefore=self.registryValue("timestampBefore"),
            sleepTime=self.registryValue("sleepTime"),
            newsPrefix=self.registryValue("newsPrefix"),
            printDate=self.registryValue("printDate"),
            ignoredUsers=self.registryValue("ignoredUsers"),
            filteredUsers=self.registryValue("filteredUsers"),
            notifyCommit=self.registryValue("notifyCommit"),
            notifyRetitle=self.registryValue("notifyRetitle"),
            chronokeyFile=self.registryValue("chronokeyFile"),
            chronokey=None,
            verbose=self.registryValue("verbose")
        )

    # Respond to channel and private messages
    def doPrivmsg(self, irc, msg):

        # TODO: check whether it works with actual PMs
        channel = msg.args[0]
        strings = PhabricatorReplyPrinter(
            txt=msg.args[1],
            conduitAPI=self.conduitAPI,
            formatting=self.formatting
        ).getReplies()

        for strng in strings:
            irc.queueMsg(ircmsgs.privmsg(channel, strng))

    def do315(self, irc, msg):

        print("do315 in ", msg.args[1])
        print("current channels:", irc.state.channels.items())

        self.syncedChannels.append(msg.args[1])

        # Don't send messages before all channels were synced
        for (channel, _) in irc.state.channels.items():
            if channel not in self.syncedChannels:
                return

        print("all channels synced", msg.args[1])

        # Notify about recent phabricator stories
        if self.thread:
            print("thread still already running")
            return

        self.thread = threading.Thread(target=self.storyPrinter.printStoriesForever, args=(irc,), daemon=True)
        self.thread.start()

    def doPart(self, irc, msg):
        if msg.nick != conf.supybot.nick:
            return

        for channel in msg.args[0].split(','):
            if channel in self.syncedChannels:
                print("parting from ", channel)
                self.syncedChannels.remove(channel)

class PhabricatorReplyPrinter:

    def __init__(self, txt, conduitAPI, formatting):
        self.txt = txt
        self.conduitAPI = conduitAPI
        self.formatting = formatting

    def getReplies(self):
        return \
            self.__differentialReplies() + \
            self.__commitReplies() + \
            self.__pasteReplies()

    # Display the title and URL of all differential IDs appearing in the text (D123)
    def __differentialReplies(self):

        matches = re.findall(r"\b(D\d+)\b", self.txt)
        revisions = list(map(lambda d: d[1:], matches))
        revisions = OrderedDict.fromkeys(revisions, True)

        if revisions is None or len(revisions) == 0 or list(revisions)[0] == "":
            #print("Fix differnetial revision regex for", self.txt)
            return []

        results = self.conduitAPI.queryDifferentials(revisions)

        if results is None:
            return []

        strings = []
        for result in results:

            replyStringConstructor = PhabricatorReplyStringConstructor(
                objID="D" + result["id"],
                objLink=result["uri"],
                objTitle=result["title"],
                formatting=self.formatting
            )

            strings.append(replyStringConstructor.constructDifferentialReplyString(
                statusName=result["statusName"]
            ))

        return strings

    # Display the title and URL of all differential IDs appearing in the text (D123)
    def __commitReplies(self):

        # fails at ":D" as the colon is considered a word boundary too
        commitIDs = re.findall(r"\b(rP\d+)\b", self.txt)
        commitIDs = list(map(lambda d: d[2:], commitIDs))
        commitIDs = OrderedDict.fromkeys(commitIDs, True)

        if commitIDs is None or len(commitIDs) == 0 or list(commitIDs)[0] == "":
            #print("Fix commit regex for", self.txt)
            return []

        results = self.conduitAPI.queryCommitsByID(commitIDs).get("data")

        if results is None:
            return []

        strings = []
        for commitID in commitIDs:
            for commitPHID in results:

                result = results[commitPHID]
                if result["id"] == commitID:

                    replyStringConstructor = PhabricatorReplyStringConstructor(
                        objID="rP" + result["id"],
                        objLink=result["uri"],
                        objTitle=result["summary"],
                        formatting=self.formatting,
                    )

                    strings.append(replyStringConstructor.constructRevisionReplyString(
                        authorName=result["authorName"],
                    ))

        return strings

    # Display the title and URL of all differential IDs appearing in the text (D123)
    def __pasteReplies(self):

        pasteIDs = re.findall(r"\b(P\d+)\b", self.txt)
        pasteIDs = list(map(lambda d: d[1:], pasteIDs))
        pasteIDs = OrderedDict.fromkeys(pasteIDs, True)

        if pasteIDs is None or len(pasteIDs) == 0 or list(pasteIDs)[0] == "":
            #print("Fix paste regex for", self.txt)
            return []

        results = self.conduitAPI.queryPastesByID(pasteIDs)

        if results is None:
            return []

        authorPHIDs = []
        for pastePHID in results:
            authorPHID = results[pastePHID]["authorPHID"]
            if authorPHID not in authorPHIDs:
                authorPHIDs.append(authorPHID)

        authorNames = self.conduitAPI.queryAuthorNames(authorPHIDs)

        strings = []
        for pasteID in pasteIDs:
            for pastePHID in results:

                result = results[pastePHID]

                if result["id"] == pasteID:
                    replyStringConstructor = PhabricatorReplyStringConstructor(
                        objID="P" + result["id"],
                        objTitle=result["title"],
                        objLink=result["uri"],
                        formatting=self.formatting
                    )

                    strings.append(replyStringConstructor.constructPasteReplyString(
                        authorName=authorNames[result["authorPHID"]]
                    ))

        return strings

# Constructs human-readable strings and optionally posts them to IRC.
# Allows testing of the querying and printing without actually connecting to IRC.
class PhabricatorStoryPrinter:

    def __init__(self,
                 conduitAPI,
                 formatting,
                 channels,
                 storyLimit,
                 historyForwards,
                 timestampBefore,
                 timestampAfter,
                 sleepTime,
                 newsPrefix,
                 printDate,
                 ignoredUsers,
                 filteredUsers,
                 notifyCommit,
                 notifyRetitle,
                 chronokeyFile,
                 chronokey,
                 verbose
                ):

        self.conduitAPI = conduitAPI
        self.channels = channels
        self.formatting = formatting

        self.storyLimit = storyLimit
        self.historyForwards = historyForwards
        self.timestampBefore = timestampBefore
        self.timestampAfter = timestampAfter
        self.sleepTime = sleepTime
        self.newsPrefix = newsPrefix
        self.printDate = printDate
        self.ignoredUsers = ignoredUsers
        self.filteredUsers = filteredUsers
        self.notifyCommit = notifyCommit
        self.notifyRetitle = notifyRetitle
        self.chronokeyFile = chronokeyFile
        self.chronokey = chronokey
        self.verbose = verbose

        self.chronokeyEpoch = None

    # Repeatedly query and print new stories on phabricator
    def printStoriesForever(self, irc):

        self.chronokey = self.__loadChronokey()

        while True:
            try:
                if self.printSomeStories(irc):
                    return

            except KeyboardInterrupt:
                return
            except:
                raise

    def printSomeStories(self, irc):

        stories = self.pullSomeStories()
        if stories is True:
            return True

        for story in stories:
            string, _, _, _, _ = story
            print(string)
            if irc:
                for (channel,_) in irc.state.channels.items():
                    if not self.channels or channel in self.channels:
                        irc.queueMsg(ircmsgs.privmsg(channel, string))

        time.sleep(self.sleepTime)
        return False

    # Pulls some stories on phabricator that are more recent or older than the current chronokey.
    # Fetches the refered authors and differentials.
    # Returns a list of human-readable strings to be posted in irc and the updated chronokey or
    #
    def pullSomeStories(self):

        if self.chronokeyEpoch:
            if self.historyForwards and self.timestampBefore != 0 and self.chronokeyEpoch > self.timestampBefore or \
               not self.historyForwards and self.timestampAfter != 0 and self.chronokeyEpoch < self.timestampAfter:
                if self.verbose:
                    print("Finished, chronokey is ", self.chronokey)
                return True

        stories, objectPHIDs, authorPHIDs = self.conduitAPI.queryFeed(self.chronokey, self.storyLimit, self.historyForwards)
        authorNames = self.conduitAPI.queryAuthorNames(authorPHIDs)
        objects = self.conduitAPI.queryObjects(objectPHIDs)

        if not self.historyForwards and len(stories) == 0:
            if self.verbose:
                print("No more stories found")
            return True

        # We can't do anything with the transaction PHIDs! Not even getting the sub-URL of the modified object
        # https://secure.phabricator.com/T5873
        # transactions = queryObjects(allTransactionPHIDs)

        # Sort by timestamp
        storiesSorted = sorted(stories, key=lambda story: story[1], reverse=not self.historyForwards)

        strings = []
        for story in storiesSorted:

            # Extract the objects referenced by this particular story
            _, newChronokey, epoch, authorPHID, objectPHID, text = story
            objType, objID, objTitle, objLink = objects[objectPHID]
            authorName = authorNames[authorPHID]

            # Remember most recently actually printed story (in the specified chronological order)
            self.__updateChronokey(newChronokey, epoch)

            # TODO: move this to queryAuthorNames
            if authorPHID == "PHID-APPS-PhabricatorDiffusionApplication":
                if self.verbose:
                    print("Fallback: Commit without phabricator account: [" + text + "]")
                authorName = self.conduitAPI.queryCommitsByID(objID[len("rP"):]).get("data")[objectPHID]["author"]

            if self.__filterDate(epoch, True) or self.__filterUser(authorName):
                continue

            # Create a string from the parsed story data and referenced objects
            storyString = PhabricatorStoryStringConstructor(
                objType,
                objectPHID,
                objID,
                objTitle,
                objLink,
                authorName,
                text,
                self.notifyCommit,
                self.notifyRetitle,
                self.formatting,
                self.verbose
            ).constructStoryString()

            try:
                string, action = storyString
            except TypeError:
                print("constructStoryString returned non-iterable", storyString, "from", text)
                continue

            if string is None:
                continue

            datePrefix = datetime.datetime.fromtimestamp(epoch).strftime('[%Y-%m-%d %H:%M:%S] ') if self.printDate else ""
            string = datePrefix + self.newsPrefix + string
            strings.append((string, authorName, objID, objType, action))

        return strings

    def __filterUser(self, authorName):

        if self.ignoredUsers is not None and authorName in self.ignoredUsers:
            if self.verbose:
                print("Skipping blocked user", authorName)
            return True

        if self.filteredUsers and len(self.filteredUsers) and authorName not in self.filteredUsers:
            if self.verbose:
                print("Skipping non-filtered user", authorName)
            return True

        return False

    def __filterDate(self, timestamp, debugPrint):

        if self.timestampAfter != 0 and timestamp < self.timestampAfter:
            if self.verbose:
                print("Skipping story that is too old")
            return True

        if self.timestampBefore != 0 and timestamp > self.timestampBefore:
            if self.verbose:
                print("Skipping story that is too recent")
            return True

        return False

    # Remember the chronological entry of the most recently
    # processed or printed update on phabricator
    # Returns None or number
    def __loadChronokey(self):

        if self.chronokeyFile is None:
            return self.chronokey

        if not os.path.isfile(self.chronokeyFile):
            print(self.chronokeyFile, "not found, starting at 0")
            return self.chronokey

        return int(open(self.chronokeyFile, 'r').read())

    # Save the state immediately after processing a message,
    # so that we don't lose the state after a crash
    def __saveChronokey(self, chronokey):

        if self.verbose:
            print("Saving chronokey", chronokey)

        text_file = open(self.chronokeyFile, "w")
        text_file.write(str(chronokey) + "\n")
        text_file.close()

    def __updateChronokey(self, newChronokey, newEpoch):

        if self.chronokeyEpoch is None:
            self.chronokeyEpoch = newEpoch

        if self.chronokey is None:
            if self.verbose:
                print("Initializing chronokey with", newChronokey)
            self.chronokey = newChronokey
            return

        previous = self.chronokey
        if self.historyForwards:
            self.chronokey = max(self.chronokey, newChronokey)
            self.chronokeyEpoch = max(self.chronokeyEpoch, newEpoch)
        else:
            self.chronokey = min(self.chronokey, newChronokey)
            self.chronokeyEpoch  = min(self.chronokeyEpoch, newEpoch)

        if previous == self.chronokey:
            return

        if self.verbose:
            print("New chronokey:", self.chronokey)

        if self.chronokeyFile:
            self.__saveChronokey(self.chronokey)

# Provides some abstraction and parsing of the RESTful Phabricator API
import json
class ConduitAPI:

    def __init__(self, phabricatorURL, phabricatorToken, acceptInvalidSSLCert):
        self.phabricatorToken = phabricatorToken
        self.phabricatorURL = phabricatorURL
        self.acceptInvalidSSLCert = acceptInvalidSSLCert

    # Send an HTTPS GET request to the phabricator location and
    # return the interpreted JSON object
    def queryAPI(self, path, params):

        if self.phabricatorURL is None or self.phabricatorURL == "":
            print("Error: You must configure the Phabricator location!")
            return None

        if self.phabricatorToken is None or self.phabricatorToken == "":
            print("Error: You must configure a Phabricator API token!")
            return None

        params["api.token"] = self.phabricatorToken

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Charset": "utf-8"
        }

        conn = http.client.HTTPSConnection(self.phabricatorURL, context=ssl._create_unverified_context() if self.acceptInvalidSSLCert else None)
        conn.request("GET", path, urllib.parse.urlencode(params, True), headers)
        response = conn.getresponse()

        if response.status != 200:
            print(response.status, response.reason)
            conn.close()
            return None

        data = response.read()
        conn.close()
        data = json.loads(data.decode("utf-8"))

        if data["error_code"] is not None:
            print("Error:", data["error_info"])
            print("Query:", path, params)
            return None

        return data.get("result")

    # Return some information about arbitrary objects, like
    # differntials, users, commits, transactions, ...
    def queryPHIDs(self, phids):

        if len(phids) == 0:
            return []

        return self.queryAPI("/api/phid.query", {"phids[]": phids})

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

            fullName = obj["fullName"]

            # Clumsy object name parsing
            if obj["typeName"] != "Project":
                fullName = fullName[len(obj["name"] + " "):]

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
    def queryFeed(self, chronokey, storyLimit, historyForwards):

        arguments = {
            'limit': storyLimit,
            'view': "text"
        }

        # Query stories before or after the given chronokey,
        # otherwise query for the most recent ones (as of now)
        if chronokey is not None:
            if historyForwards:
                arguments["before"] = chronokey
            else:
                arguments["after"] = chronokey

        print("Pulling", storyLimit, "stories")
        results = self.queryAPI("/api/feed.query", arguments)

        if results is None:
            return [], [], []

        stories = []
        authorPHIDs = []
        objectPHIDs = []
        #allTransactionPHIDs = []

        for storyPHID in results:
            epoch = int(results[storyPHID]["epoch"])
            newChronokey = int(results[storyPHID]["chronologicalKey"])

            if chronokey is None:
                chronokey = newChronokey

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

            stories.append((storyPHID, newChronokey, epoch, authorPHID, objectPHID, text))

        return stories, objectPHIDs, authorPHIDs #, allTransactionPHIDs

class PhabricatorStringFormatting:

    def __init__(self, bolding, obscureUsernames, htmlLinks):
        self.bolding = bolding
        self.obscureUsernames = obscureUsernames
        self.htmlLinks = htmlLinks

    def bold(self, txt):
        if not self.bolding:
            return txt
        return ircutils.bold(txt)

    # Adds invisible whitespace between characters to
    # avoid people pinging themselves with updates
    def obscureAuthorName(self, authorName):
        if not self.obscureUsernames:
            return authorName
        return u"\u200B".join(list(authorName))

    def formatLink(self, url):
        if not self.htmlLinks:
            return "<" + url + ">"
        return "<a href=\"" + url + "\">" + html.escape("<" + url + ">") + "</a>"

class PhabricatorReplyStringConstructor:

    def __init__(self, objID, objTitle, objLink, formatting):
        self.objID = objID
        self.objTitle = objTitle
        self.objLink = objLink
        self.formatting = formatting

    def constructDifferentialReplyString(self, statusName):
        return self.formatting.bold(self.objID) + ": " + self.objTitle + " [" + statusName + "] – " + \
            self.formatting.formatLink(self.objLink)

    def constructRevisionReplyString(self, authorName):
        return self.formatting.bold(self.objID) + " " + \
            self.formatting.bold("Author:") + " " + self.formatting.obscureAuthorName(authorName) + ". " + \
            self.formatting.bold("Commit message:") + " " + self.objTitle + " " + \
            self.formatting.formatLink(self.objLink)

    def constructPasteReplyString(self, authorName):
        return self.formatting.bold("Paste " + self.objID) + " " + \
            self.formatting.bold("Author:") + " " + self.formatting.obscureAuthorName(authorName) + ". " + \
            self.formatting.bold("Title:") + " " + self.objTitle+ " " + \
            self.formatting.formatLink(self.objLink)

class PhabricatorStoryStringConstructor:

    def __init__(self, objType, objectPHID, objID, objTitle, objLink, authorName, text, notifyCommit, notifyRetitle, formatting, verbose):
        self.objType = objType
        self.objectPHID = objectPHID
        self.objID = objID
        self.objTitle = objTitle
        self.objLink = objLink
        self.authorName = authorName
        self.text = text
        self.formatting = formatting
        self.notifyCommit = notifyCommit
        self.notifyRetitle = notifyRetitle
        self.verbose = verbose

        # Clumsy parsing of the "text" property of the feed.query api results, since transactionPHIDs can't be queried yet
        self.action = self.text[len(self.authorName + " "):]

    # Returns the string and the action identifier
    def constructStoryString(self):

        if self.objType == "Differential Revision":
            return self.__constructDifferentialRevisionStoryString()

        if self.objType == "Diffusion Commit":
            return self.__constructCommitStoryString()

        if self.objType == "Paste":
            return self.__constructPasteStoryString()

        if self.objType == "Project":
            return self.__constructProjectStoryString()

        if self.objType == "Image Macro":
            return self.__constructImageMacroStoryString()

        print("Unexpected object type '" + self.objType + "'", self.objectPHID)
        return None, None

    def __constructDifferentialRevisionStoryString(self):

        # TODO: lookup the file that contains the strings, link it, add remaining strings
        supportedActions = (
            "created",
            "retitled",
            "closed",
            "accepted",
            "awarded",
            "resigned from",
            "abandoned",
            "reclaimed",
            "commandeered",
            "added a dependency for",
            "added a dependent revision for",
            "removed a project from",
            "planned changes to",
            "requested review of",
            "added a reviewer for",
            "removed a reviewer for",
            "edited reviewers for",
            "removed 1 commit(s)",
            "added 1 commit(s)",
            # TODO: removed reviewers for?
            "failed to build",
            "added reviewers for", # TODO: that query is messed up e​l​e​x​i​s added reviewers for D188: Whales shou D188 (Whales should not block ships) <https://code.wildfiregames.com/D188>.
            "added a comment to", # TODO: extra space
            "added inline comments to",
            "updated",
            "updated the summary of",
            "updated the diff for",
            "updated subscribers of",
            "updated the Trac tickets for",
            "updated the test plan for",
            "requested changes to",
            "changed the visibility for",
            "set the repository for",
        )

        if not self.action.startswith(supportedActions):
            print("WARNING! unsupported differential revision action:", self.action)

        # contrary to other actions, this one extends the string by the added reviewer
        if self.action.startswith("added a reviewer for"):
            return self.__constructDifferentialRevisionReviewerAddedStoryString(), "added a reviewer for"

        if self.action.startswith("closed"):
            return self.__constructDifferentialRevisionCloseStoryString(), "closed"

        if self.action.startswith("set the repository for"):
            return self.__constructDifferentialRevisionSetRepositoryStoryString(), "set the repository for"

        if self.action.startswith("awarded"):
            return self.__constructDifferentialRevisionAwardedStoryString(), "awarded"

        if self.action.startswith("retitled"):
            return self.__constructDifferentialRevisionRetitleStoryString(), "retitled"

        # All other cases are assumed to have this format
        action = self.action[:-len(" " + self.objID + ": " + self.objTitle + ".")]

        string = self.formatting.obscureAuthorName(self.authorName) + " " + \
            action + " " + \
            self.formatting.bold(self.objID) + " (" + self.objTitle + ") " + \
            self.formatting.formatLink(self.objLink)

        return string, action

    def __constructGenericStoryString(self, action):
        string = self.formatting.obscureAuthorName(self.authorName) + \
            " " + action + " " + \
            self.formatting.bold(self.objID) + " (" + self.objTitle + ") " + \
            self.formatting.formatLink(self.objLink)
        return string

    def __constructDifferentialRevisionRetitleStoryString(self):

        # We don't print the previous title which is sent by the conduitAPI
        if not self.notifyRetitle:
            if self.verbose:
                print("Skipping retitle of", self.objID)
            return None
        return self.__constructGenericStoryString("retitled")

    def __constructDifferentialRevisionReviewerAddedStoryString(self):
        # TODO: broken string: e​l​e​x​i​s added e​O​b​j​e​c​t​s​:​ ​e​l​e​x​i​s as a reviewer for D189 (Extending rmgen lib's SimpleGroup's place method to avoid collision of included SimpleObjects) <https://code.wildfiregames.com/D189>.
        addedReviewer = self.action[len("added a reviewer for" + " " + self.objID + ": " + self.objTitle + ": "):-len(".")]
        return self.__constructGenericStoryString(
            "added " + \
            self.formatting.obscureAuthorName(addedReviewer) + \
            " as a reviewer for")

    def __constructDifferentialRevisionAwardedStoryString(self):
        token = self.action[len("awarded " + self.objID + ": " + self.objTitle + " a "):-len(" token.")]
        return self.__constructGenericStoryString("gave a " + token + " award to ")

    def __constructDifferentialRevisionCloseStoryString(self):

        #by = self.action[len("closed " + self.objID + ": " + self.objTitle):-len(".")]

        #if not by:
        return self.__constructGenericStoryString("closed")

        #commitID = by[len(" by committing"):].split(":", 1)[0]
        #return self.__constructGenericStoryString("closed by committing " + commitID)

    def __constructDifferentialRevisionSetRepositoryStoryString(self):
        # This cuts off the repetition of the object title in the action string
        return self.__constructGenericStoryString("set the repository for")

    def __constructCommitStoryString(self):

        supportedActions = (
            "committed",
            "added a comment to",
            "added inline comments to",
            "raised a concern with",
            "accepted",
            "added auditors to", # TODO: contains auditor name
            "edited edges for",
            "added an edge to",
            "requested verification of",
            "updated subscribers of",
            # TODO awarded
        )

        if self.action.startswith("committed"):
            if not self.notifyCommit:
                if self.verbose:
                    print("Skipping commit", self.objID, self.objTitle)
                return None, None
            return self.__constructGenericStoryString("committed"), "committed"

        for action in supportedActions:
            if self.action.startswith(action):
                return self.__constructGenericStoryString(action), action

        print("Unknown commit story type:", self.action)
        return None, None

    def __constructPasteStoryString(self):

        supportedActions = (
            "created",
            "edited",
            "archived",
            "added a comment to",
            "updated the title for",
            "updated the language for",
            "changed the visibility for"
        )

        if not self.action.startswith(supportedActions):
            print("Unknown paste story type:", self.action)
            return None, None

        # Notice the missing colon between ID and Title
        action = self.action[:-len(" " + self.objID + " " + self.objTitle)]

        return self.__constructGenericStoryString(action), action

    # Almost never new projects are created, so meh
    def __constructProjectStoryString(self):

        # TODO: created

        addedMemberAction = "added a member for"
        if self.action.startswith(addedMemberAction):
            addedMember = self.action[len(addedMemberAction + " " + self.objTitle + ": "):-len(".")]
            return self.__constructGenericStoryString(
                "added " + \
                self.formatting.obscureAuthorName(addedMember) + " " + \
                "as a member to"
            ), addedMemberAction
            # TODO: should the one above really contain the objectID?
            #return self.formatting.obscureAuthorName(self.authorName) + " " + \
            #    "added " + \
            #    self.formatting.obscureAuthorName(addedMember) + " " + \
            #    "as a member to " + \
            #    self.formatting.bold(self.objTitle) + " " \
            #    self.formatting.formatLink(self.objLink)

        addedMembersAction = "added members for"
        if self.action.startswith(addedMembersAction):
            addedMembers = self.action[len(addedMembersAction + " " + self.objTitle + ": "):-len(".")].split(", ")
            return self.formatting.obscureAuthorName(self.authorName) + " " + \
                "added " + \
                ", ".join(map(lambda member: self.formatting.obscureAuthorName(member), addedMembers)) + " " + \
                "as members to " + \
                self.formatting.bold(self.objTitle) + " " + \
                self.formatting.formatLink(self.objLink), addedMembersAction

        editPolicyAction = "changed the edit policy for"
        if self.action.startswith(editPolicyAction):
            return self.formatting.obscureAuthorName(self.authorName) + " " + \
                editPolicyAction + " " + \
                self.formatting.bold(self.objTitle) + " " + \
                self.formatting.formatLink(self.objLink), editPolicyAction

        print("Unsupported project story action:", self.action)
        return None, None

    def __constructImageMacroStoryString(self):
        return None, None

Class = Phabricator
